import os
import re
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is missing. Please set it in .env")

def get_connection():
    """Returns a direct psycopg2 connection to Neon PostgreSQL."""
    return psycopg2.connect(DATABASE_URL)

def init_db():
    """Initializes and migrates tables for dynamic AI agent tracking and REST API connections."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # 1. Chat sessions table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    session_id VARCHAR(64) PRIMARY KEY,
                    title VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # 2. Chat messages table
            cur.execute("""
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
            cur.execute("""
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
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ai_tracking_logs (
                    id SERIAL PRIMARY KEY,
                    session_id VARCHAR(64),
                    agent_name VARCHAR(128) DEFAULT 'Beam-Agent',
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
            cur.execute("""
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

            # 6. Registered Remote Agents table (For Remote Management Actions)
            cur.execute("""
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

            cur.execute("SELECT COUNT(*) FROM registered_agents;")
            if cur.fetchone()[0] == 0:
                cur.execute("""
                    INSERT INTO registered_agents (id, name, description, model, status)
                    VALUES ('beam-agent-1', 'Beam Cloud AI Agent', 'Production reasoning agent powered by Ollama beam:cloud', 'beam:cloud', 'active');
                """)

            # Seed default guardrail rules if table is empty
            cur.execute("SELECT COUNT(*) FROM guardrail_rules;")
            if cur.fetchone()[0] == 0:
                default_rules = [
                    (
                        "Destructive SQL Prevention",
                        r"(?i)(DROP\s+TABLE|DROP\s+DATABASE|TRUNCATE\s+TABLE|DELETE\s+FROM\s+\w+\s*;)",
                        "regex",
                        "block",
                        "⚠️ [INTERCEPTED] Potentially destructive SQL query blocked before execution."
                    ),
                    (
                        "Secret & Credential Leakage",
                        r"(?i)(sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{20,}|password\s*[:=]\s*['\"][^'\"]+['\"]|private_key\s*[:=])",
                        "regex",
                        "block",
                        "⚠️ [INTERCEPTED] Potential API key or private credential exposure prevented."
                    ),
                    (
                        "Unsafe Shell Execution",
                        r"(?i)(rm\s+-rf\s+[/~]|format\s+[a-z]:|del\s+/f\s+/s|powershell\s+-enc)",
                        "regex",
                        "block",
                        "⚠️ [INTERCEPTED] Dangerous shell command detected and halted."
                    ),
                    (
                        "Hallucination Flag Indicator",
                        r"(?i)(i am completely guessing|this answer is fabricated|i have no confidence in this fact)",
                        "regex",
                        "block",
                        "⚠️ [INTERCEPTED] Response flagged for potential hallucination and stopped before delivery."
                    )
                ]
                for r_name, r_pat, r_type, r_act, r_msg in default_rules:
                    cur.execute("""
                        INSERT INTO guardrail_rules (rule_name, pattern, rule_type, action, fallback_message, is_active)
                        VALUES (%s, %s, %s, %s, %s, TRUE);
                    """, (r_name, r_pat, r_type, r_act, r_msg))

            # Seed initial connection from environment variables if table is completely empty
            cur.execute("SELECT COUNT(*) FROM rest_api_connections;")
            count = cur.fetchone()[0]
            if count == 0:
                conn_name = os.getenv("REST_API_CONNECTION_NAME", "Default-Beam-Tracker")
                base_url = os.getenv("REST_API_BASE_URL", "http://localhost:8000")
                auth_key = os.getenv("OLLAMA_API_KEY", "")
                header_name = os.getenv("REST_API_HEADER_NAME", "x-api-key")
                token = os.getenv("REST_API_KEY", "")
                host = os.getenv("REST_API_HOST", "0.0.0.0")
                port = int(os.getenv("REST_API_PORT", 8000))
                model_name = os.getenv("OLLAMA_MODEL", "beam:cloud")
                ollama_url = os.getenv("OLLAMA_BASE_URL", "https://ollama.com/api/chat")
                
                cur.execute("""
                    INSERT INTO rest_api_connections 
                    (connection_name, base_url, auth_api_key, header_name, api_token, host, port, model_name, ollama_base_url, is_active, description)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s);
                """, (
                    conn_name, base_url, auth_key, header_name, token, host, port, model_name, ollama_url,
                    "Dynamic REST API & Tracker Configuration initialized in Neon PostgreSQL"
                ))

            conn.commit()
    finally:
        conn.close()

def sync_active_config_to_env(conn_dict: dict):
    """Synchronizes active connection configuration to the single .env file."""
    if not conn_dict:
        return
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    try:
        db_url = os.getenv("DATABASE_URL")
        new_env = f"""# ==============================================================================
# Neon PostgreSQL Database Connection
# ==============================================================================
DATABASE_URL={db_url}

# ==============================================================================
# Ollama Beam:Cloud Model Configuration
# ==============================================================================
OLLAMA_API_KEY={conn_dict.get('auth_api_key', '')}
OLLAMA_BASE_URL={conn_dict.get('ollama_base_url', 'https://ollama.com/api/chat')}
OLLAMA_MODEL={conn_dict.get('model_name', 'beam:cloud')}

# ==============================================================================
# REST API & Tracker Configuration (Neon DB Synced)
# ==============================================================================
REST_API_CONNECTION_NAME={conn_dict.get('connection_name', 'Beam-Tracker')}
REST_API_BASE_URL={conn_dict.get('base_url', 'http://localhost:8000')}
REST_API_HOST={conn_dict.get('host', '0.0.0.0')}
REST_API_PORT={conn_dict.get('port', 8000)}
REST_API_HEADER_NAME={conn_dict.get('header_name', 'x-api-key')}
REST_API_KEY={conn_dict.get('api_token', '')}
"""
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(new_env)
    except Exception as e:
        print("Warning: Could not sync to .env:", e)

# ----------------- Dynamic REST API Connections -----------------

def get_active_api_connection():
    """Dynamically returns the currently active REST API & Tracker configuration from Neon PostgreSQL."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM rest_api_connections WHERE is_active = TRUE ORDER BY updated_at DESC LIMIT 1;")
            row = cur.fetchone()
            if not row:
                cur.execute("SELECT * FROM rest_api_connections ORDER BY created_at DESC LIMIT 1;")
                row = cur.fetchone()
                if row:
                    cur.execute("UPDATE rest_api_connections SET is_active = TRUE WHERE id = %s;", (row["id"],))
                    conn.commit()
            return dict(row) if row else None
    finally:
        conn.close()

def set_active_api_connection(conn_id: int):
    """Dynamically activates a connection profile in Neon DB and syncs to env."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("UPDATE rest_api_connections SET is_active = FALSE;")
            cur.execute("UPDATE rest_api_connections SET is_active = TRUE, updated_at = CURRENT_TIMESTAMP WHERE id = %s RETURNING *;", (conn_id,))
            active_row = cur.fetchone()
            conn.commit()
            if active_row:
                sync_active_config_to_env(dict(active_row))
            return dict(active_row) if active_row else None
    finally:
        conn.close()

def create_api_connection(
    connection_name: str,
    base_url: str,
    auth_api_key: str,
    header_name: str,
    api_token: str,
    host: str = "0.0.0.0",
    port: int = 8000,
    model_name: str = "beam:cloud",
    ollama_base_url: str = None,
    enable_external_tracking: bool = False,
    external_tracking_url: str = None,
    description: str = "",
    is_active: bool = True,
    metadata: dict = None
):
    """Creates a new dynamic REST API & Tracker configuration profile directly in Neon PostgreSQL."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if is_active:
                cur.execute("UPDATE rest_api_connections SET is_active = FALSE;")

            cur.execute("""
                INSERT INTO rest_api_connections (
                    connection_name, base_url, auth_api_key, header_name, api_token,
                    host, port, model_name, ollama_base_url, enable_external_tracking,
                    external_tracking_url, description, is_active, metadata
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *;
            """, (
                connection_name, base_url, auth_api_key, header_name, api_token,
                host, port, model_name, ollama_base_url, enable_external_tracking,
                external_tracking_url, description, is_active, json.dumps(metadata or {})
            ))
            row = dict(cur.fetchone())
            conn.commit()
            
            if is_active:
                sync_active_config_to_env(row)

            return row
    finally:
        conn.close()

def update_api_connection(conn_id: int, **fields):
    """Dynamically updates fields for a connection profile."""
    if not fields:
        return None
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
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
            cur.execute(sql, tuple(values))
            row = cur.fetchone()
            conn.commit()
            
            if row and row.get("is_active"):
                sync_active_config_to_env(dict(row))

            return dict(row) if row else None
    finally:
        conn.close()

def get_api_connections():
    """Retrieves all connection profiles from Neon DB."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM rest_api_connections ORDER BY is_active DESC, updated_at DESC;")
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

def delete_api_connection(conn_id: int):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM rest_api_connections WHERE id = %s;", (conn_id,))
            conn.commit()
    finally:
        conn.close()

def validate_request_credentials(token: str, incoming_header_name: str = None):
    """
    Dynamically checks incoming token against Neon DB connection profiles.
    Returns the matching connection dict if valid, else None.
    """
    if not token:
        return None
        
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM rest_api_connections 
                WHERE is_active = TRUE AND api_token = %s;
            """, (token,))
            row = cur.fetchone()
            if row:
                return dict(row)

            cur.execute("SELECT * FROM rest_api_connections WHERE api_token = %s;", (token,))
            row = cur.fetchone()
            if row:
                return dict(row)

            env_token = os.getenv("REST_API_KEY")
            if env_token and token == env_token:
                cur.execute("SELECT * FROM rest_api_connections ORDER BY updated_at DESC LIMIT 1;")
                latest = cur.fetchone()
                return dict(latest) if latest else {"connection_name": "EnvDefault", "api_token": token}

            return None
    finally:
        conn.close()

# ----------------- Dynamic AI Agent Tracking Logs -----------------

def log_ai_tracking(
    session_id: str,
    model: str,
    prompt: str,
    response: str,
    thinking: str = None,
    total_duration_ms: float = 0.0,
    prompt_eval_count: int = 0,
    eval_count: int = 0,
    status: str = "success",
    error_message: str = None,
    source: str = "web_ui",
    client_ip: str = None,
    agent_name: str = "Beam-Agent",
    action: str = "chat_completion",
    step_number: int = 1,
    metadata: dict = None
):
    """
    Dynamically records every AI Agent execution step into Neon PostgreSQL.
    Tracks agent identity, action, reasoning/thinking, tokens, latency, and flexible metadata.
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO ai_tracking_logs (
                    session_id, agent_name, action, step_number, model,
                    prompt, response, thinking, total_duration_ms,
                    prompt_eval_count, eval_count, status, error_message,
                    source, client_ip, metadata
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *;
            """, (
                session_id, agent_name, action, step_number, model,
                prompt, response, thinking, total_duration_ms,
                prompt_eval_count, eval_count, status, error_message,
                source, client_ip, json.dumps(metadata or {})
            ))
            logged = dict(cur.fetchone())
            conn.commit()
            return logged
    finally:
        conn.close()

def get_ai_tracking_logs(limit: int = 50, offset: int = 0, source: str = None, agent_name: str = None, status: str = None):
    """Fetches AI Agent tracking logs with dynamic filtering."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
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
            query = f"""
                SELECT * FROM ai_tracking_logs 
                {where_str}
                ORDER BY created_at DESC 
                LIMIT %s OFFSET %s;
            """
            params.extend([limit, offset])
            cur.execute(query, tuple(params))
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

def get_ai_tracking_stats():
    """Aggregates live AI Agent performance and tracking metrics."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 
                    COUNT(*) as total_requests,
                    COUNT(DISTINCT agent_name) as active_agents_count,
                    COALESCE(AVG(total_duration_ms), 0) as avg_latency_ms,
                    COALESCE(SUM(prompt_eval_count), 0) as total_prompt_tokens,
                    COALESCE(SUM(eval_count), 0) as total_completion_tokens,
                    COUNT(*) FILTER (WHERE status = 'error') as error_count
                FROM ai_tracking_logs;
            """)
            stats = cur.fetchone()
            return dict(stats) if stats else {}
    finally:
        conn.close()

# ----------------- Chat Sessions & Messages -----------------

def get_or_create_session(session_id: str, title: str = "New Chat"):
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM chat_sessions WHERE session_id = %s;", (session_id,))
            row = cur.fetchone()
            if not row:
                cur.execute(
                    "INSERT INTO chat_sessions (session_id, title) VALUES (%s, %s) RETURNING *;",
                    (session_id, title)
                )
                row = cur.fetchone()
                conn.commit()
            return dict(row)
    finally:
        conn.close()

def list_sessions():
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM chat_sessions ORDER BY updated_at DESC;")
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

def update_session_title(session_id: str, title: str):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE chat_sessions SET title = %s, updated_at = CURRENT_TIMESTAMP WHERE session_id = %s;",
                (title, session_id)
            )
            conn.commit()
    finally:
        conn.close()

def delete_session(session_id: str):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM chat_sessions WHERE session_id = %s;", (session_id,))
            conn.commit()
    finally:
        conn.close()

def save_chat_message(session_id: str, role: str, content: str, thinking: str = None):
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO chat_messages (session_id, role, content, thinking)
                VALUES (%s, %s, %s, %s)
                RETURNING *;
            """, (session_id, role, content, thinking))
            msg = dict(cur.fetchone())
            cur.execute(
                "UPDATE chat_sessions SET updated_at = CURRENT_TIMESTAMP WHERE session_id = %s;",
                (session_id,)
            )
            conn.commit()
            return msg
    finally:
        conn.close()

def get_session_messages(session_id: str):
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM chat_messages WHERE session_id = %s ORDER BY created_at ASC;",
                (session_id,)
            )
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

# ----------------- Dynamic Guardrail & Interceptor Engine -----------------

def get_guardrail_rules(active_only: bool = False):
    """Retrieves all guardrail rules from Neon PostgreSQL."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if active_only:
                cur.execute("SELECT * FROM guardrail_rules WHERE is_active = TRUE ORDER BY id ASC;")
            else:
                cur.execute("SELECT * FROM guardrail_rules ORDER BY is_active DESC, id ASC;")
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

def create_guardrail_rule(
    rule_name: str,
    pattern: str,
    rule_type: str = "regex",
    action: str = "block",
    fallback_message: str = None
):
    """Creates a new guardrail rule dynamically in Neon PostgreSQL."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            msg = fallback_message or f"⚠️ [INTERCEPTED] Response blocked by Guardrail rule '{rule_name}' before delivery."
            cur.execute("""
                INSERT INTO guardrail_rules (rule_name, pattern, rule_type, action, fallback_message, is_active)
                VALUES (%s, %s, %s, %s, %s, TRUE)
                RETURNING *;
            """, (rule_name, pattern, rule_type, action, msg))
            row = dict(cur.fetchone())
            conn.commit()
            return row
    finally:
        conn.close()

def toggle_guardrail_rule(rule_id: int, is_active: bool):
    """Enables or disables a guardrail rule."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE guardrail_rules SET is_active = %s WHERE id = %s;", (is_active, rule_id))
            conn.commit()
    finally:
        conn.close()

def delete_guardrail_rule(rule_id: int):
    """Deletes a guardrail rule from Neon DB."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM guardrail_rules WHERE id = %s;", (rule_id,))
            conn.commit()
    finally:
        conn.close()

def set_session_aborted(session_id: str, reason: str = "Stopped by user/supervisor via REST API"):
    """Emergency abort: Signals that an in-flight session must be stopped immediately."""
    get_or_create_session(session_id, title=f"Aborted Session: {session_id}")
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE chat_sessions 
                SET is_aborted = TRUE, abort_reason = %s, updated_at = CURRENT_TIMESTAMP
                WHERE session_id = %s;
            """, (reason, session_id))
            conn.commit()
    finally:
        conn.close()

def is_session_aborted(session_id: str) -> bool:
    """Checks if an abort signal has been sent for this session."""
    if not session_id:
        return False
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT is_aborted FROM chat_sessions WHERE session_id = %s;", (session_id,))
            row = cur.fetchone()
            return bool(row[0]) if row and row[0] is not None else False
    finally:
        conn.close()

def reset_session_aborted(session_id: str):
    """Resets the abort state for a session to allow new runs."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE chat_sessions SET is_aborted = FALSE, abort_reason = NULL WHERE session_id = %s;", (session_id,))
            conn.commit()
    finally:
        conn.close()

def evaluate_content_guardrails(content: str, thinking: str = None) -> dict:
    """
    Evaluates both the generated content and internal thinking trace against active guardrail rules.
    If a violation is found, returns is_safe=False and interception details BEFORE delivery to the user.
    """
    rules = get_guardrail_rules(active_only=True)
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
                # If invalid regex, fallback to literal search
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

def get_or_create_registered_agent(agent_id: str = "beam-agent-1", name: str = "Beam Cloud AI Agent"):
    """Fetches or registers an agent for remote management actions."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM registered_agents WHERE id = %s;", (agent_id,))
            row = cur.fetchone()
            if not row:
                cur.execute("""
                    INSERT INTO registered_agents (id, name, description, model, status)
                    VALUES (%s, %s, %s, 'beam:cloud', 'active')
                    RETURNING *;
                """, (agent_id, name, f"Remote agent {name}"))
                row = cur.fetchone()
                conn.commit()
            return dict(row)
    finally:
        conn.close()

def list_registered_agents():
    """Returns all registered agents."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM registered_agents ORDER BY created_at ASC;")
            rows = cur.fetchall()
            if not rows:
                get_or_create_registered_agent()
                cur.execute("SELECT * FROM registered_agents ORDER BY created_at ASC;")
                rows = cur.fetchall()
            return [dict(r) for r in rows]
    finally:
        conn.close()

def update_agent_status(agent_id: str, status: str):
    """Updates status for an agent ('active', 'paused', 'stopped')."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                UPDATE registered_agents 
                SET status = %s, updated_at = CURRENT_TIMESTAMP 
                WHERE id = %s 
                RETURNING *;
            """, (status, agent_id))
            row = cur.fetchone()
            if not row:
                cur.execute("""
                    INSERT INTO registered_agents (id, name, status, model)
                    VALUES (%s, %s, %s, 'beam:cloud')
                    RETURNING *;
                """, (agent_id, f"Agent-{agent_id}", status))
                row = cur.fetchone()
            conn.commit()
            return dict(row)
    finally:
        conn.close()

def get_agent_tracking_metrics(agent_id: str):
    """Calculates live tracking statistics for a specific agent."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 
                    COUNT(*) as total_executions,
                    COALESCE(AVG(total_duration_ms), 0) as avg_latency_ms,
                    COALESCE(SUM(prompt_eval_count), 0) + COALESCE(SUM(eval_count), 0) as total_tokens,
                    COUNT(*) FILTER (WHERE status = 'error') as error_count,
                    COUNT(*) FILTER (WHERE status = 'intercepted') as intercepted_count
                FROM ai_tracking_logs 
                WHERE agent_name = %s OR session_id = %s;
            """, (agent_id, agent_id))
            stats = cur.fetchone()
            return dict(stats) if stats else {}
    finally:
        conn.close()
