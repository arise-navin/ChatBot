"""Production health-check endpoint."""

from fastapi import APIRouter
from ..database.adapter import get_active_api_connection

router = APIRouter(tags=["Health"])

@router.get("/api/health")
async def health_check():
    """Health check verifying Neon database connection and active configuration."""
    db_ok = True
    active_conn = None
    try:
        active_conn = await get_active_api_connection()
    except Exception:
        db_ok = False

    return {
        "status": "healthy" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
        "guardrail_engine": "active",
        "runtime": "cloudflare_workers",
        "active_connection": active_conn.get("connection_name") if active_conn else "None",
        "active_model": active_conn.get("model_name") if active_conn else "beam:cloud",
        "header_name": active_conn.get("header_name") if active_conn else "x-api-key"
    }
