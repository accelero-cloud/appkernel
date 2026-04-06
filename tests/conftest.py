"""
Pytest configuration for AppKernel tests.

Motor 3.x caches the event loop in AgnosticClient._io_loop on first use.
Pymongo background monitoring threads then use this cached loop to dispatch
topology events via loop.call_soon_threadsafe(). When the cached loop closes
(after asyncio.run() completes), these callbacks fail with "Event loop is closed".

Fix: patch AgnosticClient.io_loop to update the cached loop whenever the
currently running loop changes. Inside async context (get_running_loop() works),
we always use the running loop. Outside async context (coroutine creation), we
use the cached loop if still open, else get a fresh one.

This makes Motor safe to use across multiple sequential event loops in tests.
"""
import asyncio
from motor.core import AgnosticClient
from motor.frameworks.asyncio import get_event_loop as _motor_get_loop


def _adaptive_io_loop(self):
    """Return the correct event loop, refreshing the cache when it's closed."""
    try:
        running = asyncio.get_running_loop()
        # Inside async context — always use the running loop and update cache
        self._io_loop = running
        return running
    except RuntimeError:
        # Not inside async context (sync code creating a coroutine)
        if self._io_loop is None or self._io_loop.is_closed():
            # Stale or missing — get a fresh loop
            try:
                self._io_loop = _motor_get_loop()
            except RuntimeError:
                pass
        return self._io_loop


AgnosticClient.io_loop = property(_adaptive_io_loop)
