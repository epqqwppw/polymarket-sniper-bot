"""Deterministic Polymarket slug generation for crypto up/down markets."""

import time
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional

# Timezone constants
_UTC = ZoneInfo("UTC")
_ET = ZoneInfo("America/New_York")
_IST = ZoneInfo("Asia/Kolkata")

# Asset full-name map for hourly slugs
_ASSET_FULL_NAME: dict[str, str] = {
    "btc": "bitcoin",
    "eth": "ethereum",
    "sol": "solana",
}


def floor_snap(now_ts: float, interval_min: int) -> int:
    """Return the floor-aligned Unix timestamp for the given interval."""
    step = interval_min * 60
    return (int(now_ts) // step) * step


def get_short_slugs(
    asset: str,
    interval_min: int,
    now_ts: float,
    past: int = 3,
    future: int = 3,
) -> list[dict]:
    """Return short-interval slug dicts with past/live/future window labels."""
    step = interval_min * 60
    base_ts = floor_snap(now_ts, interval_min)
    results: list[dict] = []

    for k in range(-past, future + 1):
        unix_ts = base_ts + k * step
        slug = f"{asset.lower()}-updown-{interval_min}m-{unix_ts}"
        if k < 0:
            wtype = "past"
        elif k == 0:
            wtype = "live"
        else:
            wtype = "future"

        ist_dt = datetime.fromtimestamp(unix_ts, tz=_UTC).astimezone(_IST)
        ist_label = ist_dt.strftime("%Y-%m-%d %H:%M IST")

        results.append(
            {
                "slug": slug,
                "unix_ts": unix_ts,
                "window_type": wtype,
                "ist_label": ist_label,
            }
        )
    return results


def get_hourly_slug(asset: str, now_ts: float) -> dict:
    """Return the hourly slug dict for the given asset and timestamp."""
    full_name = _ASSET_FULL_NAME.get(asset.lower(), asset.lower())

    et_dt = datetime.fromtimestamp(now_ts, tz=_UTC).astimezone(_ET)
    et_hour = et_dt.hour
    display_hour = et_hour + 1

    # Determine 12-hour label and am/pm suffix
    if display_hour == 24:
        hour_label = "12"
        suffix = "am"
    elif display_hour > 12:
        hour_label = str(display_hour - 12)
        suffix = "pm"
    elif display_hour == 12:
        hour_label = "12"
        suffix = "pm"
    elif display_hour == 0:
        hour_label = "12"
        suffix = "am"
    else:
        hour_label = str(display_hour)
        suffix = "am"

    month = et_dt.strftime("%B").lower()
    day = et_dt.day
    year = et_dt.year

    slug = f"{full_name}-up-or-down-{month}-{day}-{year}-{hour_label}{suffix}-et"

    et_window_start = f"{et_hour:d}:00"
    et_window_end = f"{display_hour % 24:d}:00"
    et_window = f"{et_window_start}-{et_window_end} ET"

    return {
        "slug": slug,
        "et_window": et_window,
        "window_type": "live",
    }


def get_all_slugs(
    assets: Optional[list[str]] = None,
    intervals: Optional[list[int]] = None,
    now_ts: Optional[float] = None,
) -> list[dict]:
    """Return a combined list of slugs for all asset/interval/hourly combos."""
    if assets is None:
        assets = ["btc", "eth", "sol"]
    if intervals is None:
        intervals = [5, 15]
    if now_ts is None:
        now_ts = time.time()

    results: list[dict] = []
    for asset in assets:
        for interval in intervals:
            results.extend(get_short_slugs(asset, interval, now_ts))
        results.append(get_hourly_slug(asset, now_ts))
    return results


if __name__ == "__main__":
    # ── Verification asserts ──────────────────────────────────────────
    assert floor_snap(1742123455, 5) == 1742123400, "5m snap failed"
    # The problem statement listed 1742122500 but that is not divisible by 900
    # (15*60). The correct floor-snap per the documented formula is 1742122800.
    assert floor_snap(1742123455, 15) == 1742122800, "15m snap failed"

    live_slugs = [s["slug"] for s in get_short_slugs("btc", 5, 1742123455, 0, 0)]
    assert "btc-updown-5m-1742123400" in live_slugs, "live slug missing"

    hourly = get_hourly_slug("btc", 1742123455.0)
    assert hourly["slug"].startswith("bitcoin-up-or-down-"), "hourly prefix wrong"

    all_slugs = get_all_slugs(now_ts=1742123455.0)
    for s in all_slugs:
        assert s["slug"] == s["slug"].lower(), f"not lowercase: {s['slug']}"
        assert " " not in s["slug"], f"space found: {s['slug']}"

    print("✓ All asserts passed.\n")

    # ── Sample output ─────────────────────────────────────────────────
    now = time.time()
    now_utc = datetime.fromtimestamp(now, tz=_UTC)
    print(f"Now (UTC): {now_utc:%Y-%m-%d %H:%M:%S}")
    print(f"Now (ET) : {now_utc.astimezone(_ET):%Y-%m-%d %H:%M:%S %Z}")
    print(f"Now (IST): {now_utc.astimezone(_IST):%Y-%m-%d %H:%M:%S %Z}")
    print()

    for entry in get_all_slugs(now_ts=now):
        print(entry)
