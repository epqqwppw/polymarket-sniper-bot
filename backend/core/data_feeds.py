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
    POLYMARKET_RTDS_URL,
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

                    # Subscribe to known tokens — official format per
                    # docs.polymarket.com/market-data/websocket/market-channel
                    if self._subscribed_tokens:
                        sub_msg = {
                            "assets_ids": list(self._subscribed_tokens),
                            "type": "market",
                            "custom_feature_enabled": True,
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

            if event_type in ("price_change", "best_bid_ask"):
                asset_id = msg.get("asset_id", "")
                price = safe_float(msg.get("price"))
                if asset_id and price:
                    self.yes_prices[asset_id] = price
                    await redis_manager.publish(
                        f"orderflow:{asset_id}",
                        {"type": "price", "asset_id": asset_id, "price": price, "ts": timestamp_ms()},
                    )

            elif event_type == "last_trade_price":
                # Per official docs this is the trade execution event
                asset_id = msg.get("asset_id", "")
                price = safe_float(msg.get("price", msg.get("last_trade_price")))
                side = msg.get("side", "")
                size = safe_float(msg.get("size"))
                ts = timestamp_ms()
                if asset_id and price:
                    self.yes_prices[asset_id] = price
                if asset_id:
                    trade = {"side": side, "size": size, "price": price, "ts": ts, "asset_id": asset_id}
                    self.order_flow[asset_id].append(trade)
                    await redis_manager.publish(f"orderflow:{asset_id}", trade)

        except Exception:
            logger.exception("Error handling CLOB message")

    # ── Feed 3: Polymarket RTDS (Chainlink Resolution Price) ────────────

    async def _polymarket_rtds_loop(self) -> None:
        """Connect to RTDS for Chainlink resolution prices.

        The RTDS (Real-Time Data Socket) at wss://ws-live-data.polymarket.com
        provides the exact Chainlink price Polymarket uses to resolve markets.
        Subscription format per docs.polymarket.com/market-data/websocket/rtds
        """
        backoff = 1
        while self._running:
            try:
                logger.info("Connecting to Polymarket RTDS …")
                async with websockets.connect(POLYMARKET_RTDS_URL, ping_interval=5) as ws:
                    self.rtds_healthy = True
                    backoff = 1
                    logger.info("RTDS connected to %s", POLYMARKET_RTDS_URL)

                    # Subscribe to Chainlink crypto prices — official RTDS format
                    sub = {
                        "action": "subscribe",
                        "subscriptions": [
                            {
                                "topic": "crypto_prices_chainlink",
                                "type": "*",
                            }
                        ],
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
        """Handle RTDS messages.

        Official payload structure (docs.polymarket.com/market-data/websocket/rtds):
        {
            "topic": "crypto_prices_chainlink",
            "type": "update",
            "timestamp": 1753314064237,
            "payload": {
                "symbol": "btcusd",
                "timestamp": 1753314064213,
                "value": 84250.55
            }
        }
        """
        try:
            msg = json.loads(raw)
            topic = msg.get("topic", "")

            if topic == "crypto_prices_chainlink":
                payload = msg.get("payload", {})
                if isinstance(payload, dict) and "symbol" in payload:
                    # Single-symbol update
                    await self._process_rtds_price(payload)
                elif isinstance(payload, list):
                    # Batch update
                    for item in payload:
                        await self._process_rtds_price(item)
            elif topic == "crypto_prices":
                # Binance-sourced prices also available via RTDS
                payload = msg.get("payload", {})
                if isinstance(payload, dict) and "symbol" in payload:
                    await self._process_rtds_price(payload)
        except Exception:
            logger.exception("Error handling RTDS message")

    async def _process_rtds_price(self, payload: dict) -> None:
        """Extract asset and price from a single RTDS price payload."""
        symbol = payload.get("symbol", "").upper().replace("/", "")
        # Normalize symbols: "BTCUSD" → "BTC", "ETHUSD" → "ETH", etc.
        asset = None
        for prefix in ("BTC", "ETH", "SOL"):
            if symbol.startswith(prefix):
                asset = prefix
                break
        if not asset:
            return

        price = safe_float(payload.get("value", payload.get("price")))
        if not price:
            return

        ts = int(payload.get("timestamp", timestamp_ms()))
        self.chainlink_prices[asset] = price
        self.chainlink_ts[asset] = ts
        await redis_manager.publish(
            f"price:chainlink:{asset}",
            {"price": price, "ts": ts},
        )

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
        """Fetch current funding rate from Binance premiumIndex endpoint.

        /fapi/v1/premiumIndex returns real-time data including lastFundingRate.
        /fapi/v1/fundingRate only returns historical rates — not suitable for
        live trading decisions.
        """
        if not self._http:
            return
        url = f"{BINANCE_FUTURES_API}/fapi/v1/premiumIndex"
        try:
            async with self._http.get(
                url, params={"symbol": symbol},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data and isinstance(data, dict):
                        self.funding_rates[asset] = safe_float(data.get("lastFundingRate"))
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
