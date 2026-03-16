"""Pydantic models for Polymarket market data."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Asset(str, Enum):
    BTC = "BTC"
    ETH = "ETH"
    SOL = "SOL"


class Duration(int, Enum):
    FIVE_MIN = 300
    FIFTEEN_MIN = 900


class MarketStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    CLOSED = "closed"
    RESOLVED = "resolved"


class ClobTokenIds(BaseModel):
    model_config = {"frozen": True}

    yes_id: str
    no_id: str


class MarketInfo(BaseModel):
    model_config = {"frozen": True}

    slug: str
    asset: Asset
    duration: Duration
    condition_id: str
    clob_token_ids: ClobTokenIds
    question: str
    price_to_beat: float
    start_time: int
    end_time: int
    status: MarketStatus = MarketStatus.PENDING


class MarketState(BaseModel):
    market_info: MarketInfo
    yes_price: float = Field(default=0.0, ge=0.0, le=1.0)
    no_price: float = Field(default=0.0, ge=0.0, le=1.0)
    chainlink_price: Optional[float] = None
    binance_price: Optional[float] = None
    time_remaining: int = 0
    is_active: bool = False
