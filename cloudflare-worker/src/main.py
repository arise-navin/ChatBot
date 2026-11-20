"""FastAPI entry point for Cloudflare Python Workers."""

import os
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse

from .config import update_runtime_env
from .database.adapter import init_db
from .security.signet import ensure_identity_store
from .routes import (
    health,
    chat,
    tracking,
    guardrails,
    connections,
    agents,
    signet,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initializes tables on worker cold start if database is available."""
    try:
        if os.environ.get("DATABASE_URL"):
            await init_db()
            await ensure_identity_store()
    except Exception:
        pass
    yield

app = FastAPI(
    title="Cloudflare AI ChatBot & Dynamic REST Tracker",
    description="Production AI ChatBot on Cloudflare Workers with real-time tracking, safety guardrails, and emergency kill-switch.",
    version="2.1.0",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cloudflare scope environment propagation middleware
@app.middleware("http")
async def cloudflare_env_middleware(request: Request, call_next):
    env = request.scope.get("env")
    if env:
        update_runtime_env(env)
    return await call_next(request)

# Register route modules
app.include_router(health.router)
app.include_router(chat.router)
app.include_router(tracking.router)
app.include_router(guardrails.router)
app.include_router(connections.router)
app.include_router(agents.router)
app.include_router(signet.router)


# Optional route to serve index.html directly from Python Worker if static assets binding isn't used
@app.get("/app", response_class=HTMLResponse)
async def serve_app():
    public_index = os.path.join(os.path.dirname(os.path.dirname(__file__)), "public", "index.html")
    if os.path.exists(public_index):
        with open(public_index, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>ChatBot Worker running</h1><p>Visit <a href='/docs'>/docs</a></p>")

# Cloudflare Workers Python ASGI entrypoint export
try:
    from workers import asgi
    entrypoint = asgi.entrypoint(app)
    Default = entrypoint
except ImportError:
    # Running outside Cloudflare Workers (e.g. pytest, uvicorn)
    pass
