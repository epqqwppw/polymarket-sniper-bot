"""FastAPI application entry point for the Polymarket Sniper Bot."""

import asyncio
from contextlib import asynccontextmanager

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import router as api_router
from backend.api.websocket_handler import broadcaster, sio
from backend.config import LOG_LEVEL
from backend.core.data_feeds import data_feed_manager
from backend.core.market_discovery import market_discovery
from backend.core.market_manager import market_manager
from backend.core.redis_manager import redis_manager
from backend.core.signal_engine import signal_engine
from backend.utils.logger import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown of all services."""
    logger.info("Starting Polymarket Sniper Bot …")
    try:
        # 1. Connect Redis
        await redis_manager.connect()

        # 2. Start data feeds (Binance WS, Polymarket CLOB/RTDS, etc.)
        await data_feed_manager.start()

        # 3. Start market discovery
        await market_discovery.start()

        # 4. Start signal engine
        await signal_engine.start()

        # 5. Start market manager (orchestrator)
        await market_manager.start()

        # 6. Start WebSocket broadcaster
        await broadcaster.start()

        logger.info("All services started successfully ✅")
    except Exception:
        logger.exception("Failed to start services")
        raise

    yield  # Application is running

    # Shutdown
    logger.info("Shutting down Polymarket Sniper Bot …")
    await broadcaster.stop()
    await market_manager.stop()
    await signal_engine.stop()
    await data_feed_manager.stop()
    await market_discovery.stop()
    await redis_manager.disconnect()
    logger.info("Shutdown complete 🛑")


# Create FastAPI app
app = FastAPI(
    title="Polymarket Sniper Bot",
    description="Real-time Polymarket crypto prediction market analysis and simulated trading bot",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include REST API routes
app.include_router(api_router)

# Wrap FastAPI with Socket.IO ASGI app
socket_app = socketio.ASGIApp(sio, other_app=app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:socket_app",
        host="0.0.0.0",
        port=8000,
        log_level=LOG_LEVEL.lower(),
        reload=False,
    )
