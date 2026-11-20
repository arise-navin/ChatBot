# Cloudflare Workers AI ChatBot (`chatbot`)

Production-ready serverless migration of the AI ChatBot, Real-Time Tracker, and Safety Guardrail Engine deployed on **Cloudflare Workers**.

---

## Architecture Overview

```
ChatBot (Root)
├── api.py                    # Legacy FastAPI application (preserved)
├── app.py                    # Streamlit frontend (local dev UI, hardened)
├── database.py               # Synchronous Neon client (preserved)
├── ollama_client.py          # Legacy Ollama caller (preserved)
├── signet_identity.py        # Signet workload identity (preserved)
├── signet_response.py        # Signet refusal parsing (preserved)
├── vendor/signet-sdk/        # Pure Python Signet SDK
│
└── cloudflare-worker/        # Cloudflare Workers Production Deployment
    ├── wrangler.jsonc        # Cloudflare Worker configuration (project: chatbot)
    ├── pyproject.toml        # Pure-Python dependencies & test config
    ├── src/
    │   ├── main.py           # FastAPI ASGI entrypoint (workers.asgi)
    │   ├── config.py         # Cloudflare Worker request.scope['env'] adapter
    │   ├── database/
    │   │   ├── neon_http.py  # Pure async Neon PostgreSQL client over HTTPS
    │   │   └── adapter.py    # Database models, sessions, logs, and rules
    │   ├── security/
    │   │   ├── auth.py       # Dynamic REST API key verification
    │   │   └── signet.py     # Signet workload token management & refusal handler
    │   ├── services/
    │   │   └── ollama.py     # Async Ollama Cloud integration with guardrails
    │   └── routes/
    │       ├── health.py     # GET /api/health
    │       ├── chat.py       # POST /api/chat, /api/agent/run, /api/agent/stop
    │       ├── tracking.py   # POST /api/track, GET /api/tracking/logs, /stats
    │       ├── guardrails.py # GET/POST/DELETE /api/guardrails
    │       ├── connections.py# GET/POST /api/connections
    │       ├── agents.py     # GET /agents, /agents/{id}/track, executions, run, pause, stop
    │       └── signet.py     # POST /api/signet/identity/refresh
    ├── public/
    │   └── index.html        # Single-page UI with chat, config, guardrails, & logs
    └── tests/                # 15 automated integration tests (all passing)
```

---

## Cloudflare Secrets Configuration

Before deploying, configure your secrets using the Cloudflare Wrangler CLI. Do not commit actual secrets to git or `.env`.

```bash
# 1. Neon PostgreSQL Connection String
npx wrangler secret put DATABASE_URL

# 2. Ollama Cloud API Key
npx wrangler secret put OLLAMA_API_KEY

# 3. Dynamic REST API Key Token
npx wrangler secret put REST_API_KEY

# 4. Signet Workload Identity Credentials
npx wrangler secret put SIGNET_CONTROL_URL
npx wrangler secret put SIGNET_GATEWAY_URL
npx wrangler secret put SIGNET_AGENT_ID
npx wrangler secret put SIGNET_DEPLOYMENT_CREDENTIAL
npx wrangler secret put SIGNET_WORKLOAD_REFRESH_TOKEN
```

---

## Local Development & Testing

Run the automated test suite locally:

```bash
cd cloudflare-worker
python -m pytest tests -v
```

Test the Cloudflare Worker locally using Wrangler:

```bash
cd cloudflare-worker
npx wrangler dev
```

Visit `http://localhost:8787` in your browser to access the application and UI.

---

## Production Deployment to Cloudflare

Deploy the worker and static assets to Cloudflare Workers:

```bash
cd cloudflare-worker
npx wrangler deploy
```

Once deployed, Cloudflare will output your public HTTPS URL:
`https://chatbot.<your-subdomain>.workers.dev`

---

## Verified Endpoints Reference

| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `GET` | `/api/health` | Production health check verifying DB & Guardrail Engine | No |
| `POST` | `/api/chat` | AI Chat completion with pre-delivery guardrail checks | Yes (`x-api-key`) |
| `POST` | `/api/agent/run` | Execute AI agent task with thinking traces | Yes (`x-api-key`) |
| `POST` | `/api/agent/stop` | Emergency kill-switch to abort in-flight agent session | Yes (`x-api-key`) |
| `POST` | `/api/agent/abort` | Alias for emergency abort kill-switch | Yes (`x-api-key`) |
| `POST` | `/api/track` | Track arbitrary AI execution steps to Neon DB | Yes (`x-api-key`) |
| `GET` | `/api/tracking/logs` | Fetch audit logs with status, source, and agent filters | Yes (`x-api-key`) |
| `GET` | `/api/tracking/stats` | Aggregated performance metrics (latency, tokens, errors) | Yes (`x-api-key`) |
| `GET` | `/api/guardrails` | List all active safety guardrail rules | Yes (`x-api-key`) |
| `POST` | `/api/guardrails` | Create new regex or keyword guardrail rule | Yes (`x-api-key`) |
| `POST` | `/api/guardrails/{id}/toggle` | Toggle rule activation status | Yes (`x-api-key`) |
| `DELETE` | `/api/guardrails/{id}` | Delete a guardrail rule | Yes (`x-api-key`) |
| `GET` | `/api/connections` | List all dynamic REST API connection profiles | No |
| `GET` | `/api/connections/active` | Get currently active connection profile | No |
| `POST` | `/api/connections/generate` | Generate and activate new dynamic API key profile | No |
| `GET` | `/agents` | Discover registered agents (Remote Management Actions) | No |
| `GET` | `/agents/{id}/track` | Live agent metrics and tracking state | No |
| `GET` | `/agents/executions` | Execution history for a specific agent | No |
| `POST` | `/agents/{id}/run` | Execute remote agent task | No |
| `POST` | `/agents/{id}/pause` | Pause remote agent | No |
| `POST` | `/agents/{id}/stop` | Immediately stop remote agent (Kill-switch) | No |
| `POST` | `/agents/{id}/activate` | Activate remote agent | No |
| `POST` | `/api/signet/identity/refresh` | Refresh Signet workload identity | `x-signet-workload-refresh` |
