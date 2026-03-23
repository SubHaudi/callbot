"""callbot.server.admin_routes — 관리자 API 라우터."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def _get_pg(request: Request) -> Any:
    return request.app.state.pg_conn


@router.get("/calls")
def list_calls(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    resolution: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    search: Optional[str] = None,
) -> Dict[str, Any]:
    """통화 목록 조회 (페이지네이션 + 필터)."""
    pg = _get_pg(request)
    conn = pg._acquire_conn()
    try:
        conditions = []  # type: List[str]
        params = []  # type: List[Any]

        if resolution:
            conditions.append("resolution = %s")
            params.append(resolution)
        if date_from:
            conditions.append("start_time >= %s")
            params.append(date_from)
        if date_to:
            conditions.append("start_time <= %s")
            params.append(date_to)
        if search:
            conditions.append("(caller_id ILIKE %s OR call_summary ILIKE %s)")
            params.extend([f"%{search}%", f"%{search}%"])

        where = " AND ".join(conditions)
        where_clause = f"WHERE {where}" if where else ""

        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM conversation_sessions {where_clause}", params)
            total = cur.fetchone()[0]

        offset = (page - 1) * per_page
        with conn.cursor() as cur:
            cur.execute(
                f"""SELECT session_id, caller_id, start_time, end_time,
                           resolution, primary_intent, total_turn_count, call_summary
                    FROM conversation_sessions {where_clause}
                    ORDER BY start_time DESC
                    LIMIT %s OFFSET %s""",
                params + [per_page, offset],
            )
            rows = cur.fetchall()

        calls = [
            {
                "session_id": r[0], "caller_id": r[1],
                "start_time": str(r[2]) if r[2] else None,
                "end_time": str(r[3]) if r[3] else None,
                "resolution": r[4], "primary_intent": r[5],
                "total_turn_count": r[6], "call_summary": r[7],
            }
            for r in rows
        ]
        return {"calls": calls, "total": total, "page": page, "per_page": per_page}
    finally:
        pg._release_conn(conn, close=False)


@router.get("/calls/{session_id}")
def get_call_detail(request: Request, session_id: str) -> Dict[str, Any]:
    """통화 상세 조회 (세션 + 턴 + 요약)."""
    pg = _get_pg(request)
    conn = pg._acquire_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT session_id, caller_id, start_time, end_time,
                          resolution, primary_intent, total_turn_count,
                          call_summary, end_reason
                   FROM conversation_sessions WHERE session_id = %s""",
                (session_id,),
            )
            row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Session not found")

        session = {
            "session_id": row[0], "caller_id": row[1],
            "start_time": str(row[2]) if row[2] else None,
            "end_time": str(row[3]) if row[3] else None,
            "resolution": row[4], "primary_intent": row[5],
            "total_turn_count": row[6], "call_summary": row[7],
            "end_reason": row[8],
        }

        with conn.cursor() as cur:
            cur.execute(
                """SELECT turn_number, user_text, bot_text, intent, action_type, created_at
                   FROM conversation_turns WHERE session_id = %s
                   ORDER BY turn_number""",
                (session_id,),
            )
            turn_rows = cur.fetchall()

        turns = [
            {
                "turn_number": t[0], "user_text": t[1], "bot_text": t[2],
                "intent": t[3], "action_type": t[4],
                "created_at": str(t[5]) if t[5] else None,
            }
            for t in turn_rows
        ]
        return {"session": session, "turns": turns, "call_summary": session["call_summary"]}
    finally:
        pg._release_conn(conn, close=False)


@router.get("/stats")
def get_stats(request: Request, days: int = Query(30, ge=1, le=365)) -> Dict[str, Any]:
    """통계 API."""
    pg = _get_pg(request)
    conn = pg._acquire_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT COUNT(*),
                          COUNT(*) FILTER (WHERE resolution = 'resolved'),
                          AVG(total_turn_count),
                          AVG(EXTRACT(EPOCH FROM (end_time - start_time)))
                   FROM conversation_sessions
                   WHERE start_time >= NOW() - INTERVAL '%s days'""",
                (days,),
            )
            row = cur.fetchone()
            total = row[0] or 0
            resolved = row[1] or 0
            avg_turns = float(row[2] or 0)
            avg_duration = float(row[3] or 0)

        with conn.cursor() as cur:
            cur.execute(
                """SELECT DATE(start_time) as d, COUNT(*),
                          COUNT(*) FILTER (WHERE resolution = 'resolved')
                   FROM conversation_sessions
                   WHERE start_time >= NOW() - INTERVAL '%s days'
                   GROUP BY d ORDER BY d""",
                (days,),
            )
            daily_rows = cur.fetchall()

        daily = [
            {"date": str(r[0]), "count": r[1], "resolved": r[2]}
            for r in daily_rows
        ]
        return {
            "period_days": days,
            "total_calls": total,
            "resolution_rate": round(resolved / total, 2) if total > 0 else 0,
            "avg_turns": round(avg_turns, 1),
            "avg_duration_seconds": round(avg_duration, 0),
            "daily": daily,
        }
    finally:
        pg._release_conn(conn, close=False)


@router.get("/stats/intents")
def get_intent_stats(request: Request) -> Dict[str, Any]:
    """인텐트별 통화 분포 API."""
    pg = _get_pg(request)
    conn = pg._acquire_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT primary_intent, COUNT(*),
                          COUNT(*) FILTER (WHERE resolution = 'resolved')
                   FROM conversation_sessions
                   WHERE primary_intent IS NOT NULL
                   GROUP BY primary_intent ORDER BY COUNT(*) DESC"""
            )
            rows = cur.fetchall()

        intents = [
            {
                "intent": r[0], "count": r[1], "resolved": r[2],
                "resolution_rate": round(r[2] / r[1], 2) if r[1] > 0 else 0,
            }
            for r in rows
        ]
        return {"intents": intents}
    finally:
        pg._release_conn(conn, close=False)
