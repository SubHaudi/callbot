"""Phase D CloudWatch 알람 테스트 (FR-009)."""

from callbot.monitoring.alarms import (
    DEFAULT_ALARMS, AlarmConfig, alarm_to_cloudformation, export_alarms_json
)


class TestCloudWatchAlarms:
    def test_alarm_json_includes_error_rate(self):
        cfn = export_alarms_json()
        resources = cfn["Resources"]
        assert "CallbotHighErrorRate" in resources
        props = resources["CallbotHighErrorRate"]["Properties"]
        assert props["MetricName"] == "intent_failure_total"
        assert props["Threshold"] == 5.0

    def test_alarm_json_includes_llm_cost(self):
        cfn = export_alarms_json()
        resources = cfn["Resources"]
        assert "CallbotLLMCostSpike" in resources
        props = resources["CallbotLLMCostSpike"]["Properties"]
        assert props["MetricName"] == "llm_estimated_cost_usd"
        assert props["Period"] == 3600

    def test_alarm_json_includes_p95_latency(self):
        cfn = export_alarms_json()
        resources = cfn["Resources"]
        assert "CallbotHighP95Latency" in resources
        props = resources["CallbotHighP95Latency"]["Properties"]
        assert "ExtendedStatistic" in props
        assert props["ExtendedStatistic"] == "p95"

    def test_alarm_json_includes_llm_errors(self):
        cfn = export_alarms_json()
        resources = cfn["Resources"]
        assert "CallbotLLMHighErrorRate" in resources

    def test_default_alarms_count(self):
        assert len(DEFAULT_ALARMS) == 4

    def test_custom_alarm(self):
        custom = AlarmConfig(
            name="Custom-Test",
            metric_name="test_metric",
            namespace="Test",
            threshold=99.0,
            comparison="GreaterThanThreshold",
            dimensions={"env": "prod"},
        )
        cfn = alarm_to_cloudformation(custom)
        assert cfn["Properties"]["Dimensions"] == [{"Name": "env", "Value": "prod"}]
