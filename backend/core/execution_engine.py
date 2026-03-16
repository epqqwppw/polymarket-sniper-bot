"""Execution engine — simulated (DRY RUN) trade execution.

ALL trade execution is in DRY-RUN / SIMULATION mode by default.
The bot logs what it WOULD do but does NOT place real orders.
Real execution code is included but disabled behind the DRY_RUN flag.
"""

from dataclasses import dataclass
from typing import Optional

from backend.config import DRY_RUN
from backend.core.money_manager import money_manager
from backend.core.redis_manager import redis_manager
from backend.models.market import Duration, MarketInfo
from backend.models.trade import SimulatedTrade, TradeAction
from backend.utils.helpers import timestamp_ms
from backend.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SplitResult:
    success: bool
    amount: float
    yes_tokens: float
    no_tokens: float
    message: str


@dataclass
class SellResult:
    success: bool
    side: str
    size: float
    price: float
    revenue: float
    message: str


@dataclass
class MergeResult:
    success: bool
    amount: float
    returned: float
    message: str


@dataclass
class RedeemResult:
    success: bool
    side: str
    amount: float
    payout: float
    message: str


class ExecutionEngine:
    """Handles trade execution in simulation (DRY_RUN) or live mode."""

    async def split(self, market: MarketInfo, amount: float) -> SplitResult:
        """Split USDC into YES + NO token pairs.

        In a real scenario this calls ConditionalTokens.splitPosition()
        on the Polygon network.
        """
        if DRY_RUN:
            if not money_manager.can_open_position(amount):
                return SplitResult(
                    success=False,
                    amount=amount,
                    yes_tokens=0,
                    no_tokens=0,
                    message="Cannot open position — guard check failed",
                )

            money_manager.record_split(amount)
            msg = (
                f"[DRY RUN] SPLIT ${amount} into {amount} YES + {amount} NO "
                f"for market {market.slug}"
            )
            logger.info(msg)
            return SplitResult(
                success=True,
                amount=amount,
                yes_tokens=amount,
                no_tokens=amount,
                message=msg,
            )

        # ── REAL EXECUTION (future) ──────────────────────────────────────
        # from py_clob_client.client import ClobClient
        # client = ClobClient(host, key=POLYMARKET_API_KEY, ...)
        # Approve USDC spending for ConditionalTokens contract
        # tx = conditional_tokens.splitPosition(
        #     collateralToken=USDC_ADDRESS,
        #     parentCollectionId=bytes32(0),
        #     conditionId=market.condition_id,
        #     partition=[1, 2],  # YES=1, NO=2
        #     amount=int(amount * 1e6),  # USDC has 6 decimals
        # )
        # await wait_for_tx(tx)
        raise NotImplementedError("Real execution is not enabled")

    async def sell(
        self,
        market: MarketInfo,
        side: str,
        size: float,
        price: float,
    ) -> SellResult:
        """Sell tokens on the Polymarket CLOB.

        side: "YES" or "NO"
        size: number of tokens to sell
        price: limit price (0-1)
        """
        if DRY_RUN:
            revenue = size * price
            msg = (
                f"[DRY RUN] SELL {size} {side} tokens at ${price:.4f} "
                f"for market {market.slug} → revenue ${revenue:.2f}"
            )
            logger.info(msg)

            trade = SimulatedTrade(
                timestamp=timestamp_ms(),
                market_id=market.slug,
                asset=market.asset.value,
                duration=market.duration.value,
                action=TradeAction.SELL_YES if side == "YES" else TradeAction.SELL_NO,
                side=side,
                size=size,
                price=price,
                revenue=revenue,
                pnl=0.0,  # will be computed by money_manager
                gas_estimate=0.02,
            )
            money_manager.record_sell(trade)
            await redis_manager.log_trade(trade.model_dump())
            return SellResult(
                success=True,
                side=side,
                size=size,
                price=price,
                revenue=revenue,
                message=msg,
            )

        # ── REAL EXECUTION (future) ──────────────────────────────────────
        # from py_clob_client.client import ClobClient
        # from py_clob_client.order_builder.constants import BUY, SELL
        # client = ClobClient(host, key=POLYMARKET_API_KEY, ...)
        # token_id = market.clob_token_ids.yes_id if side == "YES"
        #            else market.clob_token_ids.no_id
        # order = client.create_order(
        #     OrderArgs(
        #         token_id=token_id,
        #         price=price,
        #         size=size,
        #         side=SELL,
        #     )
        # )
        # resp = client.post_order(order)
        raise NotImplementedError("Real execution is not enabled")

    async def merge(self, market: MarketInfo, amount: float) -> MergeResult:
        """Merge YES + NO tokens back into USDC (skip/cancel a market).

        Returns the original capital minus gas.
        """
        if DRY_RUN:
            money_manager.record_merge(amount)
            msg = (
                f"[DRY RUN] MERGE {amount} YES + {amount} NO back to ${amount} "
                f"for market {market.slug}"
            )
            logger.info(msg)
            return MergeResult(
                success=True,
                amount=amount,
                returned=amount,
                message=msg,
            )

        # ── REAL EXECUTION (future) ──────────────────────────────────────
        # tx = conditional_tokens.mergePositions(
        #     collateralToken=USDC_ADDRESS,
        #     parentCollectionId=bytes32(0),
        #     conditionId=market.condition_id,
        #     partition=[1, 2],
        #     amount=int(amount * 1e6),
        # )
        # await wait_for_tx(tx)
        raise NotImplementedError("Real execution is not enabled")

    async def redeem(
        self, market: MarketInfo, side: str, amount: float
    ) -> RedeemResult:
        """Redeem winning tokens after market resolution.

        Winning tokens are worth $1.00 each.
        """
        if DRY_RUN:
            money_manager.record_redeem(amount, side)
            msg = (
                f"[DRY RUN] REDEEM {amount} winning {side} tokens = ${amount} "
                f"for market {market.slug}"
            )
            logger.info(msg)
            return RedeemResult(
                success=True,
                side=side,
                amount=amount,
                payout=amount,
                message=msg,
            )

        # ── REAL EXECUTION (future) ──────────────────────────────────────
        # tx = conditional_tokens.redeemPositions(
        #     collateralToken=USDC_ADDRESS,
        #     parentCollectionId=bytes32(0),
        #     conditionId=market.condition_id,
        #     indexSets=[1, 2],
        # )
        # await wait_for_tx(tx)
        raise NotImplementedError("Real execution is not enabled")


# Module-level singleton
execution_engine = ExecutionEngine()
