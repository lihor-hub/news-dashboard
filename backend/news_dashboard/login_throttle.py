"""In-process throttle for failed password-login attempts.

Keys on normalized username only; client address is excluded because
reverse-proxy deployments may not expose the original remote address reliably.

Window: 15 minutes / 5 failures → HTTP 429.  A successful login clears the
recorded failures for that key so legitimate users are never permanently locked.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timezone

_WINDOW_SECONDS: int = 15 * 60
_MAX_FAILURES: int = 5

# Protected by _lock; maps normalised username → list[datetime (utc)]
_failures: dict[str, list[datetime]] = defaultdict(list)
_lock = threading.Lock()


def _wall_clock() -> datetime:
    return datetime.now(timezone.utc)


# Swappable clock for deterministic tests (default: wall time)
_now: Callable[[], datetime] = _wall_clock


def _set_clock(clock: Callable[[], datetime]) -> None:
    """Override the clock — test use only."""
    global _now  # noqa: PLW0603
    _now = clock


def _reset_clock() -> None:
    global _now  # noqa: PLW0603
    _now = _wall_clock


def _prune(key: str, now: datetime) -> None:
    cutoff = now.timestamp() - _WINDOW_SECONDS
    _failures[key] = [ts for ts in _failures[key] if ts.timestamp() >= cutoff]


def is_throttled(username: str) -> bool:
    """Return True if *username* has too many recent failures."""
    key = username.strip().lower()
    now = _now()
    with _lock:
        _prune(key, now)
        return len(_failures[key]) >= _MAX_FAILURES


def record_failure(username: str) -> None:
    """Record one failed attempt for *username*."""
    key = username.strip().lower()
    now = _now()
    with _lock:
        _prune(key, now)
        _failures[key].append(now)


def clear_failures(username: str) -> None:
    """Clear all recorded failures for *username* (call after successful login)."""
    key = username.strip().lower()
    with _lock:
        _failures.pop(key, None)


def reset_all() -> None:
    """Wipe all throttle state — test use only."""
    with _lock:
        _failures.clear()
