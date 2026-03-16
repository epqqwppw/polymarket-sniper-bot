"""Redis manager for real-time data streaming, caching, and pub/sub."""

import json
import time
from typing import Any, Dict, List, Optional

import redis.asyncio as aioredis

from backend.config import REDIS_URL
from backend.utils.logger import get_logger

logger = get_logger(__name__)

PRICE_BUFFER_MAX = 300
MARKET_CACHE_TTL = 600


class RedisManager:
    """Manages Redis connections for pub/sub, caching, and data streaming."""

    def __init__(self) -> None:
        self._redis: Optional[aioredis.Redis] = None
        self._pubsub: Optional[aioredis.client.PubSub] = None

    async def connect(self) -> None:
        """Establish Redis connection."""
        try:
            self._redis = aioredis.from_url(
                REDIS_URL,
                decode_responses=True,
                max_connections=20,
            )
            await self._redis.ping()
            logger.info("Redis connected successfully to %s", REDIS_URL)
        except Exception:
            logger.exception("Failed to connect to Redis")
            raise

    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self._pubsub:
            await self._pubsub.close()
        if self._redis:
            await self._redis.close()
            logger.info("Redis disconnected")

    @property
    def client(self) -> aioredis.Redis:
        if self._redis is None:
            raise RuntimeError("Redis is not connected. Call connect() first.")
        return self._redis

    # ── Pub/Sub ──────────────────────────────────────────────────────────

    async def publish(self, channel: str, data: Any) -> None:
        """Publish JSON-serialized data to a Redis channel."""
        try:
            payload = json.dumps(data) if not isinstance(data, str) else data
            await self.client.publish(channel, payload)
        except Exception:
            logger.exception("Redis publish error on channel %s", channel)

    async def subscribe(self, *channels: str) -> aioredis.client.PubSub:
        """Subscribe to one or more channels and return the PubSub object."""
        self._pubsub = self.client.pubsub()
        await self._pubsub.subscribe(*channels)
        logger.info("Subscribed to Redis channels: %s", channels)
        return self._pubsub

    # ── Price Buffer ─────────────────────────────────────────────────────

    async def push_price_tick(self, asset: str, price: float, ts_ms: int) -> None:
        """Push a price tick to the rolling buffer (FIFO, max 300 entries)."""
        key = f"prices:buffer:{asset}"
        entry = json.dumps({"price": price, "ts": ts_ms})
        pipe = self.client.pipeline()
        pipe.rpush(key, entry)
        pipe.ltrim(key, -PRICE_BUFFER_MAX, -1)
        await pipe.execute()

    async def get_price_buffer(self, asset: str, count: int = PRICE_BUFFER_MAX) -> List[Dict]:
        """Retrieve the last *count* price ticks for an asset."""
        key = f"prices:buffer:{asset}"
        raw = await self.client.lrange(key, -count, -1)
        return [json.loads(r) for r in raw]

    # ── Market Cache ─────────────────────────────────────────────────────

    async def cache_market(self, slug: str, data: Dict) -> None:
        """Cache market details with a TTL."""
        key = f"market:active:{slug}"
        await self.client.set(key, json.dumps(data), ex=MARKET_CACHE_TTL)

    async def get_cached_market(self, slug: str) -> Optional[Dict]:
        """Retrieve cached market details."""
        key = f"market:active:{slug}"
        raw = await self.client.get(key)
        return json.loads(raw) if raw else None

    # ── Bankroll ─────────────────────────────────────────────────────────

    async def save_bankroll(self, state: Dict) -> None:
        """Persist the current bankroll state."""
        await self.client.set("bankroll", json.dumps(state))

    async def get_bankroll(self) -> Optional[Dict]:
        """Retrieve the bankroll state."""
        raw = await self.client.get("bankroll")
        return json.loads(raw) if raw else None

    # ── Trade Log ────────────────────────────────────────────────────────

    async def log_trade(self, trade: Dict) -> None:
        """Append a simulated trade to the log."""
        await self.client.rpush("trades:log", json.dumps(trade))

    async def get_trade_log(self, limit: int = 50) -> List[Dict]:
        """Retrieve the last *limit* simulated trades (most recent first)."""
        raw = await self.client.lrange("trades:log", -limit, -1)
        return [json.loads(r) for r in reversed(raw)]

    # ── Rate Limiting ────────────────────────────────────────────────────

    async def check_rate_limit(self, key: str, max_calls: int, window_secs: int) -> bool:
        """Return True if the action is allowed, False if rate-limited."""
        now = int(time.time())
        rl_key = f"ratelimit:{key}"
        pipe = self.client.pipeline()
        pipe.zadd(rl_key, {str(now): now})
        pipe.zremrangebyscore(rl_key, 0, now - window_secs)
        pipe.zcard(rl_key)
        pipe.expire(rl_key, window_secs)
        results = await pipe.execute()
        count = results[2]
        return count <= max_calls

    # ── Generic helpers ──────────────────────────────────────────────────

    async def set_json(self, key: str, data: Any, ttl: Optional[int] = None) -> None:
        """Set a JSON value with optional TTL."""
        payload = json.dumps(data)
        if ttl:
            await self.client.set(key, payload, ex=ttl)
        else:
            await self.client.set(key, payload)

    async def get_json(self, key: str) -> Optional[Any]:
        """Get a JSON value."""
        raw = await self.client.get(key)
        return json.loads(raw) if raw else None


# Module-level singleton
redis_manager = RedisManager()
