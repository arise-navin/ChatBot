"""AI Agent tracking logs and analytics routes."""

from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from ..database.adapter import (
    log_ai_tracking,
    get_ai_tracking_logs,
    get_ai_tracking_stats
)
from ..security.auth import verify_dynamic_api_key

router = APIRouter(tags=["Tracking"])

class DynamicTrackRequest(BaseModel):
    session_id: Optional[str] = "external"
    agent_name: Optional[str] = "External-Agent"
    action: Optional[str] = "custom_action"
    step_number: Optional[int] = 1
    model: Optional[str] = "beam:cloud"
    prompt: str
    response: str
    thinking: Optional[str] = None
    total_duration_ms: Optional[float] = 0.0
    prompt_eval_count: Optional[int] = 0
    eval_count: Optional[int] = 0
    status: Optional[str] = "success"
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

@router.post("/api/track", dependencies=[Depends(verify_dynamic_api_key)])
async def track_agent_action(data: DynamicTrackRequest, request: Request):
    """
    Dynamic Tracking Endpoint:
    Tracks any AI Agent action, step, reasoning trace, and metrics into Neon PostgreSQL.
    """
    client_ip = request.client.host if request.client else None
    logged = await log_ai_tracking(
        session_id=data.session_id or "external",
        model=data.model or "beam:cloud",
        prompt=data.prompt,
        response=data.response,
        thinking=data.thinking,
        total_duration_ms=data.total_duration_ms,
        prompt_eval_count=data.prompt_eval_count,
        eval_count=data.eval_count,
        status=data.status,
        error_message=data.error_message,
        source="external_rest_api",
        client_ip=client_ip,
        agent_name=data.agent_name,
        action=data.action,
        step_number=data.step_number,
        metadata=data.metadata
    )
    return {"status": "tracked", "log": logged}

@router.get("/api/tracking/logs", dependencies=[Depends(verify_dynamic_api_key)])
async def list_tracking_logs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    source: Optional[str] = None,
    agent_name: Optional[str] = None,
    status: Optional[str] = None
):
    """Dynamically queries AI Agent tracking logs from Neon PostgreSQL."""
    logs = await get_ai_tracking_logs(
        limit=limit,
        offset=offset,
        source=source,
        agent_name=agent_name,
        status=status
    )
    return {"total": len(logs), "logs": logs}

@router.get("/api/tracking/stats", dependencies=[Depends(verify_dynamic_api_key)])
async def get_tracking_stats():
    """Returns dynamic AI agent tracking analytics from Neon PostgreSQL."""
    return await get_ai_tracking_stats()
