"""Chat completion, agent execution, and emergency stop routes."""

import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..database.adapter import (
    get_or_create_session,
    save_chat_message,
    reset_session_aborted,
    set_session_aborted,
    log_ai_tracking
)
from ..security.auth import verify_dynamic_api_key
from ..services.ollama import call_ollama

router = APIRouter(tags=["Chat & Agents"])

class ChatMessage(BaseModel):
    role: str = Field(..., description="Role: 'user', 'assistant', or 'system'")
    content: str = Field(..., description="Message text content")

class AgentRunRequest(BaseModel):
    messages: List[ChatMessage]
    agent_name: Optional[str] = "beam-agent-1"
    action: Optional[str] = "agent_execution"
    step_number: Optional[int] = 1
    model: Optional[str] = None
    session_id: Optional[str] = None
    save_to_chat: Optional[bool] = True
    metadata: Optional[Dict[str, Any]] = None

class StopAgentRequest(BaseModel):
    session_id: str = Field(..., description="The session_id of the agent to stop")
    reason: Optional[str] = "Stopped by user/supervisor via REST API kill-switch"

@router.post("/api/chat", dependencies=[Depends(verify_dynamic_api_key)])
@router.post("/api/agent/run", dependencies=[Depends(verify_dynamic_api_key)])
async def run_agent_workflow(req: AgentRunRequest, request: Request):
    """
    Dynamic AI Agent REST API with Active Guardrail Interceptor:
    Executes task, checks pre-delivery safety guardrails, stops incorrect results,
    and logs the trace to Neon PostgreSQL.
    """
    session_id = req.session_id or f"agent_sess_{uuid.uuid4().hex[:10]}"
    
    # Reset abort state for this session
    await reset_session_aborted(session_id)

    if req.save_to_chat:
        await get_or_create_session(session_id, title=f"Agent Run: {req.agent_name}")
        for m in req.messages:
            if m.role == "user":
                await save_chat_message(session_id, m.role, m.content)

    client_ip = request.client.host if request.client else None
    messages_payload = [{"role": m.role, "content": m.content} for m in req.messages]

    res = await call_ollama(
        messages=messages_payload,
        model=req.model,
        session_id=session_id,
        source="rest_api",
        client_ip=client_ip,
        agent_name=req.agent_name or "beam-agent-1",
        action=req.action or "chat_completion",
        step_number=req.step_number or 1,
        metadata=req.metadata or {}
    )

    if not res.get("success"):
        if res.get("blocked_by") == "signet":
            raise HTTPException(status_code=res["http_status"], detail={
                "blocked_by": "signet",
                "message": res["error"],
                "code": res["code"],
                "record_id": res["record_id"],
            })
        raise HTTPException(status_code=500, detail=res.get("error", "AI Agent step execution failed"))

    # Save final (clean or intercepted) message to database
    if req.save_to_chat:
        await save_chat_message(
            session_id,
            "assistant",
            res.get("content", ""),
            res.get("thinking")
        )

    is_intercepted = res.get("intercepted", False)
    return {
        "session_id": session_id,
        "agent_name": res.get("agent_name"),
        "model": res.get("model"),
        "content": res.get("content"),
        "thinking": res.get("thinking"),
        "total_duration_ms": res.get("total_duration_ms"),
        "prompt_tokens": res.get("prompt_eval_count"),
        "completion_tokens": res.get("eval_count"),
        "metadata": res.get("metadata"),
        "status": res.get("status", "success"),
        "is_intercepted": is_intercepted,
        "rule_triggered": res.get("rule_name") if is_intercepted else None,
        "matched_pattern": res.get("matched_text") if is_intercepted else None
    }

@router.post("/api/agent/stop", dependencies=[Depends(verify_dynamic_api_key)])
@router.post("/api/agent/abort", dependencies=[Depends(verify_dynamic_api_key)])
async def stop_agent_execution(req: StopAgentRequest):
    """
    Emergency Kill-Switch:
    Signals an active AI agent or session to immediately abort before giving any bad result.
    """
    await set_session_aborted(req.session_id, req.reason)
    
    # Log the stop event in Neon DB
    await log_ai_tracking(
        session_id=req.session_id,
        model="beam:cloud",
        prompt="",
        response="🛑 [STOPPED] Execution was aborted by supervisor via REST API.",
        status="aborted",
        error_message=req.reason,
        source="rest_api_kill_switch"
    )
    
    return {
        "status": "stopped",
        "session_id": req.session_id,
        "reason": req.reason,
        "message": f"Agent session '{req.session_id}' has been signaled to stop immediately."
    }
