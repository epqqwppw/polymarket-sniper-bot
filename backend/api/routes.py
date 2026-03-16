"""REST API routes for the Polymarket Sniper Bot dashboard."""

from fastapi import APIRouter

from backend.core.data_feeds import data_feed_manager
from backend.core.market_manager import market_manager
from backend.core.money_manager import money_manager
from backend.core.redis_manager import redis_manager
from backend.core.signal_engine import signal_engine

router = APIRouter(prefix="/api", tags=["bot"])


@router.get("/status")
async def get_status():
    """Overall bot status and connection health."""
    return {
        "running": market_manager._running,
        "connections": {
            "binance_ws": data_feed_manager.binance_ws_healthy,
            "rtds": data_feed_manager.rtds_healthy,
            "redis": redis_manager._redis is not None,
        },
        "tracked_markets": len(market_manager.tracked_markets),
    }


@router.get("/markets")
async def get_markets():
    """List all tracked markets with current state."""
    markets = []
    for slug, mi in market_manager.tracked_markets.items():
        asset = mi.asset.value
        signals = signal_engine.latest_signals.get(slug)
        markets.append({
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
        })
    return {"markets": markets}


@router.get("/bankroll")
async def get_bankroll():
    """Current bankroll and P&L state."""
    return money_manager.get_state().model_dump()


@router.get("/trades")
async def get_trades():
    """Simulated trade history log."""
    trades = await redis_manager.get_trade_log(limit=100)
    return {"trades": trades}


@router.get("/prices/{asset}")
async def get_price_history(asset: str, count: int = 60):
    """Recent price ticks for an asset."""
    asset = asset.upper()
    ticks = await redis_manager.get_price_buffer(asset, count)
    return {"asset": asset, "ticks": ticks}
