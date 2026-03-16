import React, { useState, useEffect } from "react";
import {
  formatCryptoPrice,
  formatPct,
  formatCountdown,
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
  } = market;

  const durationLabel = duration === 300 ? "5-MIN" : "15-MIN";
  const chainlinkPx = chainlink_price || binance_price || 0;
  const priceDiff = chainlinkPx - price_to_beat;
  const priceDiffPct =
    price_to_beat > 0 ? (priceDiff / price_to_beat) * 100 : 0;
  const isAbove = priceDiff >= 0;

  // Decision info from signals
  const decision = signals ? getDecisionDisplay(signals) : null;

  // Progress bar percentage (time elapsed)
  const totalDuration = duration;
  const elapsed = totalDuration - timeRemaining;
  const progressPct = totalDuration > 0 ? (elapsed / totalDuration) * 100 : 0;

  // Price ticks for chart (from signals or empty)
  const ticks = market.price_ticks || [];

  return (
    <div className="bg-brand-card border border-brand-border rounded-lg p-4 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold text-brand-accent">
            {asset} {durationLabel}
          </span>
        </div>
        <span className="text-xs text-gray-500">{slug}</span>
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
            <span
              className={`text-sm font-bold ${
                decision.color
              }`}
            >
              {decision.icon} {decision.label}
            </span>
            <span className="text-xs text-gray-400">
              Confidence: {signals.confidence || 0}/10
            </span>
          </div>
          {decision.reasoning && decision.reasoning.length > 0 && (
            <ul className="text-xs text-gray-400 space-y-0.5 list-disc list-inside">
              {decision.reasoning.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
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

/** Derive display info from signals/decision data */
function getDecisionDisplay(signals) {
  // This maps signal data to UI decision display
  // In practice, the decision comes from a separate event; here we infer from signals
  const dist = Math.abs(signals.price_vs_strike_pct || 0);
  const timeRem = signals.time_remaining || 999;

  // Simple inference (actual decision comes from backend)
  if (timeRem > 90) {
    return {
      icon: "⏳",
      label: "WAIT",
      color: "text-gray-400",
      reasoning: ["Waiting for decision deadline"],
    };
  }
  if (dist < 0.03) {
    return {
      icon: "🟡",
      label: "MERGE (skip)",
      color: "text-yellow-400",
      reasoning: ["Too close to strike — coin flip"],
    };
  }
  if (signals.price_vs_strike_pct > 0) {
    return {
      icon: "🟢",
      label: "SELL NO tokens",
      color: "text-green-400",
      reasoning: ["Price above strike", "Sell losing NO side"],
    };
  }
  return {
    icon: "🔴",
    label: "SELL YES tokens",
    color: "text-red-400",
    reasoning: ["Price below strike", "Sell losing YES side"],
  };
}
