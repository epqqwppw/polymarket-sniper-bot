"""Pydantic models for trading signals."""

from typing import Optional

from pydantic import BaseModel, Field


class SignalSet(BaseModel):
    market_id: str
    timestamp: int

    # Core price signals
    price_vs_strike_pct: float = 0.0
    momentum_5s: float = 0.0
    momentum_15s: float = 0.0
    momentum_30s: float = 0.0
    exchange_lead: float = 0.0
    time_remaining: int = 0
    implied_probability: float = Field(default=0.0, ge=0.0, le=1.0)

    # Order-flow signals
    net_order_flow_30s: float = 0.0

    # Technical indicators
    rsi_14: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    ema_crossover: float = 0.0
    vwap_deviation: float = 0.0

    # Volatility / derivatives signals
    volatility_60s: float = 0.0
    funding_rate: Optional[float] = None
    open_interest_change: Optional[float] = None

    # Consensus
    multi_exchange_consensus: float = 0.0
