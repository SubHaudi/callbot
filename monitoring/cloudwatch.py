"""CloudWatchCollector — EMF JSON stdout output for CloudWatch metrics."""

import json
import sys
import time
from typing import Dict, List, Optional


class CloudWatchCollector:
    """Outputs metrics in CloudWatch Embedded Metric Format (EMF) via stdout.

    Uses direct EMF JSON output instead of aws-embedded-metrics SDK
    for broader compatibility (RISK-001 mitigation).
    """

    def __init__(self, namespace: str = "Callbot") -> None:
        self._namespace = namespace
        self._buffer: List[dict] = []

    def increment(
        self,
        name: str,
        value: float = 1,
        dimensions: Optional[Dict[str, str]] = None,
    ) -> None:
        pass  # TODO: TASK-006

    def observe(
        self,
        name: str,
        value: float,
        dimensions: Optional[Dict[str, str]] = None,
    ) -> None:
        pass  # TODO: TASK-006

    def set_gauge(
        self,
        name: str,
        value: float,
        dimensions: Optional[Dict[str, str]] = None,
    ) -> None:
        pass  # TODO: TASK-006
