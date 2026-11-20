"""Database operations adapter for Cloudflare Workers using Neon HTTP."""

import json
import re
from typing import Any, Dict, List, Optional
from .neon_http import db_client
from ..config import get_setting

# ----------------- Database Initialization -----------------

async def init_db() -> None:
    """Verifies and initializes required tables in Neon PostgreSQL."""
    # 1. Chat sessions table
    await db_client.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            session_id VARCHAR(64) PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            is_aborted BOOLEAN DEFAULT FALSE,
            abort_reason TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 2. Chat messages table
    await db_client.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id SERIAL PRIMARY KEY,
            session_id VARCHAR(64) REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
            role VARCHAR(32) NOT NULL,
            content TEXT NOT NULL,
            thinking TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 3. Dynamic REST API Connections table
    await db_client.execute("""
        CREATE TABLE IF NOT EXISTS rest_api_connections (
            id SERIAL PRIMARY KEY,
            connection_name VARCHAR(128) NOT NULL,
            base_url VARCHAR(512) NOT NULL,
            auth_api_key TEXT NOT NULL,
            header_name VARCHAR(64) DEFAULT 'x-api-key',
            api_token TEXT NOT NULL,
            host VARCHAR(64) DEFAULT '0.0.0.0',
            port INTEGER DEFAULT 8000,
            model_name VARCHAR(128) DEFAULT 'beam:cloud',
            ollama_base_url VARCHAR(512),
            enable_external_tracking BOOLEAN DEFAULT FALSE,
            external_tracking_url VARCHAR(512),
            description TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            metadata JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 4. Dynamic AI Agent Tracking logs
    await db_client.execute("""
        CREATE TABLE IF NOT EXISTS ai_tracking_logs (
            id SERIAL PRIMARY KEY,
            session_id VARCHAR(64),
            agent_name VARCHAR(128) DEFAULT 'beam-agent-1',
            action VARCHAR(128) DEFAULT 'chat_completion',
            step_number INTEGER DEFAULT 1,
            model VARCHAR(64) NOT NULL,
            prompt TEXT,
            response TEXT,
            thinking TEXT,
            total_duration_ms DOUBLE PRECISION,
            prompt_eval_count INTEGER,
            eval_count INTEGER,
            status VARCHAR(32) DEFAULT 'success',
            error_message TEXT,
            source VARCHAR(32) DEFAULT 'web_ui',
            client_ip VARCHAR(64),
            metadata JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 5. Guardrail & Interceptor Rules table
    await db_client.execute("""
        CREATE TABLE IF NOT EXISTS guardrail_rules (
            id SERIAL PRIMARY KEY,
            rule_name VARCHAR(128) NOT NULL,
            pattern TEXT NOT NULL,
            rule_type VARCHAR(64) DEFAULT 'regex',
            action VARCHAR(32) DEFAULT 'block',
            fallback_message TEXT DEFAULT '⚠️ [INTERCEPTED] Response blocked by REST API Safety Guardrail before reaching user.',
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 6. Registered Remote Agents table
    await db_client.execute("""
        CREATE TABLE IF NOT EXISTS registered_agents (
            id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(128) NOT NULL,
            description TEXT,
            model VARCHAR(64) DEFAULT 'beam:cloud',
            status VARCHAR(32) DEFAULT 'active',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Seed registered agent if empty
    agents_count = await db_client.query("SELECT COUNT(*) as count FROM registered_agents;")
    if int(agents_count[0]["count"]) == 0:
        await db_client.execute("""
            INSERT INTO registered_agents (id, name, description, model, status)
            VALUES ('beam-agent-1', 'Beam Cloud AI Agent', 'Production reasoning agent powered by Ollama beam:cloud', 'beam:cloud', 'active');
        """)

# ----------------- Dynamic REST API Connections -----------------

async def get_active_api_connection() -> Optional[Dict[str, Any]]:
    """Returns the currently active REST API connection profile from Neon PostgreSQL."""
    rows = await db_client.query("SELECT * FROM rest_api_connections WHERE is_active = TRUE ORDER BY updated_at DESC LIMIT 1;")
    if rows:
        return rows[0]
    fallback = await db_client.query("SELECT * FROM rest_api_connections ORDER BY created_at DESC LIMIT 1;")
    if fallback:
        first_row = fallback[0]
        await db_client.execute("UPDATE rest_api_connections SET is_active = TRUE WHERE id = %s;", [first_row["id"]])
        return first_row
    return None

async def set_active_api_connection(conn_id: int) -> Optional[Dict[str, Any]]:
    """Sets a connection profile as the active profile."""
    await db_client.execute("UPDATE rest_api_connections SET is_active = FALSE;")
    res = await db_client.execute(
        "UPDATE rest_api_connections SET is_active = TRUE, updated_at = CURRENT_TIMESTAMP WHERE id = %s RETURNING *;",
        [conn_id]
    )
    return res["rows"][0] if res.get("rows") else None

async def create_api_connection(
    connection_name: str,
    base_url: str,
    auth_api_key: str,
    header_name: str,
    api_token: str,
    host: str = "0.0.0.0",
    port: int = 8000,
    model_name: str = "beam:cloud",
    ollama_base_url: Optional[str] = None,
    enable_external_tracking: bool = False,
    external_tracking_url: Optional[str] = None,
    description: str = "",
    is_active: bool = True,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Creates a new dynamic REST API connection profile."""
    if is_active:
        await db_client.execute("UPDATE rest_api_connections SET is_active = FALSE;")

    res = await db_client.execute("""
        INSERT INTO rest_api_connections (
            connection_name, base_url, auth_api_key, header_name, api_token,
            host, port, model_name, ollama_base_url, enable_external_tracking,
            external_tracking_url, description, is_active, metadata
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *;
    """, [
        connection_name, base_url, auth_api_key, header_name, api_token,
        host, port, model_name, ollama_base_url, enable_external_tracking,
        external_tracking_url, description, is_active, metadata or {}
    ])
    return res["rows"][0]

async def update_api_connection(conn_id: int, **fields) -> Optional[Dict[str, Any]]:
    """Updates fields for a connection profile."""
    if not fields:
        return None
    set_clauses = []
    values = []
    for k, v in fields.items():
        if k == "metadata" and isinstance(v, dict):
            v = json.dumps(v)
        set_clauses.append(f"{k} = %s")
        values.append(v)
    set_clauses.append("updated_at = CURRENT_TIMESTAMP")
    values.append(conn_id)

    sql = f"UPDATE rest_api_connections SET {', '.join(set_clauses)} WHERE id = %s RETURNING *;"
    res = await db_client.execute(sql, values)
    return res["rows"][0] if res.get("rows") else None

async def get_api_connections() -> List[Dict[str, Any]]:
    """Retrieves all connection profiles from Neon DB."""
    return await db_client.query("SELECT * FROM rest_api_connections ORDER BY is_active DESC, updated_at DESC;")

async def delete_api_connection(conn_id: int) -> None:
    """Deletes a connection profile."""
    await db_client.execute("DELETE FROM rest_api_connections WHERE id = %s;", [conn_id])

async def validate_request_credentials(token: str) -> Optional[Dict[str, Any]]:
    """Validates an incoming token against Neon DB active profiles or fallback."""
    if not token:
        return None

    # Check active profiles
    rows = await db_client.query(
        "SELECT * FROM rest_api_connections WHERE is_active = TRUE AND api_token = %s;",
        [token]
    )
    if rows:
        return rows[0]

    # Check any profile matching the token
    rows = await db_client.query("SELECT * FROM rest_api_connections WHERE api_token = %s;", [token])
    if rows:
        return rows[0]

    # Check configured environment token
    env_token = get_setting("REST_API_KEY")
    if env_token and token == env_token:
        latest = await db_client.query("SELECT * FROM rest_api_connections ORDER BY updated_at DESC LIMIT 1;")
        return latest[0] if latest else {"connection_name": "EnvDefault", "api_token": token}

    return None

# ----------------- Dynamic AI Agent Tracking Logs -----------------

async def log_ai_tracking(
    session_id: str,
    model: str,
    prompt: str,
    response: str,
    thinking: Optional[str] = None,
    total_duration_ms: float = 0.0,
    prompt_eval_count: int = 0,
    eval_count: int = 0,
    status: str = "success",
    error_message: Optional[str] = None,
    source: str = "web_ui",
    client_ip: Optional[str] = None,
    agent_name: str = "beam-agent-1",
    action: str = "chat_completion",
    step_number: int = 1,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Records an AI execution step into Neon PostgreSQL."""
    res = await db_client.execute("""
        INSERT INTO ai_tracking_logs (
            session_id, agent_name, action, step_number, model,
            prompt, response, thinking, total_duration_ms,
            prompt_eval_count, eval_count, status, error_message,
            source, client_ip, metadata
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *;
    """, [
        session_id, agent_name, action, step_number, model,
        prompt, response, thinking, total_duration_ms,
        prompt_eval_count, eval_count, status, error_message,
        source, client_ip, metadata or {}
    ])
    return res["rows"][0]

async def get_ai_tracking_logs(
    limit: int = 50,
    offset: int = 0,
    source: Optional[str] = None,
    agent_name: Optional[str] = None,
    status: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Fetches AI tracking logs with dynamic filtering."""
    filters = []
    params = []
    if source:
        filters.append("source = %s")
        params.append(source)
    if agent_name:
        filters.append("agent_name = %s")
        params.append(agent_name)
    if status:
        filters.append("status = %s")
        params.append(status)

    where_str = f"WHERE {' AND '.join(filters)}" if filters else ""
    query_str = f"""
        SELECT * FROM ai_tracking_logs 
        {where_str}
        ORDER BY created_at DESC 
        LIMIT %s OFFSET %s;
    """
    params.extend([limit, offset])
    return await db_client.query(query_str, params)

async def get_ai_tracking_stats() -> Dict[str, Any]:
    """Aggregates AI performance and tracking statistics."""
    rows = await db_client.query("""
        SELECT 
            COUNT(*) as total_requests,
            COUNT(DISTINCT agent_name) as active_agents_count,
            COALESCE(AVG(total_duration_ms), 0) as avg_latency_ms,
            COALESCE(SUM(prompt_eval_count), 0) as total_prompt_tokens,
            COALESCE(SUM(eval_count), 0) as total_completion_tokens,
            COUNT(*) FILTER (WHERE status = 'error') as error_count
        FROM ai_tracking_logs;
    """)
    return rows[0] if rows else {}

# ----------------- Chat Sessions & Messages -----------------

async def get_or_create_session(session_id: str, title: str = "New Chat") -> Dict[str, Any]:
    rows = await db_client.query("SELECT * FROM chat_sessions WHERE session_id = %s;", [session_id])
    if rows:
        return rows[0]
    res = await db_client.execute(
        "INSERT INTO chat_sessions (session_id, title) VALUES (%s, %s) RETURNING *;",
        [session_id, title]
    )
    return res["rows"][0]

async def list_sessions() -> List[Dict[str, Any]]:
    return await db_client.query("SELECT * FROM chat_sessions ORDER BY updated_at DESC;")

async def update_session_title(session_id: str, title: str) -> None:
    await db_client.execute(
        "UPDATE chat_sessions SET title = %s, updated_at = CURRENT_TIMESTAMP WHERE session_id = %s;",
        [title, session_id]
    )

async def delete_session(session_id: str) -> None:
    await db_client.execute("DELETE FROM chat_sessions WHERE session_id = %s;", [session_id])

async def save_chat_message(
    session_id: str,
    role: str,
    content: str,
    thinking: Optional[str] = None
) -> Dict[str, Any]:
    res = await db_client.execute("""
        INSERT INTO chat_messages (session_id, role, content, thinking)
        VALUES (%s, %s, %s, %s)
        RETURNING *;
    """, [session_id, role, content, thinking])
    await db_client.execute(
        "UPDATE chat_sessions SET updated_at = CURRENT_TIMESTAMP WHERE session_id = %s;",
        [session_id]
    )
    return res["rows"][0]

async def get_session_messages(session_id: str) -> List[Dict[str, Any]]:
    return await db_client.query(
        "SELECT * FROM chat_messages WHERE session_id = %s ORDER BY created_at ASC;",
        [session_id]
    )

# ----------------- Guardrail & Emergency Stop Engine -----------------

async def get_guardrail_rules(active_only: bool = False) -> List[Dict[str, Any]]:
    """Retrieves guardrail rules from Neon DB."""
    if active_only:
        return await db_client.query("SELECT * FROM guardrail_rules WHERE is_active = TRUE ORDER BY id ASC;")
    return await db_client.query("SELECT * FROM guardrail_rules ORDER BY is_active DESC, id ASC;")

async def create_guardrail_rule(
    rule_name: str,
    pattern: str,
    rule_type: str = "regex",
    action: str = "block",
    fallback_message: Optional[str] = None
) -> Dict[str, Any]:
    msg = fallback_message or f"⚠️ [INTERCEPTED] Response blocked by Guardrail rule '{rule_name}' before delivery."
    res = await db_client.execute("""
        INSERT INTO guardrail_rules (rule_name, pattern, rule_type, action, fallback_message, is_active)
        VALUES (%s, %s, %s, %s, %s, TRUE)
        RETURNING *;
    """, [rule_name, pattern, rule_type, action, msg])
    return res["rows"][0]

async def toggle_guardrail_rule(rule_id: int, is_active: bool) -> None:
    await db_client.execute("UPDATE guardrail_rules SET is_active = %s WHERE id = %s;", [is_active, rule_id])

async def delete_guardrail_rule(rule_id: int) -> None:
    await db_client.execute("DELETE FROM guardrail_rules WHERE id = %s;", [rule_id])

async def set_session_aborted(session_id: str, reason: str = "Stopped by user/supervisor via REST API") -> None:
    await get_or_create_session(session_id, title=f"Aborted Session: {session_id}")
    await db_client.execute("""
        UPDATE chat_sessions 
        SET is_aborted = TRUE, abort_reason = %s, updated_at = CURRENT_TIMESTAMP
        WHERE session_id = %s;
    """, [reason, session_id])

async def is_session_aborted(session_id: str) -> bool:
    if not session_id:
        return False
    rows = await db_client.query("SELECT is_aborted FROM chat_sessions WHERE session_id = %s;", [session_id])
    if rows and rows[0].get("is_aborted") is not None:
        return bool(rows[0]["is_aborted"])
    return False

async def reset_session_aborted(session_id: str) -> None:
    await db_client.execute(
        "UPDATE chat_sessions SET is_aborted = FALSE, abort_reason = NULL WHERE session_id = %s;",
        [session_id]
    )

async def evaluate_content_guardrails(content: str, thinking: Optional[str] = None) -> Dict[str, Any]:
    """Evaluates content and thinking trace against active guardrail rules before delivery."""
    rules = await get_guardrail_rules(active_only=True)
    text_to_check = f"{content or ''}\n{thinking or ''}"

    for r in rules:
        pat = r["pattern"]
        r_type = r.get("rule_type", "regex")
        matched = False
        matched_str = ""

        if r_type == "keyword":
            keywords = [k.strip().lower() for k in pat.split("|") if k.strip()]
            for kw in keywords:
                if kw in text_to_check.lower():
                    matched = True
                    matched_str = kw
                    break
        else: # regex
            try:
                m = re.search(pat, text_to_check, re.IGNORECASE)
                if m:
                    matched = True
                    matched_str = m.group(0)
            except re.error:
                if pat.lower() in text_to_check.lower():
                    matched = True
                    matched_str = pat

        if matched:
            return {
                "is_safe": False,
                "rule_name": r["rule_name"],
                "action": r.get("action", "block"),
                "matched_text": matched_str,
                "fallback_message": r.get("fallback_message") or f"⚠️ [INTERCEPTED] Flagged by guardrail rule '{r['rule_name']}'."
            }

    return {"is_safe": True, "rule_name": None, "matched_text": None, "fallback_message": None}

# ----------------- Remote Management Actions (Agents Protocol) -----------------

async def get_or_create_registered_agent(agent_id: str = "beam-agent-1", name: str = "Beam Cloud AI Agent") -> Dict[str, Any]:
    rows = await db_client.query("SELECT * FROM registered_agents WHERE id = %s;", [agent_id])
    if rows:
        return rows[0]
    res = await db_client.execute("""
        INSERT INTO registered_agents (id, name, description, model, status)
        VALUES (%s, %s, %s, 'beam:cloud', 'active')
        RETURNING *;
    """, [agent_id, name, f"Remote agent {name}"])
    return res["rows"][0]

async def list_registered_agents() -> List[Dict[str, Any]]:
    rows = await db_client.query("SELECT * FROM registered_agents ORDER BY created_at ASC;")
    if not rows:
        await get_or_create_registered_agent()
        rows = await db_client.query("SELECT * FROM registered_agents ORDER BY created_at ASC;")
    return rows

async def update_agent_status(agent_id: str, status: str) -> Dict[str, Any]:
    res = await db_client.execute("""
        UPDATE registered_agents 
        SET status = %s, updated_at = CURRENT_TIMESTAMP 
        WHERE id = %s 
        RETURNING *;
    """, [status, agent_id])
    if res.get("rows"):
        return res["rows"][0]
    res = await db_client.execute("""
        INSERT INTO registered_agents (id, name, status, model)
        VALUES (%s, %s, %s, 'beam:cloud')
        RETURNING *;
    """, [agent_id, f"Agent-{agent_id}", status])
    return res["rows"][0]

async def get_agent_tracking_metrics(agent_id: str) -> Dict[str, Any]:
    rows = await db_client.query("""
        SELECT 
            COUNT(*) as total_executions,
            COALESCE(AVG(total_duration_ms), 0) as avg_latency_ms,
            COALESCE(SUM(prompt_eval_count), 0) + COALESCE(SUM(eval_count), 0) as total_tokens,
            COUNT(*) FILTER (WHERE status = 'error') as error_count,
            COUNT(*) FILTER (WHERE status = 'intercepted') as intercepted_count
        FROM ai_tracking_logs 
        WHERE agent_name = %s OR session_id = %s;
    """, [agent_id, agent_id])
    return rows[0] if rows else {}
