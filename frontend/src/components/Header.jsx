import React from "react";
import { formatPrice, formatPnL, colorClass } from "../utils/formatters";

/**
 * App header with status indicators, bankroll, and control buttons.
 */
export default function Header({
  bankroll,
  connectionStatus,
  running,
  onStart,
  onPause,
  onToggleTradeLog,
}) {
  const pnl = bankroll?.total_pnl ?? 0;
  const winRate = bankroll?.win_rate ?? 0;

  return (
    <header className="bg-brand-card border-b border-brand-border px-6 py-3">
      <div className="flex items-center justify-between flex-wrap gap-3">
        {/* Title + Status */}
        <div className="flex items-center gap-4">
          <h1 className="text-xl font-bold text-white">
            🎯 Polymarket Sniper Bot
          </h1>
          <span
            className={`text-sm font-medium px-2 py-0.5 rounded ${
              running
                ? "bg-green-900/50 text-green-400"
                : "bg-yellow-900/50 text-yellow-400"
            }`}
          >
            {running ? "🟢 Running" : "🟡 Paused"}
          </span>
        </div>

        {/* Bankroll Stats */}
        <div className="flex items-center gap-6 text-sm">
          <div>
            <span className="text-gray-400">Bankroll: </span>
            <span className="font-semibold text-white">
              {formatPrice(bankroll?.current_bankroll)}
            </span>
          </div>
          <div>
            <span className="text-gray-400">P&L: </span>
            <span className={`font-semibold ${colorClass(pnl)}`}>
              {formatPnL(pnl)}
            </span>
          </div>
          <div>
            <span className="text-gray-400">Win Rate: </span>
            <span className="font-semibold text-white">{winRate.toFixed(1)}%</span>
          </div>
        </div>

        {/* Connection Indicators */}
        <div className="flex items-center gap-3 text-xs">
          <span title="Binance WebSocket">
            {connectionStatus.binance_ws ? "🟢" : "🔴"} Binance
          </span>
          <span title="Polymarket RTDS">
            {connectionStatus.rtds ? "🟢" : "🔴"} RTDS
          </span>
          <span title="Redis">
            {connectionStatus.redis ? "🟢" : "🔴"} Redis
          </span>
        </div>

        {/* Control Buttons */}
        <div className="flex items-center gap-2">
          {running ? (
            <button
              onClick={onPause}
              className="px-3 py-1.5 text-sm bg-yellow-600 hover:bg-yellow-700 rounded font-medium transition"
            >
              ⏸ Pause
            </button>
          ) : (
            <button
              onClick={onStart}
              className="px-3 py-1.5 text-sm bg-green-600 hover:bg-green-700 rounded font-medium transition"
            >
              ▶ Start Analysis
            </button>
          )}
          <button
            onClick={onToggleTradeLog}
            className="px-3 py-1.5 text-sm bg-brand-accent hover:bg-blue-700 rounded font-medium transition"
          >
            📊 Trade Log
          </button>
        </div>
      </div>
    </header>
  );
}
