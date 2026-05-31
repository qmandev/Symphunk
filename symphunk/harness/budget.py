import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

_MAX_RATE_PER_WINDOW = 5
_RATE_WINDOW_SECONDS = 60
_MAX_TIME_WINDOW_DAYS = 7


@dataclass
class SearchBudget:
    max_searches: int = 10
    _used: int = field(default=0, init=False)
    _window_start: float = field(default_factory=time.monotonic, init=False)
    _window_count: int = field(default=0, init=False)

    def check(self, *, expensive: bool = False) -> None:
        """Raise if over budget; otherwise consume one search slot."""
        if self._used >= self.max_searches:
            raise BudgetExhausted(f"Search cap reached ({self.max_searches}/run)")

        now = time.monotonic()
        if now - self._window_start >= _RATE_WINDOW_SECONDS:
            self._window_start = now
            self._window_count = 0

        # Expensive searches (full-scan, no tstats) count double against rate limit
        limit = _MAX_RATE_PER_WINDOW // 2 if expensive else _MAX_RATE_PER_WINDOW
        if self._window_count >= limit:
            raise RateLimitBackoff(
                f"Rate limit: {limit} searches per {_RATE_WINDOW_SECONDS}s"
                + (" (expensive)" if expensive else "")
            )

        self._used += 1
        self._window_count += 1

    @staticmethod
    def time_bounds(days: int = 1) -> tuple[str, str]:
        """Return (earliest, latest) ISO strings for SPL, capped at 7 days."""
        days = min(days, _MAX_TIME_WINDOW_DAYS)
        now = datetime.now(timezone.utc)
        earliest = now - timedelta(days=days)
        fmt = "%Y-%m-%dT%H:%M:%S"
        return earliest.strftime(fmt), now.strftime(fmt)

    @property
    def remaining(self) -> int:
        return self.max_searches - self._used


class BudgetExhausted(Exception):
    pass


class RateLimitBackoff(Exception):
    pass
