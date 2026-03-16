import React from "react";
import { formatTime, formatPnL, colorClass } from "../utils/formatters";

/**
 * Scrollable simulated trade history log.
 */
export default function TradeLog({ trades, onClose }) {
  return (
    <div className="bg-brand-card border border-brand-border rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">
          📋 Trade Log
        </h3>
        {onClose && (
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-300 text-sm"
          >
            ✕ Close
          </button>
        )}
      </div>

      {trades.length === 0 ? (
        <p className="text-gray-500 text-sm text-center py-4">
          No trades yet — waiting for market decisions…
        </p>
      ) : (
        <div className="max-h-64 overflow-y-auto space-y-1">
          {trades.map((t, i) => {
            const pnl = t.pnl ?? 0;
            const isWin = pnl > 0;
            const isMerge = t.action === "MERGE";
            return (
              <div
                key={i}
                className="flex items-center gap-3 text-xs py-1.5 px-2 rounded bg-brand-dark/50 hover:bg-brand-dark"
              >
                <span className="text-gray-500 w-16 flex-shrink-0">
                  {formatTime(t.timestamp)}
                </span>
                <span className="text-gray-300 w-14 flex-shrink-0">
                  {t.asset} {t.duration === 300 ? "5m" : "15m"}
                </span>
                <span
                  className={`w-28 flex-shrink-0 ${
                    isMerge
                      ? "text-yellow-400"
                      : isWin
                      ? "text-green-400"
                      : "text-red-400"
                  }`}
                >
                  {isMerge
                    ? "MERGED"
                    : `${t.action} ×${t.size} @ $${t.price?.toFixed(2)}`}
                </span>
                <span className={`font-mono ${colorClass(pnl)}`}>
                  {isMerge ? "$0.00" : formatPnL(pnl)}
                </span>
                {t.gas_estimate > 0 && (
                  <span className="text-gray-600 ml-auto">
                    gas: ${t.gas_estimate.toFixed(2)}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Running total */}
      {trades.length > 0 && (
        <div className="mt-2 pt-2 border-t border-brand-border flex justify-between text-xs">
          <span className="text-gray-400">
            Total trades: {trades.length}
          </span>
          <span className={colorClass(trades.reduce((s, t) => s + (t.pnl || 0), 0))}>
            Net: {formatPnL(trades.reduce((s, t) => s + (t.pnl || 0), 0))}
          </span>
        </div>
      )}
    </div>
  );
}
