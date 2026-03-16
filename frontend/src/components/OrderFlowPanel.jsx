import React from "react";

/**
 * Order flow visualization — shows recent buy/sell activity.
 */
export default function OrderFlowPanel({ signals }) {
  const flow = signals?.net_order_flow_30s ?? 0;
  const isPositive = flow >= 0;

  // Visual bar width (capped at 100%)
  const maxFlow = 50; // normalize to ±50
  const pct = Math.min(Math.abs(flow) / maxFlow, 1) * 100;

  return (
    <div className="mt-2">
      <div className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1">
        Order Flow (30s)
      </div>
      <div className="flex items-center gap-2">
        <div className="flex-1 h-3 bg-gray-700 rounded-full overflow-hidden relative">
          {/* Center marker */}
          <div className="absolute left-1/2 top-0 bottom-0 w-px bg-gray-500 z-10" />
          {/* Flow bar */}
          <div
            className={`absolute top-0 bottom-0 rounded-full transition-all duration-300 ${
              isPositive ? "bg-green-500 left-1/2" : "bg-red-500 right-1/2"
            }`}
            style={{ width: `${pct / 2}%` }}
          />
        </div>
        <span
          className={`text-xs font-mono w-16 text-right ${
            isPositive ? "text-green-400" : "text-red-400"
          }`}
        >
          {flow >= 0 ? "+" : ""}
          {flow.toFixed(1)}
        </span>
      </div>
    </div>
  );
}
