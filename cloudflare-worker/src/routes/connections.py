"""Dynamic REST API Connection management routes."""

import secrets
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import get_setting
from ..database.adapter import (
    get_api_connections,
    get_active_api_connection,
    set_active_api_connection,
    create_api_connection,
    update_api_connection,
    delete_api_connection
)

router = APIRouter(tags=["Connections"])

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

@router.get("/api/connections")
async def list_connections():
    """Lists all dynamic REST API connection profiles."""
    return await get_api_connections()

@router.get("/api/connections/active")
async def get_active_connection():
    """Returns the currently active dynamic connection profile."""
    active = await get_active_api_connection()
    if not active:
        raise HTTPException(status_code=404, detail="No active connection found.")
    return active

@router.post("/api/connections/active/{conn_id}")
async def activate_connection(conn_id: int):
    """Dynamically sets the active connection profile in Neon PostgreSQL."""
    activated = await set_active_api_connection(conn_id)
    return {"status": "activated", "active_connection_id": conn_id, "connection": activated}

@router.post("/api/connections/generate")
async def generate_connection(req: Optional[ConnectionCreateRequest] = None):
    """Dynamically generates and registers a new REST API Connection profile."""
    req = req or ConnectionCreateRequest()
    random_id = secrets.token_hex(3).upper()
    name = req.connection_name or f"Beam-Tracker-{random_id}"
    base_url = req.base_url or get_setting("REST_API_BASE_URL", "http://localhost:8000")
    auth_key = req.auth_api_key or get_setting("OLLAMA_API_KEY", "")
    header = req.header_name or get_setting("REST_API_HEADER_NAME", "x-api-key")
    token = req.api_token or f"beam_sec_{secrets.token_hex(16)}"
    model = req.model_name or get_setting("OLLAMA_MODEL", "beam:cloud")
    ollama_url = req.ollama_base_url or get_setting("OLLAMA_BASE_URL", "https://ollama.com/api/chat")

    created = await create_api_connection(
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
    return {"status": "success", "connection": created}

@router.put("/api/connections/{conn_id}")
async def update_connection_endpoint(conn_id: int, req: ConnectionUpdateRequest):
    """Dynamically updates any field of an existing connection profile."""
    update_data = {k: v for k, v in req.model_dump().items() if v is not None}
    updated = await update_api_connection(conn_id, **update_data)
    if not updated:
        raise HTTPException(status_code=404, detail="Connection not found")
    return {"status": "updated", "connection": updated}

@router.delete("/api/connections/{conn_id}")
async def delete_connection_endpoint(conn_id: int):
    """Deletes a connection profile."""
    await delete_api_connection(conn_id)
    return {"status": "deleted", "id": conn_id}
