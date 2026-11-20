"""Async Ollama Cloud AI execution client with Signet identity and safety guardrails."""

import logging
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit, urlunsplit
import httpx

from ..config import get_setting, required_setting
from ..database.adapter import (
    get_active_api_connection,
    is_session_aborted,
    evaluate_content_guardrails,
    log_ai_tracking,
)
from ..security.signet import (
    get_workload_token,
    signet_refusal,
    refusal_message,
)

logger = logging.getLogger(__name__)

def ollama_chat_url(base_url: str) -> str:
    """Formats upstream chat endpoint URL, accepting server root or /api/chat."""
    parsed = urlsplit(base_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("AI endpoint URL must be an HTTP(S) address without a query or fragment.")
    path = parsed.path.rstrip("/")
    if path != "/api/chat":
        if path and path != "":
            raise ValueError("Endpoint URL must be a server base URL or end in /api/chat.")
        path = "/api/chat"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))

async def get_dynamic_config() -> Dict[str, Any]:
    """Retrieves dynamic LLM and tracking connection settings."""
    active_conn = await get_active_api_connection()
    
    # Check if Signet gateway is configured
    signet_gateway = get_setting("SIGNET_GATEWAY_URL")
    if signet_gateway:
        base_url = ollama_chat_url(signet_gateway)
        api_key = await get_workload_token()
    else:
        # Fallback to direct Ollama Cloud
        base_url = ollama_chat_url(get_setting("OLLAMA_BASE_URL", "https://ollama.com/api/chat"))
        api_key = get_setting("OLLAMA_API_KEY", "")

    model = get_setting("OLLAMA_MODEL", "beam:cloud")

    return {
        "model": model,
        "api_key": api_key,
        "base_url": base_url,
        "enable_external_tracking": bool(active_conn and active_conn.get("enable_external_tracking")),
        "external_tracking_url": active_conn.get("external_tracking_url") if active_conn else None,
        "header_name": active_conn.get("header_name", "x-api-key") if active_conn else "x-api-key",
        "api_token": active_conn.get("api_token", "") if active_conn else "",
    }

async def dispatch_external_tracking(url: str, header_name: str, token: str, payload: dict) -> None:
    """Sends AI agent tracking payload to an external REST API endpoint asynchronously."""
    if not url:
        return
    try:
        headers = {header_name: token, "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=4.0) as client:
            await client.post(url, headers=headers, json=payload)
    except Exception as exc:
        logger.debug("External tracking dispatch failed: %s", exc)

async def call_ollama(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    session_id: str = "default",
    source: str = "web_ui",
    client_ip: Optional[str] = None,
    agent_name: str = "beam-agent-1",
    action: str = "chat_completion",
    step_number: int = 1,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Executes an AI agent call to Ollama beam:cloud.
    Includes active pre-delivery guardrail evaluation and abort check to prevent bad results.
    """
    # 1. Check if session was aborted via REST API
    if await is_session_aborted(session_id):
        return {
            "success": False,
            "intercepted": True,
            "error": "Agent execution halted by REST API stop signal.",
            "content": "🛑 [STOPPED] Agent was terminated by REST API before generating a response.",
            "status": "aborted",
            "agent_name": agent_name,
            "model": model or "beam:cloud"
        }

    config = await get_dynamic_config()
    target_model = model or config["model"]
    target_api_key = api_key or config["api_key"]
    target_base_url = base_url or config["base_url"]

    headers = {
        "Authorization": f"Bearer {target_api_key}",
        "Content-Type": "application/json",
        "x-signet-session": session_id,
    }

    payload = {
        "model": target_model,
        "messages": messages,
        "stream": False
    }

    last_user_prompt = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user_prompt = m.get("content", "")
            break

    start_time = time.time()
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(target_base_url, headers=headers, json=payload)
            elapsed_ms = (time.time() - start_time) * 1000

        # Check again if session was aborted while request was in-flight
        if await is_session_aborted(session_id):
            return {
                "success": False,
                "intercepted": True,
                "error": "Agent execution halted by REST API stop signal.",
                "content": "🛑 [STOPPED] Agent was terminated by REST API before generating a response.",
                "status": "aborted",
                "agent_name": agent_name,
                "model": target_model
            }

        # Check HTTP error status
        if response.status_code != 200:
            resp_json = {}
            try:
                resp_json = response.json()
            except Exception:
                pass

            refusal = signet_refusal(dict(response.headers), resp_json)
            err_msg = f"API error {response.status_code}: {response.text}"
            
            await log_ai_tracking(
                session_id=session_id,
                model=target_model,
                prompt=last_user_prompt,
                response="",
                thinking="",
                total_duration_ms=elapsed_ms,
                prompt_eval_count=0,
                eval_count=0,
                status="intercepted" if refusal else "error",
                error_message=err_msg,
                source=source,
                client_ip=client_ip,
                agent_name=agent_name,
                action=action,
                step_number=step_number,
                metadata=metadata
            )

            if refusal:
                return {
                    "success": False,
                    "blocked_by": "signet",
                    "http_status": response.status_code,
                    "error": refusal_message(refusal),
                    "code": refusal.code,
                    "record_id": refusal.record_id,
                    "status": "intercepted"
                }

            return {
                "success": False,
                "error": err_msg,
                "status": "error"
            }

        data = response.json()
        message = data.get("message", {})
        raw_content = message.get("content", "")
        thinking = message.get("thinking", "")
        prompt_eval_count = data.get("prompt_eval_count", 0)
        eval_count = data.get("eval_count", 0)

        # 2. Evaluate Guardrails on Content and Thinking trace BEFORE delivery
        guardrail_result = await evaluate_content_guardrails(raw_content, thinking)
        is_safe = guardrail_result["is_safe"]
        
        final_content = raw_content
        final_status = "success"
        is_intercepted = False

        if not is_safe:
            is_intercepted = True
            final_status = "intercepted"
            final_content = guardrail_result["fallback_message"]
            logger.warning(
                "AI Agent output intercepted by guardrail '%s'. Pattern matched: %s",
                guardrail_result['rule_name'], guardrail_result['matched_text']
            )

        # 3. Log execution trace to Neon PostgreSQL
        logged = await log_ai_tracking(
            session_id=session_id,
            model=target_model,
            prompt=last_user_prompt,
            response=final_content,
            thinking=thinking,
            total_duration_ms=elapsed_ms,
            prompt_eval_count=prompt_eval_count,
            eval_count=eval_count,
            status=final_status,
            error_message=f"Intercepted by guardrail: {guardrail_result['rule_name']}" if is_intercepted else None,
            source=source,
            client_ip=client_ip,
            agent_name=agent_name,
            action=action,
            step_number=step_number,
            metadata=metadata
        )

        # 4. Dispatch external tracking if configured
        if config["enable_external_tracking"] and config["external_tracking_url"]:
            await dispatch_external_tracking(
                config["external_tracking_url"],
                config["header_name"],
                config["api_token"],
                logged
            )

        return {
            "success": True,
            "content": final_content,
            "raw_content": raw_content,
            "thinking": thinking,
            "total_duration_ms": elapsed_ms,
            "prompt_eval_count": prompt_eval_count,
            "eval_count": eval_count,
            "model": target_model,
            "agent_name": agent_name,
            "intercepted": is_intercepted,
            "rule_name": guardrail_result.get("rule_name"),
            "matched_text": guardrail_result.get("matched_text"),
            "status": final_status,
            "metadata": metadata
        }

    except Exception as exc:
        elapsed_ms = (time.time() - start_time) * 1000
        await log_ai_tracking(
            session_id=session_id,
            model=target_model,
            prompt=last_user_prompt,
            response="",
            thinking="",
            total_duration_ms=elapsed_ms,
            prompt_eval_count=0,
            eval_count=0,
            status="error",
            error_message=str(exc),
            source=source,
            client_ip=client_ip,
            agent_name=agent_name,
            action=action,
            step_number=step_number,
            metadata=metadata
        )
        return {
            "success": False,
            "error": str(exc),
            "status": "error"
        }
