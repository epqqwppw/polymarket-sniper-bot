import React, { useState } from "react";
import Header from "./components/Header";
import Dashboard from "./components/Dashboard";
import { useSocket } from "./hooks/useSocket";
import { useMarketData } from "./hooks/useMarketData";

/**
 * Main App component — connects Socket.IO, manages top-level state.
 */
export default function App() {
  const { socket, connected, emit } = useSocket();
  const { markets, bankroll, decisions, connectionStatus, trades } =
    useMarketData(socket);

  const [running, setRunning] = useState(true);
  const [showTradeLog, setShowTradeLog] = useState(false);

  const handleStart = () => {
    setRunning(true);
    emit("start_analysis");
  };

  const handlePause = () => {
    setRunning(false);
    emit("pause_analysis");
  };

  const toggleTradeLog = () => setShowTradeLog((prev) => !prev);

  return (
    <div className="min-h-screen bg-brand-dark text-gray-200 flex flex-col">
      {/* Connection banner */}
      {!connected && (
        <div className="bg-red-900/70 text-red-200 text-center text-sm py-1.5 font-medium">
          ⚠️ Disconnected from server — reconnecting…
        </div>
      )}

      <Header
        bankroll={bankroll}
        connectionStatus={connectionStatus}
        running={running}
        onStart={handleStart}
        onPause={handlePause}
        onToggleTradeLog={toggleTradeLog}
      />

      <Dashboard
        markets={markets}
        bankroll={bankroll}
        trades={trades}
        running={running}
        onStart={handleStart}
        onPause={handlePause}
        showTradeLog={showTradeLog}
        onToggleTradeLog={toggleTradeLog}
      />
    </div>
  );
}
