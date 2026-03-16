import React from "react";

/**
 * Live signal indicators panel within a market card.
 * Displays all Tier 1, 2, and 3 signals.
 */
export default function SignalPanel({ signals }) {
  if (!signals) {
    return (
      <div className="text-xs text-gray-500 py-2">Waiting for signals…</div>
    );
  }

  const rows = [
    // Tier 1 — Core
    { label: "Momentum 5s", value: signals.momentum_5s, fmt: (v) => v?.toFixed(2) },
    { label: "Momentum 15s", value: signals.momentum_15s, fmt: (v) => v?.toFixed(2) },
    { label: "Momentum 30s", value: signals.momentum_30s, fmt: (v) => v?.toFixed(2) },
    { label: "Exchange Lead", value: signals.exchange_lead, fmt: (v) => v?.toFixed(2) },
    {
      label: "Implied Prob",
      value: signals.implied_probability,
      fmt: (v) => `${(v * 100).toFixed(0)}%`,
      color: false,
    },
    { label: "Order Flow", value: signals.net_order_flow_30s, fmt: (v) => `${v >= 0 ? "+" : ""}${v?.toFixed(1)} net` },
    // Tier 2 — Confirmation
    {
      label: "RSI(14)",
      value: signals.rsi_14,
      fmt: (v) => (v != null ? v.toFixed(1) : "—"),
      color: false,
    },
    {
      label: "EMA Cross",
      value: signals.ema_crossover,
      fmt: (v) => (v > 0 ? "Bullish" : v < 0 ? "Bearish" : "Neutral"),
    },
    { label: "VWAP Dev", value: signals.vwap_deviation, fmt: (v) => `${v >= 0 ? "+" : ""}${v?.toFixed(2)}%` },
    {
      label: "Volatility",
      value: signals.volatility_60s,
      fmt: (v) => {
        if (v > 50) return "High";
        if (v > 20) return "Medium";
        return "Low";
      },
      color: false,
    },
    // Tier 3 — Edge Amplifiers
    {
      label: "Funding",
      value: signals.funding_rate,
      fmt: (v) => (v != null ? `${(v * 100).toFixed(4)}%` : "—"),
    },
    {
      label: "OI Change",
      value: signals.open_interest_change,
      fmt: (v) => (v != null ? `${v >= 0 ? "+" : ""}${v.toFixed(1)}%` : "—"),
    },
    {
      label: "Consensus",
      value: signals.multi_exchange_consensus,
      fmt: (v) => (v >= 1 ? "✅ Agree" : "⚠️ Diverge"),
      color: false,
    },
  ];

  return (
    <div className="space-y-0.5">
      <div className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1">
        Signals
      </div>
      {rows.map(({ label, value, fmt, color = true }) => {
        const display = fmt ? fmt(value) : value;
        const cls =
          color === false
            ? "text-gray-200"
            : value > 0
            ? "text-green-400"
            : value < 0
            ? "text-red-400"
            : "text-gray-400";
        return (
          <div key={label} className="flex justify-between text-xs">
            <span className="text-gray-500">{label}</span>
            <span className={cls}>{display}</span>
          </div>
        );
      })}
    </div>
  );
}
