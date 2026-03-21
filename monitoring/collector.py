"""MetricsCollector protocol — the single interface for all metric backends."""

from typing import Dict, Optional, Protocol, runtime_checkable


@runtime_checkable
class MetricsCollector(Protocol):
    """Protocol for metric collection backends.

    Implementations: InMemoryCollector (test), CloudWatchCollector (prod).
    Injected via DI into TurnPipeline and SessionManager.
    """

    def increment(
        self,
        name: str,
        value: float = 1,
        dimensions: Optional[Dict[str, str]] = None,
    ) -> None:
        """Increment a counter metric."""
        ...

    def observe(
        self,
        name: str,
        value: float,
        dimensions: Optional[Dict[str, str]] = None,
        unit: str = "Milliseconds",
    ) -> None:
        """Record an observation (histogram/distribution)."""
        ...

    def set_gauge(
        self,
        name: str,
        value: float,
        dimensions: Optional[Dict[str, str]] = None,
    ) -> None:
        """Set a gauge to an absolute value."""
        ...

    def flush(self) -> None:
        """Flush pending metrics to the backend. No-op for in-memory."""
        ...
