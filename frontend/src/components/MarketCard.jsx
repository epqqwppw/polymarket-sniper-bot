import React, { useState, useEffect } from "react";
import {
  formatCryptoPrice,
  formatPct,
  formatCountdown,
  formatPnL,
  colorClass,
} from "../utils/formatters";
import SignalPanel from "./SignalPanel";
import PriceChart from "./PriceChart";
import OrderFlowPanel from "./OrderFlowPanel";

/**
 * Individual market analysis card.
 * Shows price data, signals, decision, and mini chart for one market.
 */
export default function MarketCard({ market }) {
  const [timeRemaining, setTimeRemaining] = useState(0);

  // Local countdown timer (updates every second)
  useEffect(() => {
    const update = () => {
      const remaining = Math.max(
        0,
        Math.floor(market.end_time - Date.now() / 1000)
      );
      setTimeRemaining(remaining);
    };
    update();
    const id = setInterval(update, 1000);
    return () => clearInterval(id);
  }, [market.end_time]);

  const {
    slug,
    asset,
    duration,
    question,
    price_to_beat,
    binance_price,
    chainlink_price,
    yes_price,
    no_price,
    signals,
    decision: backendDecision,
  } = market;

  const durationLabel = duration === 300 ? "5-MIN" : "15-MIN";
  const chainlinkPx = chainlink_price || binance_price || 0;
  const priceDiff = chainlinkPx - price_to_beat;
  const priceDiffPct =
    price_to_beat > 0 ? (priceDiff / price_to_beat) * 100 : 0;
  const isAbove = priceDiff >= 0;

  // Decision info — use backend decision if available, otherwise infer from signals
  const decision = backendDecision
    ? formatBackendDecision(backendDecision)
    : signals
    ? inferDecisionDisplay(signals, duration)
    : null;

  // Confidence comes from backend decision or 0
  const confidence = backendDecision?.confidence ?? 0;

  // Estimated profit from the decision
  const estProfit = backendDecision?.recommended_sell_price
    ? (backendDecision.recommended_sell_price * (duration === 300 ? 10 : 13)).toFixed(2)
    : null;

  // Progress bar percentage (time elapsed)
  const totalDuration = duration;
  const elapsed = totalDuration - timeRemaining;
  const progressPct = totalDuration > 0 ? (elapsed / totalDuration) * 100 : 0;

  // Price ticks for chart
  const ticks = market.price_ticks || [];

  return (
    <div className="bg-brand-card border border-brand-border rounded-lg p-4 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold text-brand-accent">
            {asset} {durationLabel}
          </span>
          {decision && (
            <span className={`text-xs px-1.5 py-0.5 rounded ${decision.bgColor}`}>
              {decision.icon} {decision.shortLabel}
            </span>
          )}
        </div>
        <span className="text-xs text-gray-500 truncate ml-2 max-w-[120px]">{slug}</span>
      </div>

      {/* Question */}
      <p className="text-xs text-gray-400 mb-3 leading-snug">
        {question || `Will ${asset} be above/below strike?`}
      </p>

      {/* Price Data */}
      <div className="space-y-1.5 mb-3">
        <div className="flex justify-between text-sm">
          <span className="text-gray-400">Price to Beat:</span>
          <span className="font-semibold text-white">
            {formatCryptoPrice(price_to_beat)}
          </span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-gray-400">Live Chainlink:</span>
          <span className={`font-semibold ${isAbove ? "text-green-400" : "text-red-400"}`}>
            {formatCryptoPrice(chainlinkPx)} {isAbove ? "▲" : "▼"}
          </span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-gray-400">Binance:</span>
          <span className="font-semibold text-gray-200">
            {formatCryptoPrice(binance_price)}
          </span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-gray-400">Difference:</span>
          <span className={`font-semibold ${colorClass(priceDiff)}`}>
            {priceDiff >= 0 ? "+" : ""}
            {formatCryptoPrice(Math.abs(priceDiff))} ({formatPct(priceDiffPct)})
          </span>
        </div>
      </div>

      {/* Above/Below Strike Badge */}
      <div
        className={`text-center py-1.5 rounded text-sm font-bold mb-3 ${
          isAbove
            ? "bg-green-900/40 text-green-400"
            : "bg-red-900/40 text-red-400"
        }`}
      >
        {isAbove ? "🟢 ABOVE STRIKE" : "🔴 BELOW STRIKE"}
      </div>

      {/* Time Remaining */}
      <div className="mb-3">
        <div className="flex justify-between text-xs mb-1">
          <span className="text-gray-400">Time Left</span>
          <span className="font-mono text-white">
            {formatCountdown(timeRemaining)}
          </span>
        </div>
        <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-1000 ${
              progressPct > 80
                ? "bg-red-500"
                : progressPct > 50
                ? "bg-yellow-500"
                : "bg-blue-500"
            }`}
            style={{ width: `${Math.min(progressPct, 100)}%` }}
          />
        </div>
      </div>

      {/* Mini Price Chart */}
      <PriceChart ticks={ticks} strike={price_to_beat} />

      {/* Signals */}
      <div className="mt-3 pt-3 border-t border-brand-border">
        <SignalPanel signals={signals} />
      </div>

      {/* Order Flow */}
      <OrderFlowPanel signals={signals} />

      {/* Decision */}
      {decision && (
        <div className="mt-3 pt-3 border-t border-brand-border">
          <div className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1">
            Decision
          </div>
          <div className="flex items-center gap-2 mb-1">
            <span className={`text-sm font-bold ${decision.color}`}>
              {decision.icon} {decision.label}
            </span>
            <span className="text-xs text-gray-400">
              Confidence: {confidence}/10
            </span>
            {backendDecision?.risk_level && (
              <span className={`text-xs px-1 py-0.5 rounded ${
                backendDecision.risk_level === "LOW" ? "bg-green-900/40 text-green-400" :
                backendDecision.risk_level === "MEDIUM" ? "bg-yellow-900/40 text-yellow-400" :
                backendDecision.risk_level === "HIGH" ? "bg-orange-900/40 text-orange-400" :
                "bg-red-900/40 text-red-400"
              }`}>
                {backendDecision.risk_level}
              </span>
            )}
          </div>
          {decision.reasoning && decision.reasoning.length > 0 && (
            <ul className="text-xs text-gray-400 space-y-0.5 list-disc list-inside max-h-24 overflow-y-auto">
              {decision.reasoning.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          )}
          {estProfit && (
            <div className={`text-xs mt-1 ${colorClass(parseFloat(estProfit))}`}>
              Est. Profit: {formatPnL(parseFloat(estProfit))}
            </div>
          )}
        </div>
      )}

      {/* YES/NO Prices */}
      <div className="mt-3 pt-3 border-t border-brand-border flex justify-between text-xs">
        <span className="text-gray-500">
          YES: <span className="text-green-400">${(yes_price || 0.5).toFixed(2)}</span>
        </span>
        <span className="text-gray-500">
          NO: <span className="text-red-400">${(no_price || 0.5).toFixed(2)}</span>
        </span>
      </div>
    </div>
  );
}

/**
 * Format a backend Decision object into display data for the UI.
 */
function formatBackendDecision(decision) {
  const action = decision.action;
  const reasoning = decision.reasoning || [];

  if (action === "WAIT") {
    return {
      icon: "⏳",
      label: "WAIT",
      shortLabel: "WAIT",
      color: "text-gray-400",
      bgColor: "bg-gray-800 text-gray-400",
      reasoning,
    };
  }
  if (action === "MERGE") {
    return {
      icon: "🟡",
      label: "MERGE (skip)",
      shortLabel: "MERGE",
      color: "text-yellow-400",
      bgColor: "bg-yellow-900/40 text-yellow-400",
      reasoning,
    };
  }
  if (action === "SELL_NO") {
    return {
      icon: "🟢",
      label: "SELL NO tokens",
      shortLabel: "SELL NO",
      color: "text-green-400",
      bgColor: "bg-green-900/40 text-green-400",
      reasoning,
    };
  }
  if (action === "SELL_YES") {
    return {
      icon: "🔴",
      label: "SELL YES tokens",
      shortLabel: "SELL YES",
      color: "text-red-400",
      bgColor: "bg-red-900/40 text-red-400",
      reasoning,
    };
  }
  return {
    icon: "❓",
    label: action,
    shortLabel: action,
    color: "text-gray-400",
    bgColor: "bg-gray-800 text-gray-400",
    reasoning,
  };
}

/**
 * Fallback: infer decision display from signals when no backend decision available.
 */
function inferDecisionDisplay(signals, duration) {
  const dist = Math.abs(signals.price_vs_strike_pct || 0);
  const timeRem = signals.time_remaining || 999;
  const deadline = duration === 300 ? 90 : 180;

  if (timeRem > deadline) {
    return {
      icon: "⏳",
      label: "WAIT",
      shortLabel: "WAIT",
      color: "text-gray-400",
      bgColor: "bg-gray-800 text-gray-400",
      reasoning: [`Waiting for decision deadline (≤${deadline}s remaining)`],
    };
  }
  if (dist < 0.03) {
    return {
      icon: "🟡",
      label: "MERGE (skip)",
      shortLabel: "MERGE",
      color: "text-yellow-400",
      bgColor: "bg-yellow-900/40 text-yellow-400",
      reasoning: ["Too close to strike — coin flip"],
    };
  }
  if (signals.price_vs_strike_pct > 0) {
    return {
      icon: "🟢",
      label: "SELL NO tokens",
      shortLabel: "SELL NO",
      color: "text-green-400",
      bgColor: "bg-green-900/40 text-green-400",
      reasoning: ["Price above strike", "Sell losing NO side"],
    };
  }
  return {
    icon: "🔴",
    label: "SELL YES tokens",
    shortLabel: "SELL YES",
    color: "text-red-400",
    bgColor: "bg-red-900/40 text-red-400",
    reasoning: ["Price below strike", "Sell losing YES side"],
  };
}
