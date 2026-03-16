"""Socket.IO server for real-time dashboard updates."""

import asyncio
from typing import Optional

import socketio

from backend.core.data_feeds import data_feed_manager
from backend.core.market_manager import market_manager
from backend.core.money_manager import money_manager
from backend.core.signal_engine import signal_engine
from backend.utils.helpers import timestamp_ms
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# Create a Socket.IO async server
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
    logger=False,
    engineio_logger=False,
)


@sio.event
async def connect(sid, environ):
    logger.info("Client connected: %s", sid)
    # Send initial state on connect
    await _emit_full_state(sid)


@sio.event
async def disconnect(sid):
    logger.info("Client disconnected: %s", sid)


@sio.on("start_analysis")
async def handle_start(sid):
    """Client requests to start/resume analysis."""
    logger.info("Client %s requested start", sid)
    await sio.emit("status", {"running": True}, room=sid)


@sio.on("pause_analysis")
async def handle_pause(sid):
    """Client requests to pause analysis."""
    logger.info("Client %s requested pause", sid)
    await sio.emit("status", {"running": False}, room=sid)


async def _emit_full_state(sid: Optional[str] = None):
    """Emit the full dashboard state to a specific client or all clients."""
    target = {"room": sid} if sid else {}

    # Bankroll
    bankroll = money_manager.get_state().model_dump()
    await sio.emit("bankroll", bankroll, **target)

    # Markets and signals
    for slug, mi in market_manager.tracked_markets.items():
        asset = mi.asset.value
        signals = signal_engine.latest_signals.get(slug)
        market_data = {
            "slug": slug,
            "asset": mi.asset.value,
            "duration": mi.duration.value,
            "question": mi.question,
            "price_to_beat": mi.price_to_beat,
            "start_time": mi.start_time,
            "end_time": mi.end_time,
            "binance_price": data_feed_manager.binance_prices.get(asset),
            "chainlink_price": data_feed_manager.chainlink_prices.get(asset),
            "yes_price": data_feed_manager.yes_prices.get(mi.clob_token_ids.yes_id, 0.5),
            "no_price": 1.0 - data_feed_manager.yes_prices.get(mi.clob_token_ids.yes_id, 0.5),
            "signals": signals.model_dump() if signals else None,
        }
        await sio.emit("market_update", market_data, **target)

    # Connection status
    await sio.emit(
        "connection_status",
        {
            "binance_ws": data_feed_manager.binance_ws_healthy,
            "rtds": data_feed_manager.rtds_healthy,
            "redis": True,
        },
        **target,
    )


class SocketBroadcaster:
    """Background task that pushes updates to all connected clients every 500ms."""

    def __init__(self) -> None:
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._broadcast_loop(), name="ws_broadcaster")
        logger.info("SocketBroadcaster started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("SocketBroadcaster stopped")

    async def _broadcast_loop(self) -> None:
        while self._running:
            try:
                await _emit_full_state()
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("Broadcast error")
            await asyncio.sleep(0.5)


# Module-level singleton
broadcaster = SocketBroadcaster()
