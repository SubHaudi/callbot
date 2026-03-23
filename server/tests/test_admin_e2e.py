"""Admin API E2E Tests — CloudFront 라이브 엔드포인트 직접 호출."""
from __future__ import annotations

import os
import pytest
import requests

BASE_URL = os.environ.get("E2E_BASE_URL", "https://d2hlklbiox15zw.cloudfront.net")

skip_no_e2e = pytest.mark.skipif(
    os.environ.get("RUN_E2E") != "1",
    reason="E2E disabled (set RUN_E2E=1)"
)


# ── List API ──────────────────────────────────

@skip_no_e2e
def test_list_calls_returns_200():
    resp = requests.get(f"{BASE_URL}/api/v1/admin/calls", timeout=10)
    assert resp.status_code == 200
    data = resp.json()
    assert "calls" in data
    assert "total" in data
    assert isinstance(data["calls"], list)
    assert data["total"] >= 0


@skip_no_e2e
def test_list_calls_pagination():
    resp = requests.get(f"{BASE_URL}/api/v1/admin/calls?page=1&per_page=5", timeout=10)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["calls"]) <= 5
    assert data["page"] == 1
    assert data["per_page"] == 5


@skip_no_e2e
def test_list_calls_search_by_caller_id():
    """caller_id 검색 — 010으로 검색하면 결과 반환."""
    resp = requests.get(f"{BASE_URL}/api/v1/admin/calls?search=010", timeout=10)
    assert resp.status_code == 200
    data = resp.json()
    # 010이 포함된 caller_id가 있으면 결과가 나와야 함
    assert isinstance(data["calls"], list)


@skip_no_e2e
def test_list_calls_search_nonexistent():
    """존재하지 않는 검색어."""
    resp = requests.get(f"{BASE_URL}/api/v1/admin/calls?search=NONEXISTENT_XYZ_999", timeout=10)
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


@skip_no_e2e
def test_list_calls_filter_resolution():
    resp = requests.get(f"{BASE_URL}/api/v1/admin/calls?resolution=unknown", timeout=10)
    assert resp.status_code == 200
    for c in resp.json()["calls"]:
        assert c["resolution"] == "unknown"


# ── Detail API ────────────────────────────────

@skip_no_e2e
def test_detail_404():
    resp = requests.get(f"{BASE_URL}/api/v1/admin/calls/nonexistent-session-id", timeout=10)
    assert resp.status_code == 404


@skip_no_e2e
def test_detail_existing_session():
    """목록에서 첫 번째 세션 상세 조회."""
    list_resp = requests.get(f"{BASE_URL}/api/v1/admin/calls?per_page=1", timeout=10)
    calls = list_resp.json()["calls"]
    if not calls:
        pytest.skip("No sessions in DB")
    sid = calls[0]["session_id"]
    resp = requests.get(f"{BASE_URL}/api/v1/admin/calls/{sid}", timeout=10)
    assert resp.status_code == 200
    data = resp.json()
    assert data["session"]["session_id"] == sid
    assert "turns" in data
    assert isinstance(data["turns"], list)
    assert "call_summary" in data


# ── Stats API ─────────────────────────────────

@skip_no_e2e
def test_stats_returns_valid_structure():
    resp = requests.get(f"{BASE_URL}/api/v1/admin/stats?days=30", timeout=10)
    assert resp.status_code == 200
    data = resp.json()
    for key in ("total_calls", "resolution_rate", "avg_turns", "avg_duration_seconds", "daily"):
        assert key in data
    assert isinstance(data["daily"], list)
    assert isinstance(data["total_calls"], int)
    assert 0 <= data["resolution_rate"] <= 1


@skip_no_e2e
def test_intents_returns_valid_structure():
    resp = requests.get(f"{BASE_URL}/api/v1/admin/stats/intents", timeout=10)
    assert resp.status_code == 200
    data = resp.json()
    assert "intents" in data
    assert isinstance(data["intents"], list)


# ── Dashboard HTML ────────────────────────────

@skip_no_e2e
def test_admin_dashboard_html():
    resp = requests.get(f"{BASE_URL}/admin", timeout=10)
    assert resp.status_code == 200
    assert "Callbot Admin" in resp.text
    assert "Chart.js" in resp.text or "chart.js" in resp.text
