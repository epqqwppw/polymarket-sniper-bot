import { useEffect, useState, useCallback } from "react";

/**
 * Hook that manages market data state from Socket.IO events.
 * Listens for market_update, bankroll, decision, connection_status events.
 */
export function useMarketData(socket) {
  const [markets, setMarkets] = useState({});
  const [bankroll, setBankroll] = useState(null);
  const [decisions, setDecisions] = useState({});
  const [connectionStatus, setConnectionStatus] = useState({
    binance_ws: false,
    rtds: false,
    redis: false,
  });
  const [trades, setTrades] = useState([]);

  useEffect(() => {
    if (!socket) return;

    const handleMarketUpdate = (data) => {
      setMarkets((prev) => ({
        ...prev,
        [data.slug]: data,
      }));
    };

    const handleBankroll = (data) => {
      setBankroll(data);
    };

    const handleDecision = (data) => {
      setDecisions((prev) => ({
        ...prev,
        [data.market_id || data.slug]: data,
      }));
    };

    const handleConnectionStatus = (data) => {
      setConnectionStatus(data);
    };

    const handleTradeLog = (data) => {
      setTrades((prev) => {
        const updated = [data, ...prev];
        return updated.slice(0, 100); // Keep last 100
      });
    };

    socket.on("market_update", handleMarketUpdate);
    socket.on("bankroll", handleBankroll);
    socket.on("decision", handleDecision);
    socket.on("connection_status", handleConnectionStatus);
    socket.on("trade", handleTradeLog);

    return () => {
      socket.off("market_update", handleMarketUpdate);
      socket.off("bankroll", handleBankroll);
      socket.off("decision", handleDecision);
      socket.off("connection_status", handleConnectionStatus);
      socket.off("trade", handleTradeLog);
    };
  }, [socket]);

  const clearTrades = useCallback(() => setTrades([]), []);

  return {
    markets,
    bankroll,
    decisions,
    connectionStatus,
    trades,
    clearTrades,
  };
}
