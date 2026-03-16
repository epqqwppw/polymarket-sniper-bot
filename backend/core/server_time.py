"""Polymarket server-time synchronisation.

Uses GET https://clob.polymarket.com/time to calculate the offset between
local system time and Polymarket's CLOB server clock.  All time-sensitive
operations (slug generation, order placement) should use ``server_now()``
instead of ``time.time()`` to stay in sync with the exchange.
"""

import asyncio
import time
from typing import Optional

import aiohttp

from backend.config import POLYMARKET_CLOB_API
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# Refresh the offset every 30 seconds
_SYNC_INTERVAL_SECS = 30


class ServerTimeSyncer:
    """Keeps a running offset between local UTC and Polymarket server time."""

    def __init__(self) -> None:
        self._offset_ms: float = 0.0  # server_ms - local_ms
        self._last_sync: float = 0.0
        self._running: bool = False
        self._task: Optional[asyncio.Task] = None
        self._http: Optional[aiohttp.ClientSession] = None

    # ── Public API ───────────────────────────────────────────────────────

    @property
    def offset_ms(self) -> float:
        """Estimated (server − local) offset in milliseconds."""
        return self._offset_ms

    def server_now(self) -> float:
        """Return the current Polymarket server time as a Unix timestamp (seconds)."""
        return time.time() + (self._offset_ms / 1000.0)

    def server_now_ms(self) -> int:
        """Return the current Polymarket server time in milliseconds."""
        return int(time.time() * 1000) + int(self._offset_ms)

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the background sync loop."""
        self._running = True
        self._http = aiohttp.ClientSession()
        # Do an initial sync immediately
        await self._sync_once()
        self._task = asyncio.create_task(self._sync_loop(), name="server_time_sync")
        logger.info(
            "ServerTimeSyncer started (offset=%.1f ms)", self._offset_ms
        )

    async def stop(self) -> None:
        """Stop the sync loop and clean up."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._http:
            await self._http.close()
        logger.info("ServerTimeSyncer stopped")

    # ── Internal ─────────────────────────────────────────────────────────

    async def _sync_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(_SYNC_INTERVAL_SECS)
                await self._sync_once()
            except asyncio.CancelledError:
                return
            except Exception:
                logger.debug("Server time sync error, will retry")

    async def _sync_once(self) -> None:
        """Perform a single round-trip to GET /time and update the offset."""
        if not self._http:
            return
        url = f"{POLYMARKET_CLOB_API}/time"
        try:
            t0 = time.time() * 1000  # local ms before request
            async with self._http.get(
                url, timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status != 200:
                    logger.debug("Server time endpoint returned %d", resp.status)
                    return
                body = await resp.json()
            t1 = time.time() * 1000  # local ms after response

            # The response contains a Unix-ms timestamp
            server_ms = float(body) if isinstance(body, (int, float)) else float(body.get("time", 0))
            if server_ms <= 0:
                return

            # Estimate local time at point of server snapshot as midpoint of RTT
            local_mid = (t0 + t1) / 2.0
            self._offset_ms = server_ms - local_mid
            self._last_sync = time.time()
            logger.debug(
                "Server time synced: offset=%.1f ms  RTT=%.0f ms",
                self._offset_ms,
                t1 - t0,
            )
        except Exception:
            logger.debug("Failed to sync server time from %s", url)


# Module-level singleton
server_time_syncer = ServerTimeSyncer()
