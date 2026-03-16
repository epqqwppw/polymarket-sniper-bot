"""Money manager — bankroll tracking, Kelly criterion position sizing."""

import time
from typing import List, Optional

from backend.config import (
    ACTIVE_POOL_RATIO,
    INITIAL_BANKROLL,
    MAX_LOSS_PER_HOUR,
    MAX_SIMULTANEOUS_POSITIONS,
    MIN_SELL_PRICE,
    SPLIT_SIZE_5MIN,
    SPLIT_SIZE_15MIN,
)
from backend.core.redis_manager import redis_manager
from backend.models.market import Duration
from backend.models.trade import BankrollState, SimulatedTrade, TradeAction
from backend.utils.helpers import timestamp_ms
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# Simulated gas cost per on-chain action
_GAS_ESTIMATE = 0.02


class MoneyManager:
    """Tracks simulated bankroll, positions, and P&L."""

    def __init__(self) -> None:
        self.initial_bankroll: float = INITIAL_BANKROLL
        self.current_bankroll: float = INITIAL_BANKROLL
        self.active_positions: int = 0
        self._locked_capital: float = 0.0

        # Trade accounting
        self._trades: List[SimulatedTrade] = []
        self._win_count: int = 0
        self._loss_count: int = 0
        self._merge_count: int = 0
        self._total_sell_price: float = 0.0
        self._total_sells: int = 0
        self._total_gas: float = 0.0

        # Hourly / daily P&L tracking
        self._hour_start_bankroll: float = INITIAL_BANKROLL
        self._hour_start_ts: int = int(time.time())
        self._day_start_bankroll: float = INITIAL_BANKROLL
        self._day_start_ts: int = int(time.time())

    # ── State Snapshot ───────────────────────────────────────────────────

    def get_state(self) -> BankrollState:
        total_trades = self._win_count + self._loss_count
        win_rate = (self._win_count / total_trades * 100.0) if total_trades > 0 else 0.0
        avg_sell = (self._total_sell_price / self._total_sells) if self._total_sells > 0 else 0.0

        self._maybe_reset_periods()

        return BankrollState(
            initial_bankroll=self.initial_bankroll,
            current_bankroll=round(self.current_bankroll, 2),
            active_positions=self.active_positions,
            available_capital=round(self.available_capital, 2),
            total_pnl=round(self.current_bankroll - self.initial_bankroll, 2),
            hourly_pnl=round(self.current_bankroll - self._hour_start_bankroll, 2),
            daily_pnl=round(self.current_bankroll - self._day_start_bankroll, 2),
            win_count=self._win_count,
            loss_count=self._loss_count,
            merge_count=self._merge_count,
            total_trades=self._win_count + self._loss_count + self._merge_count,
            win_rate=round(win_rate, 1),
            avg_sell_price=round(avg_sell, 4),
            total_gas=round(self._total_gas, 4),
        )

    @property
    def available_capital(self) -> float:
        return max(0.0, self.current_bankroll - self._locked_capital)

    # ── Period Resets ────────────────────────────────────────────────────

    def _maybe_reset_periods(self) -> None:
        now = int(time.time())
        if now - self._hour_start_ts >= 3600:
            self._hour_start_bankroll = self.current_bankroll
            self._hour_start_ts = now
        if now - self._day_start_ts >= 86400:
            self._day_start_bankroll = self.current_bankroll
            self._day_start_ts = now

    # ── Position Sizing (Kelly Criterion) ────────────────────────────────

    def calculate_position_size(
        self, confidence: int, sell_price_estimate: float
    ) -> int:
        """Quarter-Kelly position sizing.

        Maps confidence 5-10 to win probability 0.50-0.75, computes the
        Kelly fraction, caps at 25 %, and uses quarter-Kelly for safety.
        """
        if confidence < 5 or sell_price_estimate <= 0 or sell_price_estimate >= 1:
            return 1  # minimum

        p = 0.50 + (confidence - 5) * 0.05
        q = 1.0 - p
        b = sell_price_estimate / (1.0 - sell_price_estimate)
        if b == 0:
            return 1
        kelly = (b * p - q) / b
        kelly = max(0.0, min(kelly, 0.25))

        # Quarter-Kelly
        position_size = self.current_bankroll * ACTIVE_POOL_RATIO * kelly * 0.25
        position_size = max(1, round(position_size))
        return int(position_size)

    def get_split_size(self, duration: Duration) -> int:
        """Return the standard split size for a market duration."""
        return SPLIT_SIZE_5MIN if duration == Duration.FIVE_MIN else SPLIT_SIZE_15MIN

    # ── Guard Checks ─────────────────────────────────────────────────────

    def can_open_position(self, amount: float) -> bool:
        """Check whether we can open a new position."""
        if self.active_positions >= MAX_SIMULTANEOUS_POSITIONS:
            logger.info("Max simultaneous positions reached (%d)", MAX_SIMULTANEOUS_POSITIONS)
            return False
        if amount > self.available_capital:
            logger.info("Insufficient capital: need $%.2f, have $%.2f", amount, self.available_capital)
            return False
        # Hourly loss guard
        hourly_pnl = self.current_bankroll - self._hour_start_bankroll
        if hourly_pnl <= -MAX_LOSS_PER_HOUR:
            logger.warning("Hourly loss limit reached ($%.2f)", hourly_pnl)
            return False
        return True

    # ── Trade Recording ──────────────────────────────────────────────────

    def record_split(self, amount: float) -> None:
        """Record that capital has been locked into a split."""
        self._locked_capital += amount
        self.active_positions += 1
        self._total_gas += _GAS_ESTIMATE
        self.current_bankroll -= _GAS_ESTIMATE  # gas cost
        logger.info(
            "[SIM] SPLIT $%.2f locked | positions=%d | bankroll=$%.2f",
            amount, self.active_positions, self.current_bankroll,
        )

    def record_sell(self, trade: SimulatedTrade) -> None:
        """Record a simulated sell."""
        revenue = trade.size * trade.price
        cost = trade.size  # cost basis = $1 per token (split)
        pnl = revenue - cost
        gas = _GAS_ESTIMATE

        self.current_bankroll += revenue - gas
        self._locked_capital -= trade.size
        self.active_positions = max(0, self.active_positions - 1)
        self._total_gas += gas

        if pnl > 0:
            self._win_count += 1
        else:
            self._loss_count += 1

        self._total_sell_price += trade.price
        self._total_sells += 1

        trade_with_pnl = trade.model_copy(update={"pnl": round(pnl, 4), "gas_estimate": gas, "revenue": round(revenue, 4)})
        self._trades.append(trade_with_pnl)
        logger.info(
            "[SIM] SELL %s ×%d @ $%.2f → revenue $%.2f, P&L %+.2f | bankroll=$%.2f",
            trade.side, trade.size, trade.price, revenue, pnl, self.current_bankroll,
        )

    def record_merge(self, amount: float) -> None:
        """Record a simulated merge (return capital, no P&L)."""
        gas = _GAS_ESTIMATE
        self.current_bankroll += amount - gas  # get capital back minus gas
        self._locked_capital -= amount
        self.active_positions = max(0, self.active_positions - 1)
        self._merge_count += 1
        self._total_gas += gas
        logger.info(
            "[SIM] MERGE $%.2f returned | gas=$%.4f | bankroll=$%.2f",
            amount, gas, self.current_bankroll,
        )

    def record_redeem(self, amount: float, side: str) -> None:
        """Record a simulated redeem of winning tokens."""
        gas = _GAS_ESTIMATE
        payout = amount  # winning tokens pay $1 each
        self.current_bankroll += payout - gas
        self._locked_capital = max(0.0, self._locked_capital - amount)
        self.active_positions = max(0, self.active_positions - 1)
        self._win_count += 1
        self._total_gas += gas
        logger.info(
            "[SIM] REDEEM %d winning %s tokens → $%.2f | bankroll=$%.2f",
            amount, side, payout, self.current_bankroll,
        )

    async def persist(self) -> None:
        """Save current state to Redis."""
        state = self.get_state()
        await redis_manager.save_bankroll(state.model_dump())

    def get_trade_log(self) -> List[SimulatedTrade]:
        return list(reversed(self._trades))


# Module-level singleton
money_manager = MoneyManager()
