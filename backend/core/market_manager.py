"""Market manager — lifecycle orchestrator with automatic market rolling."""

import asyncio
import time
from typing import Dict, Optional, Set

from backend.core.data_feeds import data_feed_manager
from backend.core.decision_engine import evaluate_market
from backend.core.execution_engine import execution_engine
from backend.core.market_discovery import market_discovery
from backend.core.money_manager import money_manager
from backend.core.redis_manager import redis_manager
from backend.core.signal_engine import signal_engine
from backend.models.market import Duration, MarketInfo
from backend.models.trade import TradeAction
from backend.utils.helpers import timestamp_ms
from backend.utils.logger import get_logger

logger = get_logger(__name__)


class MarketManager:
    """Orchestrates the full lifecycle of market tracking and trading."""

    def __init__(self) -> None:
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._discovery_task: Optional[asyncio.Task] = None

        # Markets currently being tracked (slug → MarketInfo)
        self._tracked: Dict[str, MarketInfo] = {}

        # Markets that have already been split into (slug set)
        self._split_markets: Set[str] = set()

        # Markets where a decision has been made (slug → action taken)
        self._decided: Dict[str, TradeAction] = {}

        # Pre-fetched next-market slugs
        self._prefetched: Set[str] = set()

    @property
    def tracked_markets(self) -> Dict[str, MarketInfo]:
        return dict(self._tracked)

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the market manager loop."""
        self._running = True
        self._task = asyncio.create_task(self._main_loop(), name="market_manager")
        self._discovery_task = asyncio.create_task(
            self._discovery_loop(), name="market_discovery"
        )
        logger.info("MarketManager started")

    async def stop(self) -> None:
        """Stop the market manager loop."""
        self._running = False
        for t in [self._task, self._discovery_task]:
            if t:
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass
        logger.info("MarketManager stopped")

    # ── Discovery Loop (every 10 seconds) ────────────────────────────────

    async def _discovery_loop(self) -> None:
        """Periodically discover new markets."""
        while self._running:
            try:
                markets = await market_discovery.discover()
                for mi in markets:
                    if mi.slug not in self._tracked:
                        await self._start_tracking(mi)

                # Pre-fetch next markets for seamless transitions
                await self._prefetch_next_markets()

                # Clean up expired markets
                expired = market_discovery.remove_expired()
                for slug in expired:
                    if slug in self._tracked and slug not in self._decided:
                        await self._handle_market_close(slug)

            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("Discovery loop error")
            await asyncio.sleep(10)

    # ── Main Processing Loop (every 500ms) ───────────────────────────────

    async def _main_loop(self) -> None:
        """Core loop: check each tracked market and make decisions."""
        while self._running:
            try:
                now = int(time.time())

                for slug, market in list(self._tracked.items()):
                    time_remaining = max(0, market.end_time - now)

                    # Market has closed
                    if time_remaining == 0:
                        await self._handle_market_close(slug)
                        continue

                    # Pre-fetch next market when close to ending
                    if time_remaining <= 15 and slug not in self._prefetched:
                        self._prefetched.add(slug)
                        logger.info("Pre-fetching next market for %s", slug)

                    # Skip if already decided
                    if slug in self._decided:
                        continue

                    # Get latest signals
                    signals = signal_engine.latest_signals.get(slug)
                    if signals is None:
                        continue

                    # Run decision engine
                    decision = evaluate_market(signals, market)

                    # Publish decision to Redis for UI
                    await redis_manager.publish(
                        f"decision:{slug}",
                        decision.model_dump(),
                    )

                    # Act on decision
                    if decision.action == TradeAction.WAIT:
                        continue

                    elif decision.action == TradeAction.MERGE:
                        if slug in self._split_markets:
                            split_size = money_manager.get_split_size(market.duration)
                            await execution_engine.merge(market, split_size)
                        self._decided[slug] = TradeAction.MERGE
                        logger.info(
                            "MERGE decision for %s (confidence=%d)",
                            slug, decision.confidence,
                        )

                    elif decision.action in (TradeAction.SELL_YES, TradeAction.SELL_NO):
                        side = "YES" if decision.action == TradeAction.SELL_YES else "NO"
                        sell_price = decision.recommended_sell_price or 0.5
                        split_size = money_manager.get_split_size(market.duration)
                        size = money_manager.calculate_position_size(
                            decision.confidence, sell_price
                        )
                        size = min(size, split_size)  # can't sell more than we split

                        await execution_engine.sell(market, side, size, sell_price)
                        self._decided[slug] = decision.action
                        logger.info(
                            "SELL %s decision for %s — %d tokens @ $%.2f (confidence=%d)",
                            side, slug, size, sell_price, decision.confidence,
                        )

                # Persist bankroll state
                await money_manager.persist()

            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("Main loop error")
            await asyncio.sleep(0.5)

    # ── Market Tracking ──────────────────────────────────────────────────

    async def _start_tracking(self, market: MarketInfo) -> None:
        """Begin tracking a newly discovered market."""
        slug = market.slug
        self._tracked[slug] = market

        # Subscribe to CLOB data for this market's tokens
        data_feed_manager.subscribe_market_tokens(
            market.clob_token_ids.yes_id,
            market.clob_token_ids.no_id,
        )

        # Register with signal engine
        signal_engine.track_market(market)

        # Simulate split if capital available
        split_size = money_manager.get_split_size(market.duration)
        if money_manager.can_open_position(split_size):
            result = await execution_engine.split(market, split_size)
            if result.success:
                self._split_markets.add(slug)

        logger.info(
            "Now tracking market: %s (%s %s, strike=$%.2f, ends=%d)",
            slug, market.asset.value,
            "5m" if market.duration == Duration.FIVE_MIN else "15m",
            market.price_to_beat, market.end_time,
        )

    async def _handle_market_close(self, slug: str) -> None:
        """Handle a market that has closed / expired."""
        market = self._tracked.get(slug)
        if not market:
            return

        action_taken = self._decided.get(slug)

        # If we split but didn't sell or merge, we need to handle it
        if slug in self._split_markets and action_taken is None:
            # Merge by default if no decision was made
            split_size = money_manager.get_split_size(market.duration)
            await execution_engine.merge(market, split_size)
            logger.info("Auto-merged undecided market %s on close", slug)

        # Clean up
        signal_engine.untrack_market(slug)
        self._tracked.pop(slug, None)
        self._split_markets.discard(slug)
        self._decided.pop(slug, None)
        self._prefetched.discard(slug)

        logger.info("Market %s closed and removed from tracking", slug)

    async def _prefetch_next_markets(self) -> None:
        """Pre-fetch next interval markets for seamless transitions."""
        ending_soon = market_discovery.get_markets_ending_soon(within_secs=15)
        if ending_soon:
            # Trigger a discovery cycle which includes next slugs
            logger.debug(
                "Markets ending soon: %s — next slugs already computed",
                [m.slug for m in ending_soon],
            )


# Module-level singleton
market_manager = MarketManager()
