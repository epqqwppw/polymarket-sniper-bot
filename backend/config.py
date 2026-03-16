"""Configuration module for the Polymarket Sniper Bot."""

import os
from dotenv import load_dotenv

load_dotenv()


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _env_float(key: str, default: float = 0.0) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int(key: str, default: int = 0) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


def _env_bool(key: str, default: bool = False) -> bool:
    return os.getenv(key, str(default)).lower() in ("true", "1", "yes")


# ── General ──────────────────────────────────────────────────────────────────
DRY_RUN: bool = _env_bool("DRY_RUN", True)
LOG_LEVEL: str = _env("LOG_LEVEL", "INFO")
INITIAL_BANKROLL: float = _env_float("INITIAL_BANKROLL", 100.0)

# ── Redis ────────────────────────────────────────────────────────────────────
REDIS_URL: str = _env("REDIS_URL", "redis://localhost:6379/0")

# ── Polymarket URLs ──────────────────────────────────────────────────────────
POLYMARKET_CLOB_API: str = _env(
    "POLYMARKET_CLOB_API", "https://clob.polymarket.com"
)
POLYMARKET_GAMMA_API: str = _env(
    "POLYMARKET_GAMMA_API", "https://gamma-api.polymarket.com"
)
POLYMARKET_WS_URL: str = _env(
    "POLYMARKET_WS_URL", "wss://ws-subscriptions-clob.polymarket.com/ws/market"
)
POLYMARKET_RTDS_URL: str = _env(
    "POLYMARKET_RTDS_URL", "wss://ws-live-data.polymarket.com"
)

# ── Binance URLs ─────────────────────────────────────────────────────────────
BINANCE_REST_URL: str = _env(
    "BINANCE_REST_URL", "https://api.binance.com/api/v3"
)
BINANCE_WS_URL: str = _env(
    "BINANCE_WS_URL",
    "wss://stream.binance.com:9443/stream?streams="
    "btcusdt@aggTrade/ethusdt@aggTrade/solusdt@aggTrade",
)
BINANCE_FUTURES_API: str = _env(
    "BINANCE_FUTURES_API", "https://fapi.binance.com"
)

# ── CoinGecko (fallback) ────────────────────────────────────────────────────
COINGECKO_API: str = _env(
    "COINGECKO_API", "https://api.coingecko.com/api/v3"
)

# ── Trading Parameters ───────────────────────────────────────────────────────
ACTIVE_POOL_RATIO: float = _env_float("ACTIVE_POOL_RATIO", 0.70)
RESERVE_RATIO: float = _env_float("RESERVE_RATIO", 0.30)
MAX_SIMULTANEOUS_POSITIONS: int = _env_int("MAX_SIMULTANEOUS_POSITIONS", 5)
SPLIT_SIZE_5MIN: int = _env_int("SPLIT_SIZE_5MIN", 10)
SPLIT_SIZE_15MIN: int = _env_int("SPLIT_SIZE_15MIN", 13)
MIN_SELL_PRICE: float = _env_float("MIN_SELL_PRICE", 0.15)
MIN_CONFIDENCE: int = _env_int("MIN_CONFIDENCE", 5)
MAX_LOSS_PER_HOUR: float = _env_float("MAX_LOSS_PER_HOUR", 15.00)
