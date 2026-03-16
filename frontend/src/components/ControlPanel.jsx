import React from "react";
import { formatPrice, formatPnL } from "../utils/formatters";

/**
 * Control panel with Start/Stop analysis and bankroll overview.
 */
export default function ControlPanel({ bankroll, running, onStart, onPause }) {
  return (
    <div className="bg-brand-card border border-brand-border rounded-lg p-4">
      <h3 className="text-sm font-semibold text-gray-400 mb-3 uppercase tracking-wider">
        Control Panel
      </h3>
      <div className="flex items-center gap-3 mb-4">
        {running ? (
          <button
            onClick={onPause}
            className="flex-1 py-2 bg-yellow-600 hover:bg-yellow-700 rounded font-medium transition text-sm"
          >
            ⏸ Pause Analysis
          </button>
        ) : (
          <button
            onClick={onStart}
            className="flex-1 py-2 bg-green-600 hover:bg-green-700 rounded font-medium transition text-sm"
          >
            ▶ Start Analysis
          </button>
        )}
      </div>
      {bankroll && (
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="text-gray-400">Initial:</div>
          <div>{formatPrice(bankroll.initial_bankroll)}</div>
          <div className="text-gray-400">Active Positions:</div>
          <div>{bankroll.active_positions}</div>
          <div className="text-gray-400">Available:</div>
          <div>{formatPrice(bankroll.available_capital)}</div>
          <div className="text-gray-400">Gas Spent:</div>
          <div>{formatPrice(bankroll.total_gas)}</div>
        </div>
      )}
    </div>
  );
}
