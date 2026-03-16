import React from "react";
import { formatPrice, formatPnL, colorClass } from "../utils/formatters";

/**
 * $100 bankroll P&L tracker widget.
 */
export default function BankrollTracker({ bankroll }) {
  if (!bankroll) {
    return (
      <div className="bg-brand-card border border-brand-border rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">
          Bankroll
        </h3>
        <p className="text-gray-500 mt-2 text-sm">Waiting for data…</p>
      </div>
    );
  }

  const {
    current_bankroll,
    total_pnl,
    hourly_pnl,
    daily_pnl,
    win_count,
    loss_count,
    merge_count,
    total_trades,
    win_rate,
    avg_sell_price,
  } = bankroll;

  return (
    <div className="bg-brand-card border border-brand-border rounded-lg p-4">
      <h3 className="text-sm font-semibold text-gray-400 mb-3 uppercase tracking-wider">
        💰 Bankroll Tracker
      </h3>

      {/* Main bankroll */}
      <div className="text-center mb-4">
        <div className="text-3xl font-bold text-white">
          {formatPrice(current_bankroll)}
        </div>
        <div className={`text-lg font-semibold ${colorClass(total_pnl)}`}>
          {formatPnL(total_pnl)}
        </div>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 gap-y-2 gap-x-4 text-xs">
        <div className="text-gray-400">Hourly P&L</div>
        <div className={colorClass(hourly_pnl)}>{formatPnL(hourly_pnl)}</div>

        <div className="text-gray-400">Daily P&L</div>
        <div className={colorClass(daily_pnl)}>{formatPnL(daily_pnl)}</div>

        <div className="text-gray-400">Win Rate</div>
        <div className="text-white">{win_rate.toFixed(1)}%</div>

        <div className="text-gray-400">Trades</div>
        <div className="text-white">
          {total_trades}{" "}
          <span className="text-gray-500">
            ({win_count}W / {loss_count}L / {merge_count}M)
          </span>
        </div>

        <div className="text-gray-400">Avg Sell Price</div>
        <div className="text-white">${avg_sell_price.toFixed(4)}</div>
      </div>
    </div>
  );
}
