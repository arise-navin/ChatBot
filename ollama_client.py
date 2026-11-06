import os
import time
import json
import requests
from typing import TypedDict
from urllib.parse import urlsplit, urlunsplit
from dotenv import load_dotenv
import database
from signet_identity import required_setting, workload_token

load_dotenv()

class AgentConfig(TypedDict):
    model: str
    api_key: str
    base_url: str
    enable_external_tracking: bool
    external_tracking_url: str | None
    header_name: str
    api_token: str


def ollama_chat_url(base_url: str) -> str:
    """Accept a native Ollama endpoint or a server base URL such as Signet's URL."""
    parsed = urlsplit(base_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("SIGNET_GATEWAY_URL must be an HTTP(S) address without a query or fragment")
    path = parsed.path.rstrip("/")
    if path != "/api/chat":
        if path:
            raise ValueError("SIGNET_GATEWAY_URL must be a server URL without /v1, or end in /api/chat")
        path = "/api/chat"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def get_dynamic_config() -> AgentConfig:
    """Use server LLM settings; database profiles configure REST tracking only."""
    active_conn = database.get_active_api_connection()
    return {
        "model": required_setting("OLLAMA_MODEL"),
        "api_key": workload_token(),
        "base_url": ollama_chat_url(required_setting("SIGNET_GATEWAY_URL")),
        "enable_external_tracking": bool(active_conn and active_conn.get("enable_external_tracking")),
        "external_tracking_url": active_conn.get("external_tracking_url") if active_conn else None,
        "header_name": active_conn["header_name"] if active_conn else "x-api-key",
        "api_token": active_conn["api_token"] if active_conn else "",
    }

def dispatch_external_tracking(url: str, header_name: str, token: str, payload: dict):
    """Sends AI agent tracking payload to an external REST API endpoint asynchronously."""
    if not url:
        return
    try:
        headers = {
            header_name: token,
            "Content-Type": "application/json"
        }
        requests.post(url, headers=headers, json=payload, timeout=3)
    except Exception:
        pass

def call_ollama(
    messages: list,
    model: str = None,
    api_key: str = None,
    base_url: str = None,
    session_id: str = "default",
    source: str = "web_ui",
    client_ip: str = None,
    agent_name: str = "beam-agent-1",
    action: str = "chat_completion",
    step_number: int = 1,
    metadata: dict = None
):
    """
    Executes a dynamic AI agent call to Ollama beam:cloud.
    Includes active pre-delivery guardrail evaluation and abort check to stop wrong results.
    """
    # 1. Check if session was aborted via REST API
    if database.is_session_aborted(session_id):
        return {
            "success": False,
            "intercepted": True,
            "error": "Agent execution halted by REST API stop signal.",
            "content": "🛑 [STOPPED] Agent was terminated by REST API before generating a response.",
            "status": "aborted"
        }

    config = get_dynamic_config()
    model = model or config["model"]
    api_key = api_key or config["api_key"]
    base_url = base_url or config["base_url"]

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "x-signet-session": session_id,
    }

    payload = {
        "model": model,
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
        response = requests.post(base_url, headers=headers, json=payload, timeout=90)
        elapsed_ms = (time.time() - start_time) * 1000

        # Check again if session was aborted while request was in-flight
        if database.is_session_aborted(session_id):
            return {
                "success": False,
                "intercepted": True,
                "error": "Agent execution halted by REST API stop signal.",
                "content": "🛑 [STOPPED] Agent was terminated by REST API before generating a response.",
                "status": "aborted"
            }

        if response.status_code != 200:
            err_msg = f"API error {response.status_code}: {response.text}"
            database.log_ai_tracking(
                session_id=session_id,
                model=model,
                prompt=last_user_prompt,
                response="",
                thinking="",
                total_duration_ms=elapsed_ms,
                prompt_eval_count=0,
                eval_count=0,
                status="error",
                error_message=err_msg,
                source=source,
                client_ip=client_ip,
                agent_name=agent_name,
                action=action,
                step_number=step_number,
                metadata=metadata
            )
            return {
                "success": False,
                "error": err_msg,
                "content": "",
                "thinking": "",
                "agent_name": agent_name
            }

        res_json = response.json()
        msg_obj = res_json.get("message", {})
        content = msg_obj.get("content", "")
        thinking = msg_obj.get("thinking", "")
        
        api_duration_ns = res_json.get("total_duration")
        duration_ms = (api_duration_ns / 1_000_000) if api_duration_ns else elapsed_ms
        prompt_eval_count = res_json.get("prompt_eval_count", 0)
        eval_count = res_json.get("eval_count", 0)

        # ----------------- GUARDRAIL EVALUATION BEFORE USER DELIVERY -----------------
        guardrail = database.evaluate_content_guardrails(content, thinking)
        
        if not guardrail["is_safe"]:
            # Intercept and stop the bad result before sending to user!
            err_desc = f"Intercepted by Guardrail '{guardrail['rule_name']}': matched '{guardrail['matched_text']}'"
            meta_copy = dict(metadata or {})
            meta_copy["guardrail_interception"] = guardrail
            meta_copy["original_flagged_content"] = content

            logged = database.log_ai_tracking(
                session_id=session_id,
                model=model,
                prompt=last_user_prompt,
                response=guardrail["fallback_message"],
                thinking=thinking,
                total_duration_ms=duration_ms,
                prompt_eval_count=prompt_eval_count,
                eval_count=eval_count,
                status="intercepted",
                error_message=err_desc,
                source=source,
                client_ip=client_ip,
                agent_name=agent_name,
                action=action,
                step_number=step_number,
                metadata=meta_copy
            )

            return {
                "success": True,
                "intercepted": True,
                "content": guardrail["fallback_message"],
                "thinking": thinking,
                "rule_name": guardrail["rule_name"],
                "matched_text": guardrail["matched_text"],
                "model": model,
                "agent_name": agent_name,
                "total_duration_ms": duration_ms,
                "status": "intercepted"
            }

        # If clean, record as success
        logged = database.log_ai_tracking(
            session_id=session_id,
            model=model,
            prompt=last_user_prompt,
            response=content,
            thinking=thinking,
            total_duration_ms=duration_ms,
            prompt_eval_count=prompt_eval_count,
            eval_count=eval_count,
            status="success",
            source=source,
            client_ip=client_ip,
            agent_name=agent_name,
            action=action,
            step_number=step_number,
            metadata=metadata
        )

        # External REST API tracking forwarder
        if config.get("enable_external_tracking") and config.get("external_tracking_url"):
            dispatch_external_tracking(
                url=config["external_tracking_url"],
                header_name=config["header_name"],
                token=config["api_token"],
                payload=logged
            )

        return {
            "success": True,
            "intercepted": False,
            "content": content,
            "thinking": thinking,
            "model": model,
            "agent_name": agent_name,
            "total_duration_ms": duration_ms,
            "prompt_eval_count": prompt_eval_count,
            "eval_count": eval_count,
            "metadata": metadata,
            "status": "success"
        }

    except Exception as e:
        elapsed_ms = (time.time() - start_time) * 1000
        database.log_ai_tracking(
            session_id=session_id,
            model=model,
            prompt=last_user_prompt,
            response="",
            thinking="",
            total_duration_ms=elapsed_ms,
            prompt_eval_count=0,
            eval_count=0,
            status="error",
            error_message=str(e),
            source=source,
            client_ip=client_ip,
            agent_name=agent_name,
            action=action,
            step_number=step_number,
            metadata=metadata
        )
        return {
            "success": False,
            "error": str(e),
            "content": "",
            "thinking": "",
            "agent_name": agent_name
        }

def stream_ollama(
    messages: list,
    model: str = None,
    api_key: str = None,
    base_url: str = None,
    session_id: str = "default",
    source: str = "web_ui",
    client_ip: str = None,
    agent_name: str = "beam-agent-1",
    action: str = "streaming_chat",
    step_number: int = 1,
    metadata: dict = None
):
    """
    Streaming generator with real-time abort inspection and pre-delivery guardrail interceptor.
    """
    if database.is_session_aborted(session_id):
        yield {
            "type": "intercepted",
            "reason": "Aborted via REST API kill-switch.",
            "content": "🛑 [STOPPED] Agent was terminated by REST API before generating a response."
        }
        return

    config = get_dynamic_config()
    model = model or config["model"]
    api_key = api_key or config["api_key"]
    base_url = base_url or config["base_url"]

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "x-signet-session": session_id,
    }

    payload = {
        "model": model,
        "messages": messages,
        "stream": True
    }

    last_user_prompt = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user_prompt = m.get("content", "")
            break

    start_time = time.time()
    full_content = []
    full_thinking = []
    prompt_eval_count = 0
    eval_count = 0
    api_duration_ms = None

    try:
        response = requests.post(base_url, headers=headers, json=payload, stream=True, timeout=90)
        
        if response.status_code != 200:
            err_msg = f"API error {response.status_code}: {response.text}"
            elapsed_ms = (time.time() - start_time) * 1000
            database.log_ai_tracking(
                session_id=session_id,
                model=model,
                prompt=last_user_prompt,
                response="",
                thinking="",
                total_duration_ms=elapsed_ms,
                prompt_eval_count=0,
                eval_count=0,
                status="error",
                error_message=err_msg,
                source=source,
                client_ip=client_ip,
                agent_name=agent_name,
                action=action,
                step_number=step_number,
                metadata=metadata
            )
            yield {"type": "error", "error": err_msg}
            return

        for line in response.iter_lines():
            # Check abort flag on every chunk
            if database.is_session_aborted(session_id):
                elapsed_ms = (time.time() - start_time) * 1000
                abort_msg = "🛑 [INTERCEPTED] Agent execution stopped mid-stream by REST API kill-switch."
                database.log_ai_tracking(
                    session_id=session_id,
                    model=model,
                    prompt=last_user_prompt,
                    response="".join(full_content),
                    thinking="".join(full_thinking),
                    total_duration_ms=elapsed_ms,
                    status="aborted",
                    error_message="Aborted mid-stream via REST API",
                    source=source,
                    agent_name=agent_name
                )
                yield {"type": "intercepted", "content": abort_msg, "reason": "REST API Abort"}
                return

            if not line:
                continue
            data = json.loads(line.decode("utf-8"))
            msg = data.get("message", {})

            if "thinking" in msg and msg["thinking"]:
                full_thinking.append(msg["thinking"])
                yield {"type": "thinking", "text": msg["thinking"]}

            if "content" in msg and msg["content"]:
                full_content.append(msg["content"])
                yield {"type": "content", "text": msg["content"]}

            if data.get("done"):
                total_ns = data.get("total_duration")
                if total_ns:
                    api_duration_ms = total_ns / 1_000_000
                prompt_eval_count = data.get("prompt_eval_count", 0)
                eval_count = data.get("eval_count", 0)

        elapsed_ms = api_duration_ms or ((time.time() - start_time) * 1000)
        combined_content = "".join(full_content)
        combined_thinking = "".join(full_thinking)

        # ----------------- GUARDRAIL EVALUATION BEFORE USER DELIVERY -----------------
        guardrail = database.evaluate_content_guardrails(combined_content, combined_thinking)
        
        if not guardrail["is_safe"]:
            err_desc = f"Intercepted by Guardrail '{guardrail['rule_name']}': matched '{guardrail['matched_text']}'"
            meta_copy = dict(metadata or {})
            meta_copy["guardrail_interception"] = guardrail
            meta_copy["original_flagged_content"] = combined_content

            database.log_ai_tracking(
                session_id=session_id,
                model=model,
                prompt=last_user_prompt,
                response=guardrail["fallback_message"],
                thinking=combined_thinking,
                total_duration_ms=elapsed_ms,
                prompt_eval_count=prompt_eval_count,
                eval_count=eval_count,
                status="intercepted",
                error_message=err_desc,
                source=source,
                client_ip=client_ip,
                agent_name=agent_name,
                action=action,
                step_number=step_number,
                metadata=meta_copy
            )

            yield {
                "type": "intercepted",
                "content": guardrail["fallback_message"],
                "thinking": combined_thinking,
                "rule_name": guardrail["rule_name"],
                "matched_text": guardrail["matched_text"],
                "total_duration_ms": elapsed_ms
            }
            return

        # Record clean run
        logged = database.log_ai_tracking(
            session_id=session_id,
            model=model,
            prompt=last_user_prompt,
            response=combined_content,
            thinking=combined_thinking,
            total_duration_ms=elapsed_ms,
            prompt_eval_count=prompt_eval_count,
            eval_count=eval_count,
            status="success",
            source=source,
            client_ip=client_ip,
            agent_name=agent_name,
            action=action,
            step_number=step_number,
            metadata=metadata
        )

        if config.get("enable_external_tracking") and config.get("external_tracking_url"):
            dispatch_external_tracking(
                url=config["external_tracking_url"],
                header_name=config["header_name"],
                token=config["api_token"],
                payload=logged
            )

        yield {
            "type": "done",
            "content": combined_content,
            "thinking": combined_thinking,
            "agent_name": agent_name,
            "total_duration_ms": elapsed_ms,
            "prompt_eval_count": prompt_eval_count,
            "eval_count": eval_count
        }

    except Exception as e:
        elapsed_ms = (time.time() - start_time) * 1000
        database.log_ai_tracking(
            session_id=session_id,
            model=model,
            prompt=last_user_prompt,
            response="".join(full_content),
            thinking="".join(full_thinking),
            total_duration_ms=elapsed_ms,
            prompt_eval_count=0,
            eval_count=0,
            status="error",
            error_message=str(e),
            source=source,
            client_ip=client_ip,
            agent_name=agent_name,
            action=action,
            step_number=step_number,
            metadata=metadata
        )
        yield {"type": "error", "error": str(e)}

def test_ollama_connection(api_key: str = None, base_url: str = None, model: str = None):
    """Pings the Ollama Beam Cloud model dynamically."""
    res = call_ollama(
        messages=[{"role": "user", "content": "ping"}],
        model=model,
        api_key=api_key,
        base_url=base_url,
        session_id="ping_test",
        source="connection_test",
        agent_name="Diagnostic-Agent",
        action="ping"
    )
    return res
