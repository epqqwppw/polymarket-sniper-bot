"""Real-time data feeds: Binance WS, Polymarket CLOB/RTDS, CoinGecko fallback."""

import asyncio
import json
import time
from collections import defaultdict, deque
from typing import Any, Deque, Dict, List, Optional, Set

import aiohttp
import websockets
import websockets.exceptions

from backend.config import (
    BINANCE_FUTURES_API,
    BINANCE_WS_URL,
    COINGECKO_API,
    POLYMARKET_WS_URL,
)
from backend.core.redis_manager import redis_manager
from backend.utils.helpers import safe_float, timestamp_ms
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# Symbol mapping for Binance streams
_SYMBOL_MAP = {"BTCUSDT": "BTC", "ETHUSDT": "ETH", "SOLUSDT": "SOL"}
_FUTURES_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
_COINGECKO_IDS = {"bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL"}

# Max ticks kept in local memory (Redis holds its own buffer)
_LOCAL_BUFFER_SIZE = 300


class DataFeedManager:
    """Manages all real-time data feed connections."""

    def __init__(self) -> None:
        # Latest spot prices from Binance
        self.binance_prices: Dict[str, float] = {}
        self.binance_ts: Dict[str, int] = {}

        # Chainlink / RTDS prices
        self.chainlink_prices: Dict[str, float] = {}
        self.chainlink_ts: Dict[str, int] = {}

        # Local rolling price buffers (deque of {price, ts} dicts)
        self.price_buffers: Dict[str, Deque[Dict[str, Any]]] = defaultdict(
            lambda: deque(maxlen=_LOCAL_BUFFER_SIZE)
        )

        # Polymarket CLOB order-flow data
        self.yes_prices: Dict[str, float] = {}
        self.no_prices: Dict[str, float] = {}
        self.order_flow: Dict[str, Deque[Dict]] = defaultdict(
            lambda: deque(maxlen=200)
        )

        # Binance Futures supplementary data
        self.funding_rates: Dict[str, float] = {}
        self.open_interest: Dict[str, float] = {}

        # Active market token IDs being subscribed to
        self._subscribed_tokens: Set[str] = set()

        # Asyncio tasks
        self._tasks: List[asyncio.Task] = []
        self._running = False

        # HTTP session for REST calls
        self._http: Optional[aiohttp.ClientSession] = None

        # Fallback flag
        self.binance_ws_healthy = False
        self.rtds_healthy = False

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start all data feed tasks."""
        self._running = True
        self._http = aiohttp.ClientSession()
        self._tasks = [
            asyncio.create_task(self._binance_ws_loop(), name="binance_ws"),
            asyncio.create_task(self._polymarket_clob_ws_loop(), name="poly_clob"),
            asyncio.create_task(self._polymarket_rtds_loop(), name="poly_rtds"),
            asyncio.create_task(self._binance_futures_poll(), name="futures_poll"),
            asyncio.create_task(self._coingecko_fallback_loop(), name="coingecko"),
        ]
        logger.info("DataFeedManager started (%d tasks)", len(self._tasks))

    async def stop(self) -> None:
        """Cancel all feed tasks and clean up."""
        self._running = False
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        if self._http:
            await self._http.close()
        logger.info("DataFeedManager stopped")

    def subscribe_market_tokens(self, yes_id: str, no_id: str) -> None:
        """Register token IDs so the CLOB WS subscribes to them."""
        self._subscribed_tokens.add(yes_id)
        self._subscribed_tokens.add(no_id)

    # ── Feed 1: Binance Aggregate-Trade WebSocket ────────────────────────

    async def _binance_ws_loop(self) -> None:
        backoff = 1
        while self._running:
            try:
                logger.info("Connecting to Binance WS …")
                async with websockets.connect(BINANCE_WS_URL, ping_interval=20) as ws:
                    self.binance_ws_healthy = True
                    backoff = 1
                    logger.info("Binance WS connected")
                    async for raw in ws:
                        if not self._running:
                            break
                        await self._handle_binance_msg(raw)
            except (websockets.exceptions.ConnectionClosed, ConnectionError, OSError) as exc:
                self.binance_ws_healthy = False
                logger.warning("Binance WS disconnected: %s – reconnect in %ds", exc, backoff)
            except asyncio.CancelledError:
                return
            except Exception:
                self.binance_ws_healthy = False
                logger.exception("Binance WS unexpected error – reconnect in %ds", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)

    async def _handle_binance_msg(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
            data = msg.get("data", msg)
            symbol = data.get("s", "")
            asset = _SYMBOL_MAP.get(symbol)
            if not asset:
                return
            price = safe_float(data.get("p"))
            qty = safe_float(data.get("q"))
            ts = int(data.get("T", timestamp_ms()))

            self.binance_prices[asset] = price
            self.binance_ts[asset] = ts

            tick = {"price": price, "qty": qty, "ts": ts}
            self.price_buffers[asset].append(tick)

            # Push to Redis
            await redis_manager.push_price_tick(asset, price, ts)
            await redis_manager.publish(
                f"price:binance:{asset}",
                {"price": price, "ts": ts},
            )
        except Exception:
            logger.exception("Error handling Binance message")

    # ── Feed 2: Polymarket CLOB WebSocket ────────────────────────────────

    async def _polymarket_clob_ws_loop(self) -> None:
        backoff = 1
        while self._running:
            try:
                logger.info("Connecting to Polymarket CLOB WS …")
                async with websockets.connect(POLYMARKET_WS_URL, ping_interval=25) as ws:
                    backoff = 1
                    logger.info("Polymarket CLOB WS connected")

                    # Subscribe to known tokens
                    if self._subscribed_tokens:
                        sub_msg = {
                            "type": "subscribe",
                            "channel": "market",
                            "assets_ids": list(self._subscribed_tokens),
                        }
                        await ws.send(json.dumps(sub_msg))

                    async for raw in ws:
                        if not self._running:
                            break
                        await self._handle_clob_msg(raw)
            except (websockets.exceptions.ConnectionClosed, ConnectionError, OSError) as exc:
                logger.warning("Polymarket CLOB WS disconnected: %s – reconnect in %ds", exc, backoff)
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("Polymarket CLOB WS error – reconnect in %ds", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)

    async def _handle_clob_msg(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
            event_type = msg.get("event_type", msg.get("type", ""))

            if event_type in ("price_change", "last_trade_price"):
                asset_id = msg.get("asset_id", "")
                price = safe_float(msg.get("price", msg.get("last_trade_price")))
                if asset_id and price:
                    # We store both YES and NO prices keyed by token ID
                    self.yes_prices[asset_id] = price
                    await redis_manager.publish(
                        f"orderflow:{asset_id}",
                        {"type": "price", "asset_id": asset_id, "price": price, "ts": timestamp_ms()},
                    )

            elif event_type == "trade":
                asset_id = msg.get("asset_id", "")
                side = msg.get("side", "")
                size = safe_float(msg.get("size"))
                price = safe_float(msg.get("price"))
                ts = timestamp_ms()
                trade = {"side": side, "size": size, "price": price, "ts": ts, "asset_id": asset_id}
                self.order_flow[asset_id].append(trade)
                await redis_manager.publish(f"orderflow:{asset_id}", trade)

        except Exception:
            logger.exception("Error handling CLOB message")

    # ── Feed 3: Polymarket RTDS (Chainlink Resolution Price) ────────────

    async def _polymarket_rtds_loop(self) -> None:
        """Connect to RTDS for Chainlink resolution prices.

        The RTDS WebSocket provides the exact price Polymarket uses to
        resolve markets, making it the most critical data feed.
        """
        backoff = 1
        rtds_url = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
        while self._running:
            try:
                logger.info("Connecting to Polymarket RTDS …")
                async with websockets.connect(rtds_url, ping_interval=25) as ws:
                    self.rtds_healthy = True
                    backoff = 1
                    logger.info("RTDS connected")

                    # Subscribe to Chainlink crypto prices
                    sub = {
                        "type": "subscribe",
                        "channel": "crypto_prices_chainlink",
                        "symbols": ["btc/usd", "eth/usd", "sol/usd"],
                    }
                    await ws.send(json.dumps(sub))

                    async for raw in ws:
                        if not self._running:
                            break
                        await self._handle_rtds_msg(raw)
            except (websockets.exceptions.ConnectionClosed, ConnectionError, OSError) as exc:
                self.rtds_healthy = False
                logger.warning("RTDS disconnected: %s – reconnect in %ds", exc, backoff)
            except asyncio.CancelledError:
                return
            except Exception:
                self.rtds_healthy = False
                logger.exception("RTDS error – reconnect in %ds", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)

    async def _handle_rtds_msg(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
            prices = msg.get("prices", msg.get("data", {}))
            if isinstance(prices, dict):
                for sym, val in prices.items():
                    asset = sym.split("/")[0].upper()
                    if asset in ("BTC", "ETH", "SOL"):
                        price = safe_float(val)
                        ts = timestamp_ms()
                        self.chainlink_prices[asset] = price
                        self.chainlink_ts[asset] = ts
                        await redis_manager.publish(
                            f"price:chainlink:{asset}",
                            {"price": price, "ts": ts},
                        )
            # Handle array-style responses too
            elif isinstance(prices, list):
                for item in prices:
                    sym = item.get("symbol", "")
                    asset = sym.split("/")[0].upper()
                    if asset in ("BTC", "ETH", "SOL"):
                        price = safe_float(item.get("price"))
                        ts = timestamp_ms()
                        self.chainlink_prices[asset] = price
                        self.chainlink_ts[asset] = ts
                        await redis_manager.publish(
                            f"price:chainlink:{asset}",
                            {"price": price, "ts": ts},
                        )
            # If top-level has price field
            elif "price" in msg:
                sym = msg.get("symbol", "")
                asset = sym.split("/")[0].upper()
                if asset in ("BTC", "ETH", "SOL"):
                    price = safe_float(msg["price"])
                    ts = timestamp_ms()
                    self.chainlink_prices[asset] = price
                    self.chainlink_ts[asset] = ts
                    await redis_manager.publish(
                        f"price:chainlink:{asset}",
                        {"price": price, "ts": ts},
                    )
        except Exception:
            logger.exception("Error handling RTDS message")

    # ── Feed 4: Binance Futures REST Polling ─────────────────────────────

    async def _binance_futures_poll(self) -> None:
        """Poll Binance Futures API every 5 seconds for funding rate + OI."""
        while self._running:
            try:
                for sym in _FUTURES_SYMBOLS:
                    asset = _SYMBOL_MAP[sym]
                    await asyncio.gather(
                        self._fetch_funding_rate(sym, asset),
                        self._fetch_open_interest(sym, asset),
                    )
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("Binance Futures poll error")
            await asyncio.sleep(5)

    async def _fetch_funding_rate(self, symbol: str, asset: str) -> None:
        if not self._http:
            return
        url = f"{BINANCE_FUTURES_API}/fapi/v1/fundingRate"
        try:
            async with self._http.get(
                url, params={"symbol": symbol, "limit": "1"},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data and isinstance(data, list):
                        self.funding_rates[asset] = safe_float(data[0].get("fundingRate"))
        except Exception:
            logger.debug("Failed to fetch funding rate for %s", symbol)

    async def _fetch_open_interest(self, symbol: str, asset: str) -> None:
        if not self._http:
            return
        url = f"{BINANCE_FUTURES_API}/fapi/v1/openInterest"
        try:
            async with self._http.get(
                url, params={"symbol": symbol},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.open_interest[asset] = safe_float(data.get("openInterest"))
        except Exception:
            logger.debug("Failed to fetch open interest for %s", symbol)

    # ── Feed 5: CoinGecko Fallback ──────────────────────────────────────

    async def _coingecko_fallback_loop(self) -> None:
        """Poll CoinGecko every 2 seconds ONLY when Binance WS is down."""
        while self._running:
            try:
                if not self.binance_ws_healthy:
                    await self._fetch_coingecko()
            except asyncio.CancelledError:
                return
            except Exception:
                logger.debug("CoinGecko fallback error")
            await asyncio.sleep(2)

    async def _fetch_coingecko(self) -> None:
        if not self._http:
            return
        ids = ",".join(_COINGECKO_IDS.keys())
        url = f"{COINGECKO_API}/simple/price"
        params = {"ids": ids, "vs_currencies": "usd"}
        try:
            async with self._http.get(
                url, params=params, timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    ts = timestamp_ms()
                    for cg_id, asset in _COINGECKO_IDS.items():
                        if cg_id in data:
                            price = safe_float(data[cg_id].get("usd"))
                            if price:
                                self.binance_prices[asset] = price
                                self.binance_ts[asset] = ts
                                self.price_buffers[asset].append({"price": price, "ts": ts})
                                await redis_manager.push_price_tick(asset, price, ts)
                                await redis_manager.publish(
                                    f"price:binance:{asset}",
                                    {"price": price, "ts": ts, "source": "coingecko"},
                                )
                    logger.debug("CoinGecko fallback prices updated")
        except Exception:
            logger.debug("CoinGecko API request failed")

    # ── Helper Methods ───────────────────────────────────────────────────

    def get_price_momentum(self, asset: str, window_secs: int) -> float:
        """Calculate price change over the last *window_secs* seconds."""
        buf = self.price_buffers.get(asset)
        if not buf or len(buf) < 2:
            return 0.0
        now = timestamp_ms()
        cutoff = now - (window_secs * 1000)
        current = buf[-1]["price"]

        # Find the earliest tick within the window
        for tick in buf:
            if tick["ts"] >= cutoff:
                return current - tick["price"]
        return 0.0

    def get_net_order_flow(self, token_id: str, window_secs: int = 30) -> float:
        """Net order flow (buy size - sell size) over a rolling window."""
        trades = self.order_flow.get(token_id)
        if not trades:
            return 0.0
        cutoff = timestamp_ms() - (window_secs * 1000)
        net = 0.0
        for t in trades:
            if t["ts"] >= cutoff:
                if t.get("side") == "buy":
                    net += t.get("size", 0.0)
                else:
                    net -= t.get("size", 0.0)
        return net


# Module-level singleton
data_feed_manager = DataFeedManager()
