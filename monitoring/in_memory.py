"""InMemoryCollector — test/local-dev metrics backend."""

from collections import defaultdict
from typing import Dict, List, Optional, Tuple


def _dim_key(dimensions: Optional[Dict[str, str]] = None) -> Tuple:
    """Convert dimensions dict to a hashable key."""
    if not dimensions:
        return ()
    return tuple(sorted(dimensions.items()))


class InMemoryCollector:
    """Stores metrics in memory for testing and local development."""

    def __init__(self) -> None:
        self._counters: Dict[Tuple, float] = defaultdict(float)
        self._observations: Dict[Tuple, List[float]] = defaultdict(list)
        self._gauges: Dict[Tuple, float] = {}

    def increment(
        self,
        name: str,
        value: float = 1,
        dimensions: Optional[Dict[str, str]] = None,
    ) -> None:
        key = (name, _dim_key(dimensions))
        self._counters[key] += value

    def observe(
        self,
        name: str,
        value: float,
        dimensions: Optional[Dict[str, str]] = None,
        unit: str = "Milliseconds",
    ) -> None:
        key = (name, _dim_key(dimensions))
        self._observations[key].append(value)

    def set_gauge(
        self,
        name: str,
        value: float,
        dimensions: Optional[Dict[str, str]] = None,
    ) -> None:
        key = (name, _dim_key(dimensions))
        self._gauges[key] = value

    # --- Query helpers (test only) ---

    def get_counter(
        self, name: str, dimensions: Optional[Dict[str, str]] = None
    ) -> float:
        return self._counters.get((name, _dim_key(dimensions)), 0)

    def get_observations(
        self, name: str, dimensions: Optional[Dict[str, str]] = None
    ) -> List[float]:
        return list(self._observations.get((name, _dim_key(dimensions)), []))

    def get_gauge(
        self, name: str, dimensions: Optional[Dict[str, str]] = None
    ) -> Optional[float]:
        return self._gauges.get((name, _dim_key(dimensions)))

    def flush(self) -> None:
        """No-op for in-memory collector."""
        pass
