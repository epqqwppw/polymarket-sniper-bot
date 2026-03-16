"""General-purpose utility functions."""

import time
from typing import Any


def format_price(price: float) -> str:
    """Format a numeric value as $X,XXX.XX."""
    return f"${price:,.2f}"


def format_percentage(pct: float) -> str:
    """Format a numeric value as X.XXX%."""
    return f"{pct:.3f}%"


def timestamp_ms() -> int:
    """Return the current UTC time in milliseconds."""
    return int(time.time() * 1000)


def safe_float(val: Any, default: float = 0.0) -> float:
    """Safely parse *val* to float, returning *default* on failure."""
    try:
        return float(val)
    except (TypeError, ValueError):
        return default
