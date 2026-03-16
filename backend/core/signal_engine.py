"""Signal engine — computes all 15 technical indicators in real-time."""

import asyncio
import math
import time
from collections import deque
from typing import Deque, Dict, List, Optional

from backend.core.data_feeds import data_feed_manager
from backend.core.redis_manager import redis_manager
from backend.models.market import MarketInfo
from backend.models.signal import SignalSet
from backend.utils.helpers import timestamp_ms
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# Rolling buffers for 1-second candle closes used by RSI / EMA
_CANDLE_BUFFER_SIZE = 120  # 2 minutes of 1s candles


class _AssetState:
    """Per-asset rolling state for indicator calculations."""

    def __init__(self) -> None:
        self.candle_closes: Deque[float] = deque(maxlen=_CANDLE_BUFFER_SIZE)
        self.candle_volumes: Deque[float] = deque(maxlen=_CANDLE_BUFFER_SIZE)
        self.candle_timestamps: Deque[int] = deque(maxlen=_CANDLE_BUFFER_SIZE)
        self.last_candle_sec: int = 0  # the second we last bucketed a candle
        self._ema5: Optional[float] = None
        self._ema15: Optional[float] = None
        self._vwap_cum_pv: float = 0.0  # cumulative price*volume
        self._vwap_cum_v: float = 0.0   # cumulative volume
        self._prev_oi: Optional[float] = None
        self._prev_oi_ts: int = 0

    # ── 1-Second Candle Bucketing ────────────────────────────────────────

    def update_candle(self, price: float, volume: float = 1.0) -> None:
        """Bucket tick into 1-second candles."""
        now_sec = int(time.time())
        if now_sec != self.last_candle_sec:
            self.candle_closes.append(price)
            self.candle_volumes.append(volume)
            self.candle_timestamps.append(now_sec)
            self.last_candle_sec = now_sec
            self._update_ema(price)
            self._vwap_cum_pv += price * volume
            self._vwap_cum_v += volume
        else:
            # Update the current candle's close
            if self.candle_closes:
                self.candle_closes[-1] = price
                self.candle_volumes[-1] += volume
                self._vwap_cum_pv += price * volume
                self._vwap_cum_v += volume

    # ── RSI (14-period, 1s candles) ──────────────────────────────────────

    def compute_rsi(self, period: int = 14) -> Optional[float]:
        """Standard RSI on 1-second candle closes."""
        if len(self.candle_closes) < period + 1:
            return None
        closes = list(self.candle_closes)
        gains = []
        losses = []
        for i in range(-period, 0):
            delta = closes[i] - closes[i - 1]
            if delta > 0:
                gains.append(delta)
                losses.append(0.0)
            else:
                gains.append(0.0)
                losses.append(abs(delta))
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    # ── EMA Crossover (5/15) ─────────────────────────────────────────────

    def _update_ema(self, price: float) -> None:
        k5 = 2.0 / (5 + 1)
        k15 = 2.0 / (15 + 1)
        if self._ema5 is None:
            self._ema5 = price
            self._ema15 = price
        else:
            self._ema5 = price * k5 + self._ema5 * (1 - k5)
            self._ema15 = price * k15 + self._ema15 * (1 - k15)

    def ema_crossover(self) -> float:
        """EMA(5) - EMA(15). Positive = bullish, negative = bearish."""
        if self._ema5 is None or self._ema15 is None:
            return 0.0
        return self._ema5 - self._ema15

    # ── VWAP Deviation ───────────────────────────────────────────────────

    def vwap_deviation(self, current_price: float) -> float:
        """(price - VWAP) / VWAP * 100."""
        if self._vwap_cum_v == 0:
            return 0.0
        vwap = self._vwap_cum_pv / self._vwap_cum_v
        if vwap == 0:
            return 0.0
        return (current_price - vwap) / vwap * 100.0

    # ── Volatility (60s rolling std dev) ─────────────────────────────────

    def volatility_60s(self) -> float:
        """Standard deviation of candle closes over last 60 seconds."""
        if len(self.candle_closes) < 2:
            return 0.0
        cutoff = int(time.time()) - 60
        recent = [
            c for c, t in zip(self.candle_closes, self.candle_timestamps) if t >= cutoff
        ]
        if len(recent) < 2:
            return 0.0
        mean = sum(recent) / len(recent)
        variance = sum((x - mean) ** 2 for x in recent) / len(recent)
        return math.sqrt(variance)

    # ── Open Interest Change ─────────────────────────────────────────────

    def update_oi(self, oi: float) -> Optional[float]:
        """Track open interest and return 5-min % change."""
        now = int(time.time())
        if self._prev_oi is None or (now - self._prev_oi_ts) >= 300:
            old = self._prev_oi
            self._prev_oi = oi
            self._prev_oi_ts = now
            if old and old > 0:
                return ((oi - old) / old) * 100.0
        return None

    def reset_vwap(self) -> None:
        """Reset VWAP accumulators (call at market open)."""
        self._vwap_cum_pv = 0.0
        self._vwap_cum_v = 0.0


class SignalEngine:
    """Computes all 15 indicators for each active market."""

    def __init__(self) -> None:
        self._asset_states: Dict[str, _AssetState] = {}
        self._markets: Dict[str, MarketInfo] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self.latest_signals: Dict[str, SignalSet] = {}

    def _state(self, asset: str) -> _AssetState:
        if asset not in self._asset_states:
            self._asset_states[asset] = _AssetState()
        return self._asset_states[asset]

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._compute_loop(), name="signal_engine")
        logger.info("SignalEngine started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("SignalEngine stopped")

    def track_market(self, market: MarketInfo) -> None:
        """Register a market for signal computation."""
        self._markets[market.slug] = market
        st = self._state(market.asset.value)
        st.reset_vwap()

    def untrack_market(self, slug: str) -> None:
        self._markets.pop(slug, None)
        self.latest_signals.pop(slug, None)

    # ── Main Compute Loop (every 500ms) ─────────────────────────────────

    async def _compute_loop(self) -> None:
        while self._running:
            try:
                for slug, market in list(self._markets.items()):
                    signals = self._compute_signals(market)
                    self.latest_signals[slug] = signals
                    # Publish to Redis
                    await redis_manager.publish(
                        f"signals:{slug}",
                        signals.model_dump(),
                    )
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("Signal computation error")
            await asyncio.sleep(0.5)

    def _compute_signals(self, market: MarketInfo) -> SignalSet:
        asset = market.asset.value
        dfm = data_feed_manager
        st = self._state(asset)

        # Current prices
        binance_px = dfm.binance_prices.get(asset, 0.0)
        chainlink_px = dfm.chainlink_prices.get(asset, 0.0)
        # If RTDS unavailable, approximate with Binance
        if not chainlink_px:
            chainlink_px = binance_px

        strike = market.price_to_beat

        # Update candle with latest Binance price
        if binance_px:
            st.update_candle(binance_px)

        # Update open interest tracking
        oi = dfm.open_interest.get(asset, 0.0)
        oi_change = st.update_oi(oi) if oi else None

        # ── Tier 1 — Core ────────────────────────────────────────────
        price_vs_strike_pct = ((chainlink_px - strike) / strike * 100.0) if strike != 0 else 0.0
        momentum_5s = dfm.get_price_momentum(asset, 5)
        momentum_15s = dfm.get_price_momentum(asset, 15)
        momentum_30s = dfm.get_price_momentum(asset, 30)
        exchange_lead = binance_px - chainlink_px if binance_px and chainlink_px else 0.0
        time_remaining = max(0, market.end_time - int(time.time()))

        # Implied probability from CLOB YES price
        yes_id = market.clob_token_ids.yes_id
        implied_prob = dfm.yes_prices.get(yes_id, 0.5)

        # Net order flow
        net_flow = dfm.get_net_order_flow(yes_id, 30)

        # ── Tier 2 — Confirmation ────────────────────────────────────
        rsi = st.compute_rsi(14)
        ema_cross = st.ema_crossover()
        vwap_dev = st.vwap_deviation(binance_px) if binance_px else 0.0
        vol = st.volatility_60s()

        # ── Tier 3 — Edge Amplifiers ─────────────────────────────────
        funding = dfm.funding_rates.get(asset)

        # Multi-exchange consensus: do both Binance and Chainlink agree on direction?
        binance_side = 1 if binance_px > strike else (-1 if binance_px < strike else 0)
        chainlink_side = 1 if chainlink_px > strike else (-1 if chainlink_px < strike else 0)
        consensus = 1.0 if binance_side == chainlink_side and binance_side != 0 else 0.0

        return SignalSet(
            market_id=market.slug,
            timestamp=timestamp_ms(),
            price_vs_strike_pct=round(price_vs_strike_pct, 4),
            momentum_5s=round(momentum_5s, 4),
            momentum_15s=round(momentum_15s, 4),
            momentum_30s=round(momentum_30s, 4),
            exchange_lead=round(exchange_lead, 4),
            time_remaining=time_remaining,
            implied_probability=max(0.0, min(1.0, implied_prob)),
            net_order_flow_30s=round(net_flow, 4),
            rsi_14=round(rsi, 2) if rsi is not None else None,
            ema_crossover=round(ema_cross, 4),
            vwap_deviation=round(vwap_dev, 4),
            volatility_60s=round(vol, 4),
            funding_rate=funding,
            open_interest_change=round(oi_change, 4) if oi_change is not None else None,
            multi_exchange_consensus=consensus,
        )


# Module-level singleton
signal_engine = SignalEngine()
