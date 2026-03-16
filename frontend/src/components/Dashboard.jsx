import React from "react";
import MarketCard from "./MarketCard";
import TradeLog from "./TradeLog";
import BankrollTracker from "./BankrollTracker";
import ControlPanel from "./ControlPanel";

/**
 * Main dashboard layout — market cards grid + sidebar.
 */
export default function Dashboard({
  markets,
  bankroll,
  trades,
  running,
  onStart,
  onPause,
  showTradeLog,
  onToggleTradeLog,
}) {
  // Convert markets object to sorted array
  const marketList = Object.values(markets).sort((a, b) => {
    // Sort: 5min before 15min, then by asset
    if (a.duration !== b.duration) return a.duration - b.duration;
    return a.asset.localeCompare(b.asset);
  });

  return (
    <div className="flex flex-col lg:flex-row gap-4 p-4 min-h-0 flex-1">
      {/* Main area: Market cards grid */}
      <div className="flex-1 min-w-0">
        {marketList.length === 0 ? (
          <div className="flex items-center justify-center h-64 bg-brand-card border border-brand-border rounded-lg">
            <div className="text-center">
              <div className="text-4xl mb-3">🔍</div>
              <h2 className="text-lg font-semibold text-gray-300 mb-1">
                Discovering Markets…
              </h2>
              <p className="text-sm text-gray-500">
                Searching for active 5-minute and 15-minute crypto prediction
                markets on Polymarket.
              </p>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {marketList.map((m) => (
              <MarketCard key={m.slug} market={m} />
            ))}
          </div>
        )}

        {/* Trade log (toggleable) */}
        {showTradeLog && (
          <div className="mt-4">
            <TradeLog trades={trades} onClose={onToggleTradeLog} />
          </div>
        )}
      </div>

      {/* Sidebar */}
      <div className="w-full lg:w-72 flex-shrink-0 space-y-4">
        <ControlPanel
          bankroll={bankroll}
          running={running}
          onStart={onStart}
          onPause={onPause}
        />
        <BankrollTracker bankroll={bankroll} />
      </div>
    </div>
  );
}
