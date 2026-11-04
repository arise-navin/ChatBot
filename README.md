# ⚡ Dynamic AI Agent Tracker & Ollama Beam:Cloud Console

A fully dynamic Python application powered by **Ollama Cloud** running **`beam:cloud`**, backed by **Neon PostgreSQL**, and providing a **Dynamic REST API that tracks the AI Agent working in real time**. **Nothing is hardcoded.**

---

## 🚀 Key Dynamic Features

1. **Zero Hardcoded Configuration**:
   - All connection details, API keys, tokens, endpoints, models, and header names are stored in and dynamically retrieved from **Neon PostgreSQL**.
   - Changes made in the **Settings** take effect immediately without restarting the application or editing code.

2. **Dynamic AI Agent Tracking Engine**:
   - Tracks the AI Agent's full working state:
     - `agent_name`: Dynamic identifier (e.g., `Beam-Dev-Agent`, `Code-Reviewer`, etc.)
     - `action`: Dynamic task action name (e.g., `agent_interactive_chat`, `code_generation`, `bug_triage`)
     - `step_number`: Execution step index
     - `thinking`: Beam Cloud Chain-of-Thought / internal reasoning trace
     - `prompt` & `response`: Input and generated output
     - `total_duration_ms`: Latency
     - `prompt_eval_count` & `eval_count`: Dynamic token usage
     - `metadata`: Flexible JSON payload (priority, environment, client metadata, etc.)
   - Optional **External Webhook / REST Dispatcher**: Automatically forwards agent tracking events to an external analytics REST API.

3. **Dynamic REST API (`FastAPI`)**:
   - Header inspection is dynamic: Accepts any header name configured in the active database profile (e.g. `x-api-key`, `Authorization: Bearer`, etc.).
   - `POST /api/chat` or `POST /api/agent/run`: Run AI Agent tasks, streams/returns reasoning, and dynamically tracks execution in Neon PostgreSQL.
   - `POST /api/track`: Ingest custom tracking events from external agents or microservices.
   - `GET /api/tracking/logs`: Dynamically filters tracking logs by source, agent name, or status.
   - `GET /api/tracking/stats`: Real-time analytics (total agent runs, active agent count, average latency, token totals).
   - `GET /api/connections/active`: Fetches current active profile.
   - `POST /api/connections/active/{id}`: Switches active connection profile on the fly.
   - `POST /api/connections/generate`: One-click dynamic credential and connection generation.

4. **Dynamic Minimal UI (`Streamlit`)**:
   - **💬 AI Agent Chat**: Console to chat with the agent, select dynamic agent name/action, and view live reasoning in collapsible blocks.
   - **⚙️ Settings & Dynamic API Generator**:
     - **REST API Connection Name**: Generates random names (e.g. `Beam-Tracker-A1B2`) or custom input.
     - **External API Base URL**: Configurable base URL.
     - **Authentication API Key**: Dynamic upstream Ollama Cloud Key.
     - **API Key Header Name**: Configurable (default `x-api-key`).
     - **API Key / Token**: One-click cryptographic 32-character token generator.
     - **Model Name**: Dynamic model selection (default `beam:cloud`).
     - **External Webhook Forwarding**: Forward AI tracking events to another REST service.
     - **Profile Switcher**: Switch active profiles with a single click.
   - **📊 AI Agent Tracking Logs**: Live timeline dashboard with dynamic filtering by agent, action, and source, plus detailed JSON metadata inspector.
   - **🔌 REST API Documentation**: Live, interactive API tester and dynamically rendered code snippets using the currently active profile.

---

## 📁 Project Structure

```
D:\Nov\ChatBot\
├── venv/                     # Python 3.12 Virtual Environment
├── .env                      # Environment variables & secrets
├── .env.example              # Sample configuration
├── requirements.txt          # Python dependencies
├── database.py               # Dynamic Neon PostgreSQL schema & CRUD
├── ollama_client.py          # Dynamic Ollama client with external tracking
├── api.py                    # Dynamic FastAPI AI Agent tracking REST API
├── app.py                    # Minimal Python Streamlit Web Console
├── run.py                    # Unified launcher
└── README.md                 # Documentation
```

---

## 🏃 Quick Start Guide

### 1. Launch the Application

With the virtual environment active:
```powershell
.\venv\Scripts\python.exe run.py
```
*(Or `.\venv\Scripts\streamlit.exe run app.py` — it boots both the Streamlit UI on port `8501` and the background dynamic tracking REST API on port `8000`)*

- **Web Console**: [http://localhost:8501](http://localhost:8501)
- **Dynamic REST API**: [http://localhost:8000](http://localhost:8000)
- **Interactive Swagger Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 🔌 Calling the Dynamic AI Agent REST API

### cURL Example:
```bash
curl -X POST "http://localhost:8000/api/agent/run" \
  -H "x-api-key: <YOUR_ACTIVE_DYNAMIC_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_name": "Beam-Research-Agent",
    "action": "code_analysis",
    "step_number": 1,
    "model": "beam:cloud",
    "messages": [
      {"role": "user", "content": "Explain how mixture-of-experts routing works."}
    ],
    "metadata": {"environment": "production", "task_id": "task_101"}
  }'
```

### Python Example:
```python
import requests

url = "http://localhost:8000/api/agent/run"
headers = {
    "x-api-key": "<YOUR_ACTIVE_DYNAMIC_TOKEN>",
    "Content-Type": "application/json"
}

payload = {
    "agent_name": "Beam-Dev-Agent",
    "action": "unit_test_generation",
    "step_number": 2,
    "messages": [
        {"role": "user", "content": "Write unit tests for a binary search function in Python."}
    ],
    "metadata": {"language": "python", "framework": "pytest"}
}

response = requests.post(url, headers=headers, json=payload)
data = response.json()

print("Agent:", data["agent_name"])
print("Reasoning Trace:", data["thinking"])
print("Output:", data["content"])
print("Latency:", data["total_duration_ms"], "ms")
```

---

## 🛑 Real-Time Agent Interceptor & Emergency Stop Kill-Switch

### 1. Emergency Stop / Abort Agent Execution (`POST /api/agent/stop`)
Stop any in-flight agent immediately before it outputs or commits any incorrect actions:
```bash
curl -X POST "http://localhost:8000/api/agent/stop" \
  -H "x-api-key: <YOUR_API_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "target_session_id",
    "reason": "Agent output flagged as incorrect"
  }'
```

### 2. Pre-Delivery Safety Guardrails (`guardrail_rules`)
All responses and internal reasoning traces are evaluated against active guardrail rules in Neon PostgreSQL **before reaching the user**:
- **Destructive SQL Prevention**: Blocks `DROP TABLE`, `TRUNCATE`, destructive statements.
- **Credential & Secret Leakage**: Blocks exposed API keys, private tokens, passwords.
- **Dangerous Shell Commands**: Blocks `rm -rf`, `format`, unsafe system commands.
- **Hallucination & Fabrication Flags**: Catches uncertainty / fabricated markers.
- **Custom Dynamic Rules**: Create your own rules via UI (`🛡️ Agent Guardrails & Interceptor`) or via `POST /api/guardrails`.

When intercepted:
- The bad response is **blocked** and never sent to the user.
- A safe replacement message is delivered instead.
- The violation event is logged into Neon PostgreSQL with `status: "intercepted"`.

---

## 🤖 Remote Management Actions & Agents Protocol (100% Compatible)

This application natively implements the standard Remote Agent Management & Tracking specifications:

| Action | HTTP Method | Endpoint | Description |
|---|---|---|---|
| **test** | `GET` | `/agents` | Test connection / verify mapping |
| **discover** | `GET` | `/agents` | Discover all available mapped agents |
| **track** | `GET` | `/agents/{id}/track` | Real-time agent status & tracking metrics |
| **executions** | `GET` | `/agents/executions?agentId={id}` | Historical execution logs for the agent |
| **run** | `POST` | `/agents/{id}/run` | Execute task with Ollama beam:cloud + guardrails |
| **pause** | `POST` | `/agents/{id}/pause` | Pause an agent's execution |
| **stop** | `POST` | `/agents/{id}/stop` | Emergency Stop / abort an active agent |
| **activate** | `POST` | `/agents/{id}/activate` | Re-activate a stopped/paused agent |

* **Tracking agent object JSON pointer**: `/agent` (Supported natively in all responses).


