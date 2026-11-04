import os
import json
import uuid
import secrets
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Depends, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

import database
import ollama_client

load_dotenv()

app = FastAPI(
    title="Dynamic AI Agent, Tracker & Safety Guardrail REST API",
    description="REST API with real-time AI Agent tracking, emergency stop kill-switch, and pre-delivery guardrail interceptor.",
    version="2.1.0"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def verify_dynamic_api_key(request: Request) -> Dict[str, Any]:
    """
    Dynamically authenticates incoming requests against Neon PostgreSQL.
    Inspects all headers dynamically against configured header names and tokens.
    """
    token = None
    for h_name, h_val in request.headers.items():
        if h_name.lower() in ["x-api-key", "api-key", "token"]:
            token = h_val
            break

    if not token and "authorization" in request.headers:
        auth_val = request.headers.get("authorization", "")
        if auth_val.lower().startswith("bearer "):
            token = auth_val[7:].strip()

    if not token:
        token = request.query_params.get("api_key") or request.query_params.get("token")

    matched_conn = database.validate_request_credentials(token)
    if not matched_conn:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Missing or invalid API key / token. Please provide a valid active token."
        )

    return matched_conn

# ----------------- Dynamic Models -----------------

class ChatMessage(BaseModel):
    role: str = Field(..., description="Role: 'user', 'assistant', or 'system'")
    content: str = Field(..., description="Message text content")

class AgentRunRequest(BaseModel):
    messages: List[ChatMessage]
    agent_name: Optional[str] = "Beam-Agent"
    action: Optional[str] = "agent_execution"
    step_number: Optional[int] = 1
    model: Optional[str] = None
    session_id: Optional[str] = None
    save_to_chat: Optional[bool] = True
    metadata: Optional[Dict[str, Any]] = None

class StopAgentRequest(BaseModel):
    session_id: str = Field(..., description="The session_id of the agent to stop")
    reason: Optional[str] = "Stopped by user/supervisor via REST API kill-switch"

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

class GuardrailRuleRequest(BaseModel):
    rule_name: str
    pattern: str
    rule_type: Optional[str] = "regex"
    action: Optional[str] = "block"
    fallback_message: Optional[str] = None

class ConnectionCreateRequest(BaseModel):
    connection_name: Optional[str] = None
    base_url: Optional[str] = None
    auth_api_key: Optional[str] = None
    header_name: Optional[str] = "x-api-key"
    api_token: Optional[str] = None
    model_name: Optional[str] = "beam:cloud"
    ollama_base_url: Optional[str] = None
    enable_external_tracking: Optional[bool] = False
    external_tracking_url: Optional[str] = None
    description: Optional[str] = "Dynamic REST API Connection"
    is_active: Optional[bool] = True
    metadata: Optional[Dict[str, Any]] = None

class ConnectionUpdateRequest(BaseModel):
    connection_name: Optional[str] = None
    base_url: Optional[str] = None
    auth_api_key: Optional[str] = None
    header_name: Optional[str] = None
    api_token: Optional[str] = None
    model_name: Optional[str] = None
    ollama_base_url: Optional[str] = None
    enable_external_tracking: Optional[bool] = None
    external_tracking_url: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None

# ----------------- Dynamic Endpoints -----------------

@app.get("/api/health")
def health_check():
    """Health check verifying live database, guardrail engine, and active configuration."""
    db_ok = True
    active_conn = None
    try:
        active_conn = database.get_active_api_connection()
    except Exception:
        db_ok = False

    return {
        "status": "healthy" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
        "guardrail_engine": "active",
        "active_connection": active_conn.get("connection_name") if active_conn else "None",
        "active_model": active_conn.get("model_name") if active_conn else "beam:cloud",
        "header_name": active_conn.get("header_name") if active_conn else "x-api-key"
    }

@app.post("/api/chat", dependencies=[Depends(verify_dynamic_api_key)])
@app.post("/api/agent/run", dependencies=[Depends(verify_dynamic_api_key)])
def run_agent_workflow(req: AgentRunRequest, request: Request):
    """
    Dynamic AI Agent REST API with Active Guardrail Interceptor:
    Executes task, checks pre-delivery safety guardrails, stops incorrect results,
    and logs the trace to Neon PostgreSQL.
    """
    session_id = req.session_id or f"agent_sess_{uuid.uuid4().hex[:10]}"
    
    # Reset abort state for this session
    database.reset_session_aborted(session_id)

    if req.save_to_chat:
        database.get_or_create_session(session_id, title=f"Agent Run: {req.agent_name}")
        for m in req.messages:
            if m.role == "user":
                database.save_chat_message(session_id, m.role, m.content)

    client_ip = request.client.host if request.client else None
    messages_payload = [{"role": m.role, "content": m.content} for m in req.messages]

    res = ollama_client.call_ollama(
        messages=messages_payload,
        model=req.model,
        session_id=session_id,
        source="rest_api",
        client_ip=client_ip,
        agent_name=req.agent_name or "Beam-Agent",
        action=req.action or "chat_completion",
        step_number=req.step_number or 1,
        metadata=req.metadata or {}
    )

    if not res.get("success"):
        raise HTTPException(status_code=500, detail=res.get("error", "AI Agent step execution failed"))

    # Save final (clean or intercepted) message to database
    if req.save_to_chat:
        database.save_chat_message(
            session_id,
            "assistant",
            res.get("content", ""),
            res.get("thinking")
        )

    # Return structured result
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

@app.post("/api/agent/stop", dependencies=[Depends(verify_dynamic_api_key)])
@app.post("/api/agent/abort", dependencies=[Depends(verify_dynamic_api_key)])
def stop_agent_execution(req: StopAgentRequest):
    """
    Emergency Kill-Switch:
    Signals an active AI agent or session to immediately abort before giving any bad result.
    """
    database.set_session_aborted(req.session_id, req.reason)
    
    # Log the stop event in Neon DB
    database.log_ai_tracking(
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

@app.post("/api/track", dependencies=[Depends(verify_dynamic_api_key)])
def track_agent_action(data: DynamicTrackRequest, request: Request):
    """
    Dynamic Tracking Endpoint:
    Tracks any AI Agent action, step, reasoning trace, and metrics into Neon PostgreSQL.
    """
    client_ip = request.client.host if request.client else None
    logged = database.log_ai_tracking(
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

@app.get("/api/tracking/logs", dependencies=[Depends(verify_dynamic_api_key)])
def list_tracking_logs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    source: Optional[str] = None,
    agent_name: Optional[str] = None,
    status: Optional[str] = None
):
    """Dynamically queries AI Agent tracking logs from Neon PostgreSQL."""
    logs = database.get_ai_tracking_logs(
        limit=limit,
        offset=offset,
        source=source,
        agent_name=agent_name,
        status=status
    )
    return {"total": len(logs), "logs": logs}

@app.get("/api/tracking/stats", dependencies=[Depends(verify_dynamic_api_key)])
def get_tracking_stats():
    """Returns dynamic AI agent tracking analytics from Neon PostgreSQL."""
    return database.get_ai_tracking_stats()

# ----------------- Guardrail Management Endpoints -----------------

@app.get("/api/guardrails", dependencies=[Depends(verify_dynamic_api_key)])
def list_guardrail_rules():
    """Returns all active and configured guardrail rules stored in Neon DB."""
    return database.get_guardrail_rules(active_only=False)

@app.post("/api/guardrails", dependencies=[Depends(verify_dynamic_api_key)])
def add_guardrail_rule(rule: GuardrailRuleRequest):
    """Creates a new guardrail rule dynamically in Neon PostgreSQL."""
    created = database.create_guardrail_rule(
        rule_name=rule.rule_name,
        pattern=rule.pattern,
        rule_type=rule.rule_type or "regex",
        action=rule.action or "block",
        fallback_message=rule.fallback_message
    )
    return {"status": "created", "rule": created}

@app.post("/api/guardrails/{rule_id}/toggle", dependencies=[Depends(verify_dynamic_api_key)])
def toggle_guardrail(rule_id: int, is_active: bool = Query(...)):
    """Enables or disables a guardrail rule."""
    database.toggle_guardrail_rule(rule_id, is_active)
    return {"status": "updated", "rule_id": rule_id, "is_active": is_active}

@app.delete("/api/guardrails/{rule_id}", dependencies=[Depends(verify_dynamic_api_key)])
def delete_guardrail(rule_id: int):
    """Deletes a guardrail rule from Neon DB."""
    database.delete_guardrail_rule(rule_id)
    return {"status": "deleted", "rule_id": rule_id}

# ----------------- Remote Management Actions (Agents Protocol from User Specs) -----------------

class RemoteAgentRunRequest(BaseModel):
    input: Optional[Any] = None
    prompt: Optional[str] = None
    messages: Optional[List[Dict[str, Any]]] = None
    action: Optional[str] = "remote_run"
    metadata: Optional[Dict[str, Any]] = None

@app.get("/agents")
@app.get("/api/agents")
def test_and_discover_agents():
    """
    Implements 'test' and 'discover' actions (GET /agents).
    Returns registered agents and the top-level 'agent' object for JSON pointer /agent.
    """
    agents_list = database.list_registered_agents()
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
        "agent": primary  # Satisfies Tracking agent object JSON pointer: /agent
    }

@app.get("/agents/{agent_id}/track")
@app.get("/api/agents/{agent_id}/track")
def track_agent_endpoint(agent_id: str):
    """
    Implements 'track' action (GET /agents/{id}/track).
    Returns real-time status and tracking metrics for the agent.
    """
    agent_info = database.get_or_create_registered_agent(agent_id)
    metrics = database.get_agent_tracking_metrics(agent_id)
    is_aborted = database.is_session_aborted(agent_id)
    status_val = "stopped" if is_aborted else agent_info.get("status", "active")
    
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

@app.get("/agents/executions")
@app.get("/api/agents/executions")
def get_agent_executions_endpoint(agentId: Optional[str] = Query(None), limit: int = 50):
    """
    Implements 'executions' action (GET /agents/executions?agentId={id}).
    Returns execution history and tracking logs for the agent.
    """
    target_id = agentId or "beam-agent-1"
    logs = database.get_ai_tracking_logs(limit=limit, agent_name=target_id)
    agent_info = database.get_or_create_registered_agent(target_id)

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

@app.post("/agents/{agent_id}/run")
@app.post("/api/agents/{agent_id}/run")
async def run_remote_agent_endpoint(agent_id: str, request: Request):
    """
    Implements 'run' action (POST /agents/{id}/run).
    Executes task with Ollama beam:cloud, passes through guardrails, and records in Neon DB.
    """
    # Accept arbitrary JSON body
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

    res = ollama_client.call_ollama(
        messages=messages,
        session_id=agent_id,
        source="remote_agent_run",
        agent_name=agent_id,
        action=action,
        metadata=metadata
    )

    agent_info = database.get_or_create_registered_agent(agent_id)
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

@app.post("/agents/{agent_id}/pause")
@app.post("/api/agents/{agent_id}/pause")
def pause_remote_agent_endpoint(agent_id: str):
    """
    Implements 'pause' action (POST /agents/{id}/pause).
    Pauses the agent.
    """
    updated = database.update_agent_status(agent_id, "paused")
    return {
        "status": "success",
        "action": "pause",
        "agentId": agent_id,
        "agent": updated
    }

@app.post("/agents/{agent_id}/stop")
@app.post("/api/agents/{agent_id}/stop")
def stop_remote_agent_endpoint(agent_id: str):
    """
    Implements 'stop' action (POST /agents/{id}/stop).
    Stops the agent immediately (Emergency Kill-Switch).
    """
    database.set_session_aborted(agent_id, reason=f"Stopped via remote management action /agents/{agent_id}/stop")
    updated = database.update_agent_status(agent_id, "stopped")
    return {
        "status": "success",
        "action": "stop",
        "agentId": agent_id,
        "agent": updated
    }

@app.post("/agents/{agent_id}/activate")
@app.post("/api/agents/{agent_id}/activate")
def activate_remote_agent_endpoint(agent_id: str):
    """
    Implements 'activate' action (POST /agents/{id}/activate).
    Activates the agent.
    """
    database.reset_session_aborted(agent_id)
    updated = database.update_agent_status(agent_id, "active")
    return {
        "status": "success",
        "action": "activate",
        "agentId": agent_id,
        "agent": updated
    }

# ----------------- Connections Endpoints -----------------

@app.get("/api/connections")
def list_connections():
    """Lists all dynamic REST API connection profiles."""
    return database.get_api_connections()

@app.get("/api/connections/active")
def get_active_connection():
    """Returns the currently active dynamic connection profile."""
    active = database.get_active_api_connection()
    if not active:
        raise HTTPException(status_code=404, detail="No active connection found.")
    return active

@app.post("/api/connections/active/{conn_id}")
def activate_connection(conn_id: int):
    """Dynamically sets the active connection profile in Neon PostgreSQL."""
    database.set_active_api_connection(conn_id)
    return {"status": "activated", "active_connection_id": conn_id}

@app.post("/api/connections/generate")
def generate_connection(req: ConnectionCreateRequest = None):
    """Dynamically generates and registers a new REST API Connection profile."""
    req = req or ConnectionCreateRequest()
    
    random_id = secrets.token_hex(3).upper()
    name = req.connection_name or f"Beam-Tracker-{random_id}"
    base_url = req.base_url or os.getenv("REST_API_BASE_URL", "http://localhost:8000")
    auth_key = req.auth_api_key or os.getenv("OLLAMA_API_KEY", "")
    header = req.header_name or os.getenv("REST_API_HEADER_NAME", "x-api-key")
    token = req.api_token or f"beam_sec_{secrets.token_hex(16)}"
    model = req.model_name or os.getenv("OLLAMA_MODEL", "beam:cloud")
    ollama_url = req.ollama_base_url or os.getenv("OLLAMA_BASE_URL", "https://ollama.com/api/chat")

    created = database.create_api_connection(
        connection_name=name,
        base_url=base_url,
        auth_api_key=auth_key,
        header_name=header,
        api_token=token,
        model_name=model,
        ollama_base_url=ollama_url,
        enable_external_tracking=req.enable_external_tracking or False,
        external_tracking_url=req.external_tracking_url,
        description=req.description or "Dynamic REST connection profile",
        is_active=req.is_active if req.is_active is not None else True,
        metadata=req.metadata or {}
    )
    return {
        "status": "success",
        "connection": created
    }

@app.put("/api/connections/{conn_id}")
def update_connection(conn_id: int, req: ConnectionUpdateRequest):
    """Dynamically updates any field of an existing connection profile."""
    update_data = {k: v for k, v in req.dict().items() if v is not None}
    updated = database.update_api_connection(conn_id, **update_data)
    if not updated:
        raise HTTPException(status_code=404, detail="Connection not found")
    return {"status": "updated", "connection": updated}

@app.delete("/api/connections/{conn_id}")
def delete_connection(conn_id: int):
    """Deletes a connection profile."""
    database.delete_api_connection(conn_id)
    return {"status": "deleted", "id": conn_id}

@app.on_event("startup")
def on_startup():
    database.init_db()
