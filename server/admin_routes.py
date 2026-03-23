"""callbot.server.admin_routes — 관리자 API 라우터."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
