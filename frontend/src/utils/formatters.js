/**
 * Number and time formatting helpers for the dashboard.
 */

/** Format a price as $X,XXX.XX */
export function formatPrice(price) {
  if (price == null || isNaN(price)) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(price);
}

/** Format a crypto price with more decimal places */
export function formatCryptoPrice(price) {
  if (price == null || isNaN(price)) return "—";
  const decimals = price > 100 ? 2 : price > 1 ? 4 : 6;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(price);
}

/** Format a percentage value */
export function formatPct(pct) {
  if (pct == null || isNaN(pct)) return "—";
  return `${pct >= 0 ? "+" : ""}${pct.toFixed(3)}%`;
}

/** Format seconds as M:SS countdown */
export function formatCountdown(seconds) {
  if (seconds == null || seconds < 0) return "0:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/** Format a millisecond timestamp as HH:MM:SS */
export function formatTime(ts) {
  if (!ts) return "—";
  const d = new Date(ts);
  return d.toLocaleTimeString("en-US", { hour12: false });
}

/** Format a signed dollar amount */
export function formatPnL(amount) {
  if (amount == null || isNaN(amount)) return "—";
  const sign = amount >= 0 ? "+" : "";
  return `${sign}$${Math.abs(amount).toFixed(2)}`;
}

/** Color class based on value (positive=green, negative=red, zero=gray) */
export function colorClass(value) {
  if (value > 0) return "text-green-400";
  if (value < 0) return "text-red-400";
  return "text-gray-400";
}
