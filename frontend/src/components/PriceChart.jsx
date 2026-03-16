import React from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";

/**
 * Real-time mini price chart showing the last 60 seconds of price data.
 */
export default function PriceChart({ ticks, strike }) {
  if (!ticks || ticks.length === 0) {
    return (
      <div className="h-24 flex items-center justify-center text-gray-500 text-xs">
        No price data
      </div>
    );
  }

  // Format ticks for Recharts: [{time, price}]
  const data = ticks.map((t) => ({
    time: new Date(t.ts).toLocaleTimeString("en-US", {
      hour12: false,
      minute: "2-digit",
      second: "2-digit",
    }),
    price: t.price,
  }));

  // Compute domain for Y axis (auto with some padding)
  const prices = data.map((d) => d.price).filter((p) => p != null && !isNaN(p));
  if (prices.length === 0) {
    return (
      <div className="h-24 flex items-center justify-center text-gray-500 text-xs">
        No price data
      </div>
    );
  }
  const allValues = strike ? [...prices, strike] : prices;
  const minPrice = Math.min(...allValues);
  const maxPrice = Math.max(...allValues);
  const padding = (maxPrice - minPrice) * 0.1 || 1;

  return (
    <div className="h-24 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
          <XAxis dataKey="time" hide />
          <YAxis
            domain={[minPrice - padding, maxPrice + padding]}
            hide
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#1e293b",
              border: "1px solid #334155",
              borderRadius: 6,
              fontSize: 11,
            }}
            labelStyle={{ color: "#94a3b8" }}
            formatter={(val) => [`$${Number(val).toFixed(2)}`, "Price"]}
          />
          <Line
            type="monotone"
            dataKey="price"
            stroke="#3b82f6"
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
          {/* Strike reference line — shows the "price to beat" */}
          {strike && (
            <ReferenceLine
              y={strike}
              stroke="#ef4444"
              strokeWidth={1}
              strokeDasharray="4 4"
            />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
