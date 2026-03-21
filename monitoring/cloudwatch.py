"""CloudWatchCollector — EMF JSON stdout output for CloudWatch metrics."""

import json
import sys
import time
from typing import Dict, List, Optional, Tuple


class CloudWatchCollector:
    """Outputs metrics in CloudWatch Embedded Metric Format (EMF) via stdout.

    Uses direct EMF JSON output instead of aws-embedded-metrics SDK
    for broader compatibility (RISK-001 mitigation).
    Fire-and-forget: flush errors are silently swallowed (NFR-003).
    """

    def __init__(self, namespace: str = "Callbot") -> None:
        self._namespace = namespace
        self._pending: List[Tuple[str, float, str, Optional[Dict[str, str]]]] = []

    def increment(
        self,
        name: str,
        value: float = 1,
        dimensions: Optional[Dict[str, str]] = None,
    ) -> None:
        self._pending.append((name, value, "Count", dimensions))

    def observe(
        self,
        name: str,
        value: float,
        dimensions: Optional[Dict[str, str]] = None,
        unit: str = "Milliseconds",
    ) -> None:
        self._pending.append((name, value, unit, dimensions))

    def set_gauge(
        self,
        name: str,
        value: float,
        dimensions: Optional[Dict[str, str]] = None,
    ) -> None:
        self._pending.append((name, value, "None", dimensions))

    def flush(self) -> None:
        """Write all pending metrics as EMF JSON to stdout."""
        try:
            for name, value, unit, dimensions in self._pending:
                emf = self._build_emf(name, value, unit, dimensions)
                print(json.dumps(emf), flush=True)
        except Exception:
            pass  # fire-and-forget (NFR-003)
        finally:
            self._pending.clear()

    def _build_emf(
        self,
        name: str,
        value: float,
        unit: str,
        dimensions: Optional[Dict[str, str]],
    ) -> dict:
        dim_keys = list(dimensions.keys()) if dimensions else []
        emf = {
            "_aws": {
                "Timestamp": int(time.time() * 1000),
                "CloudWatchMetrics": [
                    {
                        "Namespace": self._namespace,
                        "Dimensions": [dim_keys] if dim_keys else [[]],
                        "Metrics": [{"Name": name, "Unit": unit}],
                    }
                ],
            },
            name: value,
        }
        if dimensions:
            emf.update(dimensions)
        return emf
