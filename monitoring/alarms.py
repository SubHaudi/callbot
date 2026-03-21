"""CloudWatch alarm definitions (FR-009)."""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class AlarmConfig:
    name: str
    metric_name: str
    namespace: str
    threshold: float
    comparison: str  # GreaterThanThreshold, LessThanThreshold
    period_seconds: int = 300
    evaluation_periods: int = 1
    statistic: str = "Average"
    dimensions: Dict[str, str] = field(default_factory=dict)
    description: str = ""


# Pre-defined alarms per FR-009
DEFAULT_ALARMS: List[AlarmConfig] = [
    AlarmConfig(
        name="Callbot-HighErrorRate",
        metric_name="intent_failure_total",
        namespace="Callbot/Business",
        threshold=5.0,
        comparison="GreaterThanThreshold",
        statistic="Sum",
        description="Error rate > 5% over 5 minutes",
    ),
    AlarmConfig(
        name="Callbot-HighP95Latency",
        metric_name="total_duration_ms",
        namespace="Callbot/Pipeline",
        threshold=3000.0,
        comparison="GreaterThanThreshold",
        statistic="p95",
        description="P95 latency > 3000ms",
    ),
    AlarmConfig(
        name="Callbot-LLMHighErrorRate",
        metric_name="llm_errors_total",
        namespace="Callbot/LLM",
        threshold=10.0,
        comparison="GreaterThanThreshold",
        statistic="Sum",
        description="LLM error rate > 10%",
    ),
    AlarmConfig(
        name="Callbot-LLMCostSpike",
        metric_name="llm_estimated_cost_usd",
        namespace="Callbot/LLM",
        threshold=0.0,  # TBD — configurable at runtime
        comparison="GreaterThanThreshold",
        statistic="Sum",
        period_seconds=3600,
        description="LLM cost per hour exceeds threshold (TBD)",
    ),
]


def alarm_to_cloudformation(alarm: AlarmConfig) -> dict:
    """Convert an AlarmConfig to CloudFormation JSON."""
    resource = {
        "Type": "AWS::CloudWatch::Alarm",
        "Properties": {
            "AlarmName": alarm.name,
            "AlarmDescription": alarm.description,
            "Namespace": alarm.namespace,
            "MetricName": alarm.metric_name,
            "Statistic": alarm.statistic if alarm.statistic != "p95" else "p95",
            "Period": alarm.period_seconds,
            "EvaluationPeriods": alarm.evaluation_periods,
            "Threshold": alarm.threshold,
            "ComparisonOperator": alarm.comparison,
        },
    }
    if alarm.statistic == "p95":
        resource["Properties"].pop("Statistic")
        resource["Properties"]["ExtendedStatistic"] = "p95"
    if alarm.dimensions:
        resource["Properties"]["Dimensions"] = [
            {"Name": k, "Value": v} for k, v in alarm.dimensions.items()
        ]
    return resource


def export_alarms_json(alarms: List[AlarmConfig] = None) -> dict:
    """Export all alarms as CloudFormation JSON."""
    if alarms is None:
        alarms = DEFAULT_ALARMS
    resources = {}
    for alarm in alarms:
        safe_name = alarm.name.replace("-", "")
        resources[safe_name] = alarm_to_cloudformation(alarm)
    return {"AWSTemplateFormatVersion": "2010-09-09", "Resources": resources}
