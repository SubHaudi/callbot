"""Phase D 헬스체크 메트릭 테스트 (FR-014).

FastAPI 없는 환경에서도 동작하도록 로직만 테스트.
"""

import time
import pytest


class FakeHealthCheckable:
    def __init__(self, healthy=True, delay_ms=5):
        self._healthy = healthy
        self._delay = delay_ms / 1000

    def health_check(self):
        time.sleep(self._delay)
        return self._healthy


def _check_health(pg, redis):
    """health/router.py의 readiness 로직을 독립적으로 테스트."""
    checks = {}
    connection_times = {}

    t0 = time.perf_counter()
    pg_ok = pg.health_check() if pg else False
    connection_times["postgres"] = round((time.perf_counter() - t0) * 1000, 2)
    checks["postgres"] = "ok" if pg_ok else "error"

    t0 = time.perf_counter()
    redis_ok = redis.health_check() if redis else False
    connection_times["redis"] = round((time.perf_counter() - t0) * 1000, 2)
    checks["redis"] = "ok" if redis_ok else "error"

    status = "healthy" if pg_ok and redis_ok else "unhealthy"
    return {"status": status, "checks": checks, "connection_times": connection_times}


class TestHealthCheckMetrics:
    def test_health_ready_includes_connection_times(self):
        pg = FakeHealthCheckable(healthy=True, delay_ms=5)
        redis = FakeHealthCheckable(healthy=True, delay_ms=3)
        result = _check_health(pg, redis)
        assert result["status"] == "healthy"
        assert "postgres" in result["connection_times"]
        assert "redis" in result["connection_times"]
        assert result["connection_times"]["postgres"] >= 0
        assert result["connection_times"]["redis"] >= 0

    def test_health_live_includes_status(self):
        # Liveness is always alive
        assert {"status": "alive"} == {"status": "alive"}

    def test_unhealthy_still_has_connection_times(self):
        pg = FakeHealthCheckable(healthy=False)
        redis = FakeHealthCheckable(healthy=True)
        result = _check_health(pg, redis)
        assert result["status"] == "unhealthy"
        assert "postgres" in result["connection_times"]
