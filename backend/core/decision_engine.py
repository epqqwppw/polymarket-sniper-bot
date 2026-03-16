"""Decision engine — confidence scoring and trade action recommendations."""

from typing import List

from backend.config import MIN_CONFIDENCE, MIN_SELL_PRICE
from backend.models.market import Duration, MarketInfo
from backend.models.signal import SignalSet
from backend.models.trade import Decision, RiskLevel, TradeAction
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# Decision deadlines (seconds remaining)
_DEADLINE_5MIN = 90
_DEADLINE_15MIN = 180

# Volatility threshold for "choppy market" merge condition
_VOLATILITY_THRESHOLD = 50.0


def evaluate_market(signals: SignalSet, market: MarketInfo) -> Decision:
    """Evaluate signals for a market and return a trade decision.

    Returns a Decision with action, confidence, reasoning, recommended
    sell price, and risk level.
    """
    reasoning: List[str] = []
    time_rem = signals.time_remaining

    # ── 1. WAIT Phase ────────────────────────────────────────────────────
    deadline = _DEADLINE_5MIN if market.duration == Duration.FIVE_MIN else _DEADLINE_15MIN
    if time_rem > deadline:
        reasoning.append(
            f"Waiting — {time_rem}s remaining (decision at ≤{deadline}s)"
        )
        return Decision(
            action=TradeAction.WAIT,
            confidence=0,
            reasoning=reasoning,
            recommended_sell_price=None,
            risk_level=RiskLevel.LOW,
        )

    # ── 2. Determine direction and build confidence ──────────────────────
    distance_pct = signals.price_vs_strike_pct
    direction = "UP" if distance_pct >= 0 else "DOWN"
    confidence = 0

    # Distance from strike
    abs_dist = abs(distance_pct)
    if abs_dist > 0.15:
        confidence += 3
        reasoning.append(f"Price is {distance_pct:+.3f}% from strike — strong signal")
    elif abs_dist > 0.08:
        confidence += 2
        reasoning.append(f"Price is {distance_pct:+.3f}% from strike — moderate signal")
    elif abs_dist > 0.04:
        confidence += 1
        reasoning.append(f"Price is {distance_pct:+.3f}% from strike — weak signal")
    else:
        reasoning.append(f"Price is very close to strike ({distance_pct:+.3f}%)")

    # Momentum confirmation (both 5s and 30s agree on direction)
    mom_5s_confirms = (signals.momentum_5s > 0 and direction == "UP") or (
        signals.momentum_5s < 0 and direction == "DOWN"
    )
    mom_30s_confirms = (signals.momentum_30s > 0 and direction == "UP") or (
        signals.momentum_30s < 0 and direction == "DOWN"
    )
    if mom_5s_confirms and mom_30s_confirms:
        confidence += 2
        reasoning.append(
            f"Both 5s and 30s momentum confirm {direction} direction "
            f"(5s={signals.momentum_5s:+.2f}, 30s={signals.momentum_30s:+.2f})"
        )
    elif mom_5s_confirms or mom_30s_confirms:
        confidence += 1
        reasoning.append("Partial momentum confirmation")

    # Exchange lead confirms direction
    if (signals.exchange_lead > 0 and direction == "UP") or (
        signals.exchange_lead < 0 and direction == "DOWN"
    ):
        confidence += 1
        reasoning.append(
            f"Exchange lead confirms {direction} ({signals.exchange_lead:+.2f})"
        )

    # Polymarket implied probability alignment
    impl_prob = signals.implied_probability
    if (impl_prob > 0.65 and direction == "UP") or (impl_prob < 0.35 and direction == "DOWN"):
        confidence += 1
        reasoning.append(
            f"Polymarket implied probability aligns ({impl_prob:.0%})"
        )

    # Time bonus (closer to end = more reliable)
    if time_rem < 60:
        confidence += 2
        reasoning.append(f"Very close to close ({time_rem}s) — high reliability")
    elif time_rem < 120:
        confidence += 1
        reasoning.append(f"Approaching close ({time_rem}s) — moderate reliability")

    # RSI confirmation
    if signals.rsi_14 is not None:
        if signals.rsi_14 > 70 and direction == "UP":
            confidence += 1
            reasoning.append(f"RSI confirms overbought/UP ({signals.rsi_14:.1f})")
        elif signals.rsi_14 < 30 and direction == "DOWN":
            confidence += 1
            reasoning.append(f"RSI confirms oversold/DOWN ({signals.rsi_14:.1f})")

    # Multi-exchange consensus
    if signals.multi_exchange_consensus >= 1.0:
        confidence += 1
        reasoning.append("All price sources agree on direction ✅")

    # Cap confidence at 10
    confidence = min(confidence, 10)

    # ── 3. Estimate sell price ───────────────────────────────────────────
    # If price is ABOVE strike → YES wins → sell NO tokens at ~(1 - implied_prob)
    # If price is BELOW strike → NO wins  → sell YES tokens at ~implied_prob
    if direction == "UP":
        sell_price = max(0.01, 1.0 - impl_prob)  # sell NO tokens (losing side)
    else:
        sell_price = max(0.01, impl_prob)  # sell YES tokens (losing side)

    # ── 4. MERGE Conditions ──────────────────────────────────────────────
    merge_reason = _check_merge_conditions(signals, confidence, sell_price)
    if merge_reason:
        reasoning.append(f"MERGE: {merge_reason}")
        return Decision(
            action=TradeAction.MERGE,
            confidence=confidence,
            reasoning=reasoning,
            recommended_sell_price=sell_price,
            risk_level=RiskLevel.HIGH,
        )

    # ── 5. SELL Decision ─────────────────────────────────────────────────
    if confidence < MIN_CONFIDENCE:
        reasoning.append(
            f"Confidence {confidence}/10 below minimum {MIN_CONFIDENCE} — merge"
        )
        return Decision(
            action=TradeAction.MERGE,
            confidence=confidence,
            reasoning=reasoning,
            recommended_sell_price=sell_price,
            risk_level=RiskLevel.HIGH,
        )

    action = TradeAction.SELL_NO if direction == "UP" else TradeAction.SELL_YES
    risk = _assess_risk(confidence, abs_dist, signals.volatility_60s)
    reasoning.append(
        f"Recommendation: {action.value} at ~${sell_price:.2f} "
        f"(confidence {confidence}/10, risk {risk.value})"
    )

    return Decision(
        action=action,
        confidence=confidence,
        reasoning=reasoning,
        recommended_sell_price=sell_price,
        risk_level=risk,
    )


def _check_merge_conditions(
    signals: SignalSet, confidence: int, sell_price: float
) -> str:
    """Return a merge-reason string if any MERGE condition is met, else empty."""
    abs_dist = abs(signals.price_vs_strike_pct)

    # Too close to strike near end
    if abs_dist < 0.03 and signals.time_remaining < 120:
        return "Price too close to strike (<0.03%) with <120s remaining — coin flip"

    # Choppy market
    if signals.volatility_60s > _VOLATILITY_THRESHOLD and abs_dist < 0.08:
        return (
            f"High volatility ({signals.volatility_60s:.1f}) with small distance "
            f"({abs_dist:.3f}%) — choppy market"
        )

    # Sell price too low
    if sell_price < MIN_SELL_PRICE:
        return f"Estimated sell price ${sell_price:.2f} below minimum ${MIN_SELL_PRICE}"

    return ""


def _assess_risk(confidence: int, abs_distance_pct: float, volatility: float) -> RiskLevel:
    """Map confidence, distance, and volatility to a risk level."""
    if confidence >= 8 and abs_distance_pct > 0.15:
        return RiskLevel.LOW
    if confidence >= 6:
        return RiskLevel.MEDIUM
    if confidence >= 4:
        return RiskLevel.HIGH
    return RiskLevel.EXTREME
