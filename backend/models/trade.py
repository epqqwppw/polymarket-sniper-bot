"""Pydantic models for trade decisions and bankroll tracking."""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class TradeAction(str, Enum):
    SELL_YES = "SELL_YES"
    SELL_NO = "SELL_NO"
    MERGE = "MERGE"
    WAIT = "WAIT"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    EXTREME = "EXTREME"


class Decision(BaseModel):
    action: TradeAction
    confidence: int = Field(ge=0, le=10)
    reasoning: List[str] = Field(default_factory=list)
    recommended_sell_price: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    risk_level: RiskLevel = RiskLevel.MEDIUM


class SimulatedTrade(BaseModel):
    timestamp: int
    market_id: str
    asset: str
    duration: int
    action: TradeAction
    side: str
    size: float = Field(gt=0.0)
    price: float = Field(ge=0.0, le=1.0)
    revenue: float = 0.0
    pnl: float = 0.0
    gas_estimate: float = 0.0


class BankrollState(BaseModel):
    initial_bankroll: float
    current_bankroll: float
    active_positions: int = 0
    available_capital: float = 0.0
    total_pnl: float = 0.0
    hourly_pnl: float = 0.0
    daily_pnl: float = 0.0
    win_count: int = 0
    loss_count: int = 0
    merge_count: int = 0
    total_trades: int = 0
    win_rate: float = Field(default=0.0, ge=0.0, le=100.0)
    avg_sell_price: float = 0.0
    total_gas: float = 0.0
