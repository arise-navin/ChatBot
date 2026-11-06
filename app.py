import os
import uuid
import secrets
import threading
import time
import requests
import streamlit as st
import pandas as pd
from dotenv import load_dotenv

import database
import ollama_client

load_dotenv()

# Initialize Database tables
database.init_db()

# Ensure background REST API server is running dynamically
@st.cache_resource
def ensure_rest_api_running():
    try:
        r = requests.get("http://127.0.0.1:8000/api/health", timeout=0.8)
        if r.status_code == 200:
            return True
    except Exception:
        pass

    def run_uvicorn():
        import uvicorn
        from api import app as fastapi_app
        uvicorn.run(fastapi_app, host="0.0.0.0", port=8000, log_level="warning")

    t = threading.Thread(target=run_uvicorn, daemon=True)
    t.start()
    time.sleep(1.2)
    return True

ensure_rest_api_running()

# Page configuration
st.set_page_config(
    page_title="REST API & Tracker Configuration Console",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
<style>
    .main-header {
        font-size: 1.8rem;
        font-weight: 700;
        margin-bottom: 0.2rem;
        color: #0F172A;
    }
    .sub-header {
        font-size: 0.95rem;
        color: #475569;
        margin-bottom: 1.2rem;
    }
    .status-badge {
        display: inline-block;
        padding: 0.2rem 0.55rem;
        font-size: 0.75rem;
        font-weight: 600;
        border-radius: 9999px;
        background-color: #ECFDF5;
        color: #065F46;
        border: 1px solid #A7F3D0;
    }
    .active-profile-card {
        background-color: #F8FAFC;
        border: 1px solid #94A3B8;
        border-radius: 8px;
        padding: 0.85rem;
        margin-bottom: 1rem;
        font-size: 0.85rem;
    }
    .live-banner {
        background: linear-gradient(135deg, #EFF6FF 0%, #F0FDF4 100%);
        border: 1px solid #BFDBFE;
        border-radius: 8px;
        padding: 1rem;
        margin-bottom: 1.2rem;
    }
</style>
""", unsafe_allow_html=True)

# Fetch dynamic active connection from Neon PostgreSQL
active_conn = database.get_active_api_connection() or {}

# Session state initialization for dynamic form builder
if "cfg_name" not in st.session_state:
    st.session_state.cfg_name = f"Beam-Tracker-{secrets.token_hex(3).upper()}"
if "cfg_base_url" not in st.session_state:
    st.session_state.cfg_base_url = active_conn.get("base_url") or os.getenv("REST_API_BASE_URL", "http://localhost:8000")
if "cfg_auth_key" not in st.session_state:
    st.session_state.cfg_auth_key = active_conn.get("auth_api_key") or os.getenv("OLLAMA_API_KEY", "51a39d42270248a985164610a3bbc422.oPhkCuPaHCEAXGfSDBjZ-RWd")
if "cfg_header_name" not in st.session_state:
    st.session_state.cfg_header_name = active_conn.get("header_name") or os.getenv("REST_API_HEADER_NAME", "x-api-key")
if "cfg_token" not in st.session_state:
    st.session_state.cfg_token = f"beam_sec_{secrets.token_hex(16)}"
if "cfg_host" not in st.session_state:
    st.session_state.cfg_host = active_conn.get("host") or os.getenv("REST_API_HOST", "0.0.0.0")
if "cfg_port" not in st.session_state:
    st.session_state.cfg_port = int(active_conn.get("port") or os.getenv("REST_API_PORT", 8000))
if "cfg_model" not in st.session_state:
    st.session_state.cfg_model = active_conn.get("model_name") or os.getenv("OLLAMA_MODEL", "beam:cloud")
if "cfg_ollama_url" not in st.session_state:
    st.session_state.cfg_ollama_url = active_conn.get("ollama_base_url") or os.getenv("OLLAMA_BASE_URL", "https://ollama.com/api/chat")
if "cfg_enable_ext" not in st.session_state:
    st.session_state.cfg_enable_ext = active_conn.get("enable_external_tracking", False)
if "cfg_ext_url" not in st.session_state:
    st.session_state.cfg_ext_url = active_conn.get("external_tracking_url") or ""
if "cfg_desc" not in st.session_state:
    st.session_state.cfg_desc = "Dynamic REST API & Tracker configuration created from UI"

if "current_session_id" not in st.session_state:
    st.session_state.current_session_id = f"sess_{uuid.uuid4().hex[:10]}"

# Sidebar: System Status, Active Profile, Navigation
with st.sidebar:
    st.markdown("### ⚡ REST API & Tracker")
    st.caption("Dynamic Management • Neon PostgreSQL")
    
    st.markdown("""
        <div>
            <span class="status-badge">🟢 Neon DB Active</span>
            <span class="status-badge">🟢 REST API Online</span>
        </div>
    """, unsafe_allow_html=True)

    # Active profile indicator
    conn_name_display = active_conn.get("connection_name", "Default Tracker")
    model_display = active_conn.get("model_name", "beam:cloud")
    st.markdown(f"""
        <div class="active-profile-card">
            <b>Active REST Connection:</b><br/>
            <code>{conn_name_display}</code><br/>
            <small>Model: <b>{model_display}</b></small><br/>
            <small>Header: <code>{active_conn.get('header_name', 'x-api-key')}</code></small>
        </div>
    """, unsafe_allow_html=True)

    menu = st.radio(
        "Navigation",
        [
            "⚡ REST API & Tracker Configuration",
            "💬 AI Agent Chat Console",
            "🛡️ Agent Guardrails & Interceptor",
            "📊 AI Agent Tracking Logs",
            "🔌 REST API Live Documentation"
        ],
        index=0
    )
    
    st.markdown("---")
    st.markdown("#### 🗂️ Chat Sessions")
    
    if st.button("➕ New Chat Session", use_container_width=True, type="primary"):
        new_id = f"sess_{uuid.uuid4().hex[:10]}"
        st.session_state.current_session_id = new_id
        database.get_or_create_session(new_id, title="New Chat")
        st.rerun()

    # Load sessions from Neon PostgreSQL
    try:
        sessions = database.list_sessions()
        for s in sessions:
            col1, col2 = st.columns([0.82, 0.18])
            is_active = (s["session_id"] == st.session_state.current_session_id)
            btn_label = f"{'👉 ' if is_active else ''}{s['title'][:22]}"
            if col1.button(btn_label, key=f"sess_{s['session_id']}", use_container_width=True):
                st.session_state.current_session_id = s["session_id"]
                st.rerun()
            if col2.button("🗑️", key=f"del_{s['session_id']}"):
                database.delete_session(s["session_id"])
                if s["session_id"] == st.session_state.current_session_id:
                    st.session_state.current_session_id = f"sess_{uuid.uuid4().hex[:10]}"
                st.rerun()
    except Exception as e:
        st.error(f"Error loading sessions: {e}")

# Ensure active session exists in DB
curr_session = database.get_or_create_session(st.session_state.current_session_id)

# ========================================================
# TAB 1: REST API & TRACKER CONFIGURATION (CORE USER REQUEST)
# ========================================================
if menu == "⚡ REST API & Tracker Configuration":
    st.markdown("<div class='main-header'>⚡ REST API & Tracker Configuration</div>", unsafe_allow_html=True)
    st.markdown("<div class='sub-header'>Create dynamic REST API connections and AI tracker settings directly from the UI. Stored in Neon PostgreSQL with full real-time activation.</div>", unsafe_allow_html=True)

    # Live Status Banner
    st.markdown(f"""
        <div class="live-banner">
            <b>🟢 Active Dynamic Configuration in Neon DB:</b><br/>
            • <b>Connection Name:</b> <code>{active_conn.get('connection_name', 'None')}</code> (ID: <code>{active_conn.get('id', 'N/A')}</code>)<br/>
            • <b>Base URL:</b> <code>{active_conn.get('base_url', 'http://localhost:8000')}</code> | <b>Host:Port:</b> <code>{active_conn.get('host', '0.0.0.0')}:{active_conn.get('port', 8000)}</code><br/>
            • <b>Auth Header:</b> <code>{active_conn.get('header_name', 'x-api-key')}</code> | <b>Active Token:</b> <code>{active_conn.get('api_token', 'N/A')[:16]}...</code><br/>
            • <b>Target Model:</b> <code>{active_conn.get('model_name', 'beam:cloud')}</code> | <b>Upstream:</b> <code>{active_conn.get('ollama_base_url', 'https://ollama.com/api/chat')}</code>
        </div>
    """, unsafe_allow_html=True)

    tab_create, tab_manage, tab_verify = st.tabs([
        "🛠️ Create / Update Configuration",
        "📋 Saved Configurations in Neon DB",
        "🧪 Live Test & Full Working Verification"
    ])

    # ----------------- SUB-TAB 1: CREATE DYNAMIC CONFIG -----------------
    with tab_create:
        st.markdown("#### ⚡ Dynamic Configuration Builder")
        st.write("Generate or customize your connection parameters. Everything saved here is immediately written to **Neon PostgreSQL**.")

        # Quick Generator Shortcuts
        gen_col1, gen_col2, gen_col3 = st.columns([0.4, 0.3, 0.3])
        with gen_col1:
            if st.button("🚀 Auto-Generate Complete Working Configuration", type="primary", use_container_width=True):
                st.session_state.cfg_name = f"Beam-Tracker-{secrets.token_hex(3).upper()}"
                st.session_state.cfg_token = f"beam_sec_{secrets.token_hex(16)}"
                st.session_state.cfg_base_url = "http://localhost:8000"
                st.session_state.cfg_header_name = "x-api-key"
                st.session_state.cfg_host = "0.0.0.0"
                st.session_state.cfg_port = 8000
                st.session_state.cfg_model = "beam:cloud"
                st.session_state.cfg_auth_key = os.getenv("OLLAMA_API_KEY", "51a39d42270248a985164610a3bbc422.oPhkCuPaHCEAXGfSDBjZ-RWd")
                st.session_state.cfg_ollama_url = "https://ollama.com/api/chat"
                st.success("Generated fresh configuration parameters below!")
                st.rerun()

        with gen_col2:
            if st.button("🎲 Randomize Name", use_container_width=True):
                st.session_state.cfg_name = f"Beam-Tracker-{secrets.token_hex(3).upper()}"
                st.rerun()

        with gen_col3:
            if st.button("🔑 Generate New Token", use_container_width=True):
                st.session_state.cfg_token = f"beam_sec_{secrets.token_hex(16)}"
                st.rerun()

        st.markdown("---")

        # 1. REST API Connection Name
        f_name = st.text_input(
            "1. REST API Connection Name",
            value=st.session_state.cfg_name,
            help="Descriptive name for this connection profile in Neon DB"
        )
        st.session_state.cfg_name = f_name

        # 2. External API Base URL & Network Host/Port
        col_url1, col_url2, col_url3 = st.columns([0.5, 0.25, 0.25])
        with col_url1:
            f_base_url = st.text_input(
                "2. External API Base URL",
                value=st.session_state.cfg_base_url,
                help="The base endpoint URL of the tracking REST API (e.g. http://localhost:8000)"
            )
            st.session_state.cfg_base_url = f_base_url
        with col_url2:
            f_host = st.text_input("Host", value=st.session_state.cfg_host)
            st.session_state.cfg_host = f_host
        with col_url3:
            f_port = st.number_input("Port", value=st.session_state.cfg_port, min_value=1000, max_value=65535)
            st.session_state.cfg_port = f_port

        # 3. Authentication API Key
        f_auth_key = st.text_input(
            "3. Authentication API Key (Upstream Ollama Cloud Key)",
            value=st.session_state.cfg_auth_key,
            type="password",
            help="API Key for the remote Ollama beam:cloud endpoint"
        )
        st.session_state.cfg_auth_key = f_auth_key

        # 4 & 5. Header Name & API Key / Token
        col_sec1, col_sec2 = st.columns([0.35, 0.65])
        with col_sec1:
            f_header_name = st.text_input(
                "4. API Key Header Name",
                value=st.session_state.cfg_header_name,
                help="Header required from REST callers (default: x-api-key)"
            )
            st.session_state.cfg_header_name = f_header_name
        with col_sec2:
            f_token = st.text_input(
                "5. API Key / Token",
                value=st.session_state.cfg_token,
                help="Secret token validated against incoming requests"
            )
            st.session_state.cfg_token = f_token

        # 6. Model & Ollama URL
        col_mod1, col_mod2 = st.columns(2)
        with col_mod1:
            f_model = st.text_input("Target Model", value=st.session_state.cfg_model)
            st.session_state.cfg_model = f_model
        with col_mod2:
            f_ollama_url = st.text_input("Ollama API Endpoint", value=st.session_state.cfg_ollama_url)
            st.session_state.cfg_ollama_url = f_ollama_url

        # 7. External Tracking Dispatcher
        st.markdown("##### 📡 External AI Tracking Dispatcher (Optional)")
        f_enable_ext = st.checkbox("Forward AI Agent Tracking Events to External REST URL", value=st.session_state.cfg_enable_ext)
        st.session_state.cfg_enable_ext = f_enable_ext

        f_ext_url = st.text_input("External Webhook / Tracking URL", value=st.session_state.cfg_ext_url, placeholder="https://api.myanalytics.com/ai-track")
        st.session_state.cfg_ext_url = f_ext_url

        f_desc = st.text_area("Description / Notes", value=st.session_state.cfg_desc)
        st.session_state.cfg_desc = f_desc

        f_set_active = st.checkbox("Immediately Set as Active Configuration", value=True)

        st.markdown("---")

        # Save Action Button
        save_col1, save_col2 = st.columns([0.5, 0.5])
        with save_col1:
            if st.button("💾 Save Configuration to Neon PostgreSQL & Activate", type="primary", use_container_width=True):
                if not f_name or not f_base_url or not f_token:
                    st.error("Please ensure Connection Name, Base URL, and API Token are provided.")
                else:
                    with st.spinner("Writing configuration to Neon PostgreSQL..."):
                        created = database.create_api_connection(
                            connection_name=f_name,
                            base_url=f_base_url,
                            auth_api_key=f_auth_key,
                            header_name=f_header_name,
                            api_token=f_token,
                            host=f_host,
                            port=int(f_port),
                            model_name=f_model,
                            ollama_base_url=f_ollama_url,
                            enable_external_tracking=f_enable_ext,
                            external_tracking_url=f_ext_url,
                            description=f_desc,
                            is_active=f_set_active
                        )
                    st.success(f"✅ REST API & Tracker Configuration '{f_name}' stored in Neon PostgreSQL (ID: {created['id']})!")
                    time.sleep(1)
                    st.rerun()

        with save_col2:
            if st.button("🧪 Ping REST API with These Details", use_container_width=True):
                try:
                    t0 = time.time()
                    resp = requests.get(
                        f"{f_base_url.rstrip('/')}/api/health",
                        headers={f_header_name: f_token},
                        timeout=5
                    )
                    lat = (time.time() - t0) * 1000
                    st.success(f"Response: {resp.status_code} OK ({lat:.1f} ms)")
                    st.json(resp.json())
                except Exception as ex:
                    st.error(f"Ping failed: {ex}")

    # ----------------- SUB-TAB 2: SAVED CONFIGURATIONS -----------------
    with tab_manage:
        st.markdown("#### 📋 Configurations Stored in Neon PostgreSQL")
        conns = database.get_api_connections()
        if not conns:
            st.info("No connections found in database.")
        else:
            for c in conns:
                is_active = c.get("is_active", False)
                with st.expander(f"{'🟢 [ACTIVE] ' if is_active else '⚪ '}{c['connection_name']} (ID: {c['id']})", expanded=is_active):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.write(f"**Connection Name:** `{c['connection_name']}`")
                        st.write(f"**Base URL:** `{c['base_url']}`")
                        st.write(f"**Header Name:** `{c['header_name']}`")
                        st.write(f"**Host:Port:** `{c.get('host', '0.0.0.0')}:{c.get('port', 8000)}`")
                        st.write(f"**Model:** `{c.get('model_name', 'beam:cloud')}`")
                    with c2:
                        st.write(f"**API Token:** `{c['api_token']}`")
                        st.write(f"**External Tracking:** {'Enabled' if c.get('enable_external_tracking') else 'Disabled'}")
                        if c.get("external_tracking_url"):
                            st.write(f"**External URL:** `{c['external_tracking_url']}`")
                        st.write(f"**Created At:** {c['created_at']}")
                        
                        btn1, btn2, btn3 = st.columns(3)
                        with btn1:
                            if not is_active:
                                if st.button("⚡ Set Active", key=f"activate_{c['id']}", use_container_width=True):
                                    database.set_active_api_connection(c["id"])
                                    st.success(f"Activated '{c['connection_name']}'!")
                                    st.rerun()
                        with btn2:
                            if st.button("✏️ Load into Form", key=f"load_{c['id']}", use_container_width=True):
                                st.session_state.cfg_name = c["connection_name"]
                                st.session_state.cfg_base_url = c["base_url"]
                                st.session_state.cfg_auth_key = c["auth_api_key"]
                                st.session_state.cfg_header_name = c["header_name"]
                                st.session_state.cfg_token = c["api_token"]
                                st.session_state.cfg_host = c.get("host", "0.0.0.0")
                                st.session_state.cfg_port = c.get("port", 8000)
                                st.session_state.cfg_model = c.get("model_name", "beam:cloud")
                                st.session_state.cfg_ollama_url = c.get("ollama_base_url", "https://ollama.com/api/chat")
                                st.session_state.cfg_enable_ext = c.get("enable_external_tracking", False)
                                st.session_state.cfg_ext_url = c.get("external_tracking_url", "")
                                st.session_state.cfg_desc = c.get("description", "")
                                st.success(f"Loaded '{c['connection_name']}' into editor!")
                                st.rerun()
                        with btn3:
                            if st.button("🗑️ Delete", key=f"del_cfg_{c['id']}", use_container_width=True):
                                database.delete_api_connection(c["id"])
                                st.warning("Deleted!")
                                st.rerun()

    # ----------------- SUB-TAB 3: LIVE VERIFICATION -----------------
    with tab_verify:
        st.markdown("#### 🧪 Test & Full Working Verification of Active Configuration")
        st.write("Execute a live AI agent request using the active database configuration to verify the REST API and the Tracker.")

        test_prompt = st.text_input("Test Prompt:", value="Hello Beam Cloud! Confirm you are working.", key="verify_prompt")
        
        if st.button("🚀 Run Live AI Agent Task & Verify Tracking in DB", type="primary"):
            with st.spinner("Sending request to active REST API & Ollama Beam Cloud..."):
                t0 = time.time()
                try:
                    active_base = active_conn.get("base_url", "http://localhost:8000").rstrip("/")
                    active_hdr = active_conn.get("header_name", "x-api-key")
                    active_tok = active_conn.get("api_token", "")
                    
                    resp = requests.post(
                        f"{active_base}/api/agent/run",
                        headers={active_hdr: active_tok, "Content-Type": "application/json"},
                        json={
                            "agent_name": "Live-Verification-Agent",
                            "action": "ui_self_test",
                            "step_number": 1,
                            "messages": [{"role": "user", "content": test_prompt}],
                            "metadata": {"source": "ui_configuration_tester"}
                        },
                        timeout=90
                    )
                    duration_ms = (time.time() - t0) * 1000

                    if resp.status_code == 200:
                        r_data = resp.json()
                        st.success(f"✅ Full Working Test Successful! (HTTP 200 in {duration_ms:.0f} ms)")
                        
                        vc1, vc2 = st.columns(2)
                        with vc1:
                            st.markdown("**AI Agent Output:**")
                            st.write(r_data.get("content"))
                        with vc2:
                            st.markdown("**Reasoning / Thinking Trace:**")
                            st.text(r_data.get("thinking") or "No separate thinking block")

                        st.markdown("##### 🗄️ Verification of Stored Row in Neon PostgreSQL:")
                        logs = database.get_ai_tracking_logs(limit=1, agent_name="Live-Verification-Agent")
                        if logs:
                            st.json(logs[0])
                    else:
                        st.error(f"Test failed with HTTP {resp.status_code}: {resp.text}")

                except Exception as ex:
                    st.error(f"Error executing test: {ex}")

# ========================================================
# TAB 2: AI AGENT CHAT CONSOLE
# ========================================================
elif menu == "💬 AI Agent Chat Console":
    st.markdown(f"<div class='main-header'>💬 AI Agent Chat Console</div>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='sub-header'>Session: <b>{curr_session['title']}</b> | "
        f"Active Config: <code>{active_conn.get('connection_name', 'Default')}</code> | "
        f"Model: <code>{active_conn.get('model_name', 'beam:cloud')}</code> | "
        f"Stored in Neon PostgreSQL.</div>",
        unsafe_allow_html=True
    )

    with st.expander("🤖 Agent Working Parameters", expanded=False):
        c_a1, c_a2, c_a3 = st.columns(3)
        with c_a1:
            agent_name = st.text_input("Agent Name / Identifier", value="Beam-Coding-Agent")
        with c_a2:
            agent_action = st.text_input("Agent Action / Task", value="agent_interactive_chat")
        with c_a3:
            agent_step = st.number_input("Step Number", min_value=1, value=1, step=1)

    messages = database.get_session_messages(st.session_state.current_session_id)

    for msg in messages:
        with st.chat_message(msg["role"]):
            if msg.get("thinking"):
                with st.expander("🧠 AI Agent Reasoning / Thinking Trace", expanded=False):
                    st.markdown(f"```text\n{msg['thinking']}\n```")
            st.markdown(msg["content"])

    if user_prompt := st.chat_input("Enter instruction for the AI agent..."):
        database.save_chat_message(st.session_state.current_session_id, "user", user_prompt)
        
        if len(messages) == 0:
            new_title = (user_prompt[:25] + "...") if len(user_prompt) > 25 else user_prompt
            database.update_session_title(st.session_state.current_session_id, new_title)

        with st.chat_message("user"):
            st.markdown(user_prompt)

        full_history = database.get_session_messages(st.session_state.current_session_id)
        llm_messages = [{"role": m["role"], "content": m["content"]} for m in full_history]

        with st.chat_message("assistant"):
            thinking_placeholder = st.empty()
            content_placeholder = st.empty()
            status_placeholder = st.empty()

            accumulated_content = ""
            accumulated_thinking = ""
            final_metrics = {}

            stream_gen = ollama_client.stream_ollama(
                messages=llm_messages,
                session_id=st.session_state.current_session_id,
                source="web_ui",
                agent_name=agent_name,
                action=agent_action,
                step_number=agent_step,
                metadata={"session_title": curr_session["title"]}
            )

            for chunk in stream_gen:
                if chunk["type"] == "thinking":
                    accumulated_thinking += chunk["text"]
                    with thinking_placeholder.container():
                        with st.expander(f"🧠 Reasoning in Progress ({agent_name})...", expanded=True):
                            st.text(accumulated_thinking)

                elif chunk["type"] == "content":
                    accumulated_content += chunk["text"]
                    content_placeholder.markdown(accumulated_content + "▌")

                elif chunk["type"] == "done":
                    final_metrics = chunk
                    content_placeholder.markdown(accumulated_content)
                    if accumulated_thinking:
                        with thinking_placeholder.container():
                            with st.expander(f"🧠 Reasoning Trace ({agent_name})", expanded=False):
                                st.markdown(f"```text\n{accumulated_thinking}\n```")
                    
                    status_placeholder.caption(
                        f"⚡ Agent: {agent_name} | Latency: {final_metrics.get('total_duration_ms', 0):.0f} ms | "
                        f"Prompt tokens: {final_metrics.get('prompt_eval_count', 0)} | "
                        f"Completion tokens: {final_metrics.get('eval_count', 0)} | "
                        f"Tracked in Neon DB ✅"
                    )

                elif chunk["type"] == "error":
                    st.error(f"Error: {chunk.get('error')}")

                elif chunk["type"] == "intercepted":
                    intercepted_text = chunk.get("content", "⚠️ Response blocked by Safety Guardrail.")
                    content_placeholder.warning(intercepted_text)
                    if chunk.get("rule_name"):
                        status_placeholder.error(f"🛑 Guardrail Triggered: Flagged by '{chunk['rule_name']}' before user delivery.")
                    accumulated_content = intercepted_text

            if accumulated_content:
                database.save_chat_message(
                    st.session_state.current_session_id,
                    "assistant",
                    accumulated_content,
                    accumulated_thinking
                )

# ========================================================
# TAB 3: AGENT GUARDRAILS & INTERCEPTOR (STOPPING BAD RESULTS)
# ========================================================
elif menu == "🛡️ Agent Guardrails & Interceptor":
    st.markdown("<div class='main-header'>🛡️ Agent Guardrail Interceptor & Emergency Kill-Switch</div>", unsafe_allow_html=True)
    st.markdown("<div class='sub-header'>Automatically intercept incorrect, hallucinated, or unsafe responses BEFORE they reach the user, or trigger an emergency abort signal via REST API.</div>", unsafe_allow_html=True)

    all_rules = database.get_guardrail_rules(active_only=False)
    active_rules_count = sum(1 for r in all_rules if r.get("is_active"))
    intercepted_logs = database.get_ai_tracking_logs(limit=200, status="intercepted")
    aborted_logs = database.get_ai_tracking_logs(limit=200, status="aborted")

    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("Active Guardrail Rules", active_rules_count)
    with m2:
        st.metric("Total Intercepted Attempts", len(intercepted_logs))
    with m3:
        st.metric("Emergency Aborts Triggered", len(aborted_logs))

    st.markdown("---")

    g_tab1, g_tab2, g_tab3, g_tab4 = st.tabs([
        "🛑 Emergency Kill-Switch (Stop Agent Now)",
        "📋 Active Guardrail Rules (Neon DB)",
        "➕ Add Custom Guardrail Rule",
        "🚨 Interception History"
    ])

    with g_tab1:
        st.markdown("#### 🛑 Emergency Kill-Switch Console")
        st.write("If an agent is running or generating incorrect information, send a stop signal to terminate it immediately.")

        col_s1, col_s2 = st.columns([0.6, 0.4])
        with col_s1:
            stop_sess_id = st.text_input("Session ID to Abort:", value=st.session_state.current_session_id)
            stop_reason = st.text_input("Abort Reason:", value="Manual stop triggered: potential incorrect result detected")
        with col_s2:
            st.markdown("<br/>", unsafe_allow_html=True)
            if st.button("🛑 STOP & ABORT AGENT IMMEDIATELY", type="primary", use_container_width=True):
                database.set_session_aborted(stop_sess_id, stop_reason)
                database.log_ai_tracking(
                    session_id=stop_sess_id,
                    model=active_conn.get("model_name", "beam:cloud"),
                    prompt="",
                    response="🛑 [STOPPED] Execution was manually terminated by user via Kill-Switch.",
                    status="aborted",
                    error_message=stop_reason,
                    source="ui_kill_switch"
                )
                st.error(f"Agent session '{stop_sess_id}' has been ABORTED!")
                st.rerun()

        if database.is_session_aborted(stop_sess_id):
            st.warning(f"Session '{stop_sess_id}' is currently in ABORTED state.")
            if st.button("🔄 Reset Abort State (Allow New Prompts)"):
                database.reset_session_aborted(stop_sess_id)
                st.success("Session state reset to normal!")
                st.rerun()

    with g_tab2:
        st.markdown("#### 📋 Configured Guardrail Rules in Neon PostgreSQL")
        st.caption("When any rule pattern matches the agent's output or reasoning trace, it is immediately blocked and replaced with the safe fallback message before reaching the user.")

        if not all_rules:
            st.info("No guardrail rules configured.")
        else:
            for r in all_rules:
                r_active = r.get("is_active", False)
                with st.expander(f"{'🟢 [ENABLED] ' if r_active else '⚪ [DISABLED] '}{r['rule_name']} (ID: {r['id']})", expanded=r_active):
                    r_col1, r_col2 = st.columns([0.7, 0.3])
                    with r_col1:
                        st.write(f"**Pattern / Trigger:** `{r['pattern']}`")
                        st.write(f"**Rule Type:** `{r.get('rule_type', 'regex')}` | **Action:** `{r.get('action', 'block')}`")
                        st.write(f"**Safe Fallback Message:** {r.get('fallback_message', '')}")
                    with r_col2:
                        if st.button(f"{'Disable' if r_active else 'Enable'} Rule", key=f"tgl_{r['id']}"):
                            database.toggle_guardrail_rule(r["id"], not r_active)
                            st.rerun()
                        if st.button(f"🗑️ Delete Rule", key=f"del_gr_{r['id']}"):
                            database.delete_guardrail_rule(r["id"])
                            st.rerun()

    with g_tab3:
        st.markdown("#### ➕ Add New Custom Guardrail Rule")
        with st.form("new_guardrail_form"):
            new_r_name = st.text_input("Rule Name", placeholder="e.g. Unverified Speculation Filter")
            new_r_pattern = st.text_input("Pattern / Regex / Keywords", placeholder="e.g. (i am just guessing|unverified rumor|secret_key)")
            new_r_type = st.selectbox("Type", ["regex", "keyword"])
            new_r_action = st.selectbox("Action", ["block", "warn"])
            new_r_fallback = st.text_area(
                "Safe Fallback Message (Shown to user instead of bad output)",
                value="⚠️ [INTERCEPTED] This agent output was intercepted by the Guardrail Interceptor before delivery."
            )

            r_sub = st.form_submit_button("💾 Save Guardrail Rule to Neon DB", type="primary")
            if r_sub:
                if not new_r_name or not new_r_pattern:
                    st.error("Please fill in Rule Name and Pattern.")
                else:
                    database.create_guardrail_rule(
                        rule_name=new_r_name,
                        pattern=new_r_pattern,
                        rule_type=new_r_type,
                        action=new_r_action,
                        fallback_message=new_r_fallback
                    )
                    st.success(f"Guardrail rule '{new_r_name}' saved to Neon PostgreSQL!")
                    time.sleep(1)
                    st.rerun()

    with g_tab4:
        st.markdown("#### 🚨 Intercepted Incidents Log")
        all_intercepted = database.get_ai_tracking_logs(limit=50, status="intercepted")
        if not all_intercepted:
            st.info("No intercepted incidents logged yet. Clean runs!")
        else:
            for inc in all_intercepted:
                with st.expander(f"⚠️ Incident #{inc['id']} - {inc.get('created_at')} ({inc.get('agent_name')})"):
                    st.write(f"**Error / Rule:** {inc.get('error_message')}")
                    st.write(f"**Prompt:** {inc.get('prompt')}")
                    st.write(f"**Delivered Output:** {inc.get('response')}")
                    if inc.get("metadata", {}).get("original_flagged_content"):
                        st.markdown("**Original Blocked Content (Never shown to user):**")
                        st.code(inc["metadata"]["original_flagged_content"], language="text")

# ========================================================
# TAB 4: AI AGENT TRACKING LOGS
# ========================================================
elif menu == "📊 AI Agent Tracking Logs":
    st.markdown("<div class='main-header'>📊 AI Agent Working & Tracking Dashboard</div>", unsafe_allow_html=True)
    st.markdown("<div class='sub-header'>Real-time tracking of AI Agent working steps, reasoning traces, token consumption, and latencies from Neon PostgreSQL.</div>", unsafe_allow_html=True)

    stats = database.get_ai_tracking_stats()
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.metric("Total Agent Calls", stats.get("total_requests", 0))
    with m2:
        st.metric("Active Agents", stats.get("active_agents_count", 0))
    with m3:
        st.metric("Avg Latency", f"{stats.get('avg_latency_ms', 0):.0f} ms")
    with m4:
        st.metric("Total Tokens", (stats.get("total_prompt_tokens", 0) + stats.get("total_completion_tokens", 0)))
    with m5:
        st.metric("Errors", stats.get("error_count", 0))

    st.markdown("---")

    f1, f2, f3, f4 = st.columns([0.25, 0.25, 0.25, 0.25])
    with f1:
        filter_source = st.selectbox("Source", ["All", "web_ui", "rest_api", "external_rest_api", "connection_test"])
    with f2:
        filter_agent = st.text_input("Filter by Agent Name", placeholder="e.g. beam-agent-1")
    with f3:
        filter_status = st.selectbox("Status", ["All", "success", "error"])
    with f4:
        max_rows = st.slider("Max Rows", min_value=10, max_value=200, value=50, step=10)

    src_val = None if filter_source == "All" else filter_source
    stat_val = None if filter_status == "All" else filter_status
    agent_val = filter_agent.strip() if filter_agent.strip() else None

    logs = database.get_ai_tracking_logs(limit=max_rows, source=src_val, agent_name=agent_val, status=stat_val)

    if not logs:
        st.info("No AI Agent tracking logs matching the criteria.")
    else:
        display_cols = ["id", "created_at", "agent_name", "action", "model", "source", "status", "total_duration_ms", "prompt_eval_count", "eval_count"]
        df = pd.DataFrame(logs)
        for col in display_cols:
            if col not in df.columns:
                df[col] = None
        df = df[display_cols]
        df.columns = ["ID", "Timestamp", "Agent Name", "Action", "Model", "Source", "Status", "Latency (ms)", "Prompt Tokens", "Completion Tokens"]
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.markdown("#### 🔍 Inspect Dynamic AI Agent Execution Trace")
        selected_log_id = st.selectbox(
            "Select Log ID to inspect:",
            [l["id"] for l in logs],
            format_func=lambda x: f"Log #{x} - {next((l.get('agent_name', 'Agent') for l in logs if l['id'] == x), '')} | {next((l.get('action', '') for l in logs if l['id'] == x), '')}"
        )

        target_log = next((l for l in logs if l["id"] == selected_log_id), None)
        if target_log:
            tc1, tc2 = st.columns(2)
            with tc1:
                st.markdown(f"**Agent:** `{target_log.get('agent_name')}` | **Action:** `{target_log.get('action')}` | **Step:** `#{target_log.get('step_number', 1)}`")
                st.text_area("Prompt / Input", value=target_log.get("prompt") or "", height=140, disabled=True, key="insp_prompt")
            with tc2:
                st.markdown(f"**Model:** `{target_log.get('model')}` | **Duration:** `{target_log.get('total_duration_ms', 0):.0f} ms`")
                st.text_area("Response / Output", value=target_log.get("response") or "", height=140, disabled=True, key="insp_resp")

            if target_log.get("thinking"):
                st.markdown("**🧠 Agent Reasoning / Thinking Process:**")
                st.code(target_log["thinking"], language="text")

            if target_log.get("metadata"):
                st.markdown("**📦 Dynamic Execution Metadata:**")
                st.json(target_log["metadata"])

# ========================================================
# TAB 4: REST API LIVE DOCUMENTATION
# ========================================================
elif menu == "🔌 REST API Live Documentation":
    st.markdown("<div class='main-header'>🔌 REST API Tracking AI Agent Working</div>", unsafe_allow_html=True)
    st.markdown("<div class='sub-header'>All parameters, headers, and endpoints adapt dynamically according to the active configuration stored in Neon PostgreSQL.</div>", unsafe_allow_html=True)

    curr_base = active_conn.get("base_url") or os.getenv("REST_API_BASE_URL", "http://localhost:8000")
    curr_header = active_conn.get("header_name") or os.getenv("REST_API_HEADER_NAME", "x-api-key")
    curr_token = active_conn.get("api_token") or os.getenv("REST_API_KEY", "")
    curr_model = active_conn.get("model_name") or os.getenv("OLLAMA_MODEL", "beam:cloud")

    st.markdown(f"""
    ### 📡 Dynamic REST API Endpoints
    - **Current Base URL:** `{curr_base}`
    - **Authentication Header:** `{curr_header}: <YOUR_TOKEN>`
    - **Active Model:** `{curr_model}`

    | Method | Endpoint | Description |
    |---|---|---|
    | `GET` | `/api/health` | Health status and active dynamic profile |
    | `POST` | `/api/agent/run` or `/api/chat` | Execute AI agent task, reasoning, and track working steps in Neon DB |
    | `POST` | `/api/track` | Track arbitrary agent actions and metadata dynamically |
    | `GET` | `/api/tracking/logs` | Query agent tracking logs with dynamic filtering |
    | `GET` | `/api/tracking/stats` | Live tracking metrics (agents, tokens, latency) |
    | `GET` | `/api/connections/active` | Get currently active dynamic connection profile |
    | `POST` | `/api/connections/active/{{id}}` | Switch active connection profile dynamically |
    | `POST` | `/api/connections/generate` | Generate and register new dynamic connection profile |
    """)

    st.markdown("### 💻 Code Samples")
    sc1, sc2 = st.columns(2)
    with sc1:
        st.markdown("**cURL Example (Agent Run & Track):**")
        st.code(f"""curl -X POST "{curr_base}/api/agent/run" \\
  -H "{curr_header}: {curr_token}" \\
  -H "Content-Type: application/json" \\
  -d '{{
    "agent_name": "Beam-Research-Agent",
    "action": "code_analysis",
    "step_number": 1,
    "model": "{curr_model}",
    "messages": [
      {{"role": "user", "content": "Analyze time complexity of mergesort."}}
    ],
    "metadata": {{"environment": "production"}}
  }}'""", language="bash")

    with sc2:
        st.markdown("**Python requests Example:**")
        st.code(f"""import requests

url = "{curr_base}/api/agent/run"
headers = {{
    "{curr_header}": "{curr_token}",
    "Content-Type": "application/json"
}}
payload = {{
    "agent_name": "Beam-Dev-Agent",
    "action": "test_generation",
    "step_number": 1,
    "model": "{curr_model}",
    "messages": [
        {{"role": "user", "content": "Write unit tests for quicksort."}}
    ],
    "metadata": {{"language": "python"}}
}}

res = requests.post(url, headers=headers, json=payload)
data = res.json()
print("Agent Response:", data["content"])
print("Reasoning Trace:", data["thinking"])
print("Latency:", data["total_duration_ms"], "ms")
""", language="python")
