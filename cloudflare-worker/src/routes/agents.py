"""Remote Management Actions (Agents Protocol matching UI specifications)."""

import json
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from ..database.adapter import (
    list_registered_agents,
    get_or_create_registered_agent,
    get_agent_tracking_metrics,
    get_ai_tracking_logs,
    update_agent_status,
    is_session_aborted,
    set_session_aborted,
    reset_session_aborted
)
from ..services.ollama import call_ollama

router = APIRouter(tags=["Remote Agents"])

class RemoteAgentRunRequest(BaseModel):
    input: Optional[Any] = None
    prompt: Optional[str] = None
    messages: Optional[List[Dict[str, Any]]] = None
    action: Optional[str] = "remote_run"
    metadata: Optional[Dict[str, Any]] = None

@router.get("/agents")
@router.get("/api/agents")
async def test_and_discover_agents():
    """
    Implements 'test' and 'discover' actions (GET /agents).
    Returns registered agents and the top-level 'agent' object for JSON pointer /agent.
    """
    agents_list = await list_registered_agents()
    primary = agents_list[0] if agents_list else {
        "id": "beam-agent-1",
        "name": "Beam Cloud AI Agent",
        "description": "Production reasoning agent powered by Ollama beam:cloud",
        "model": "beam:cloud",
        "status": "active"
    }
    return {
        "status": "success",
        "count": len(agents_list),
        "agents": agents_list,
        "agent": primary
    }

@router.get("/agents/{agent_id}/track")
@router.get("/api/agents/{agent_id}/track")
async def track_agent_endpoint(agent_id: str):
    """
    Implements 'track' action (GET /agents/{id}/track).
    Returns real-time status and tracking metrics for the agent.
    """
    agent_info = await get_or_create_registered_agent(agent_id)
    metrics = await get_agent_tracking_metrics(agent_id)
    aborted = await is_session_aborted(agent_id)
    status_val = "stopped" if aborted else agent_info.get("status", "active")

    agent_obj = {
        "id": agent_id,
        "name": agent_info.get("name"),
        "status": status_val,
        "model": agent_info.get("model", "beam:cloud"),
        "total_executions": metrics.get("total_executions", 0),
        "avg_latency_ms": metrics.get("avg_latency_ms", 0),
        "total_tokens": metrics.get("total_tokens", 0)
    }
    return {
        "status": "success",
        "agentId": agent_id,
        "state": status_val,
        "metrics": metrics,
        "agent": agent_obj
    }

@router.get("/agents/executions")
@router.get("/api/agents/executions")
async def get_agent_executions_endpoint(agentId: Optional[str] = Query(None), limit: int = 50):
    """
    Implements 'executions' action (GET /agents/executions?agentId={id}).
    Returns execution history and tracking logs for the agent.
    """
    target_id = agentId or "beam-agent-1"
    logs = await get_ai_tracking_logs(limit=limit, agent_name=target_id)
    agent_info = await get_or_create_registered_agent(target_id)

    executions_data = [
        {
            "id": l["id"],
            "agentId": l.get("agent_name"),
            "action": l.get("action"),
            "status": l.get("status"),
            "duration_ms": l.get("total_duration_ms"),
            "prompt": l.get("prompt"),
            "response": l.get("response"),
            "thinking": l.get("thinking"),
            "tokens": (l.get("prompt_eval_count") or 0) + (l.get("eval_count") or 0),
            "timestamp": l.get("created_at")
        } for l in logs
    ]

    return {
        "status": "success",
        "agentId": target_id,
        "count": len(executions_data),
        "executions": executions_data,
        "agent": agent_info
    }

@router.post("/agents/{agent_id}/run")
@router.post("/api/agents/{agent_id}/run")
async def run_remote_agent_endpoint(agent_id: str, request: Request):
    """
    Implements 'run' action (POST /agents/{id}/run).
    Executes task with Ollama beam:cloud, passes through guardrails, and records in Neon DB.
    """
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    prompt = body.get("prompt") or body.get("input")
    messages = body.get("messages")
    if not messages:
        if isinstance(prompt, str) and prompt.strip():
            messages = [{"role": "user", "content": prompt}]
        elif isinstance(prompt, dict):
            messages = [{"role": "user", "content": json.dumps(prompt)}]
        else:
            messages = [{"role": "user", "content": "Execute agent task"}]

    action = body.get("action") or "remote_run"
    metadata = body.get("metadata") or {}

    res = await call_ollama(
        messages=messages,
        session_id=agent_id,
        source="remote_agent_run",
        agent_name=agent_id,
        action=action,
        metadata=metadata
    )

    agent_info = await get_or_create_registered_agent(agent_id)
    if res.get("blocked_by") == "signet":
        raise HTTPException(status_code=res["http_status"], detail={
            "blocked_by": "signet",
            "message": res["error"],
            "code": res["code"],
            "record_id": res["record_id"],
        })
    is_intercepted = res.get("intercepted", False)

    return {
        "status": "intercepted" if is_intercepted else "completed",
        "agentId": agent_id,
        "output": res.get("content"),
        "content": res.get("content"),
        "thinking": res.get("thinking"),
        "duration_ms": res.get("total_duration_ms"),
        "prompt_tokens": res.get("prompt_eval_count"),
        "completion_tokens": res.get("eval_count"),
        "is_intercepted": is_intercepted,
        "agent": agent_info
    }

@router.post("/agents/{agent_id}/pause")
@router.post("/api/agents/{agent_id}/pause")
async def pause_remote_agent_endpoint(agent_id: str):
    """Implements 'pause' action (POST /agents/{id}/pause)."""
    updated = await update_agent_status(agent_id, "paused")
    return {"status": "success", "action": "pause", "agentId": agent_id, "agent": updated}

@router.post("/agents/{agent_id}/stop")
@router.post("/api/agents/{agent_id}/stop")
async def stop_remote_agent_endpoint(agent_id: str):
    """Implements 'stop' action (POST /agents/{id}/stop)."""
    await set_session_aborted(agent_id, reason=f"Stopped via remote management action /agents/{agent_id}/stop")
    updated = await update_agent_status(agent_id, "stopped")
    return {"status": "success", "action": "stop", "agentId": agent_id, "agent": updated}

@router.post("/agents/{agent_id}/activate")
@router.post("/api/agents/{agent_id}/activate")
async def activate_remote_agent_endpoint(agent_id: str):
    """Implements 'activate' action (POST /agents/{id}/activate)."""
    await reset_session_aborted(agent_id)
    updated = await update_agent_status(agent_id, "active")
    return {"status": "success", "action": "activate", "agentId": agent_id, "agent": updated}
