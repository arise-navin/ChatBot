"""Signet workload identity, token management, and safety response handling for Cloudflare Workers."""

import base64
import json
import logging
import time
from typing import Optional, Dict, Any
import httpx
from pydantic import BaseModel, ConfigDict

from ..config import required_setting, get_setting
from ..database.neon_http import db_client

logger = logging.getLogger(__name__)

class SignetAuthError(Exception):
    """Raised when Signet token verification or exchange fails."""
    pass

class WorkloadClaims(BaseModel):
    model_config = ConfigDict(strict=True)
    agent_id: str
    ins: str
    exp: int

class DeploymentToken(BaseModel):
    model_config = ConfigDict(strict=True)
    token: str

class SignetRefusal(BaseModel):
    type: str
    code: str
    message: str
    decision: str
    record_id: Optional[str] = None
    request_id: str
    rule_ids: list[str]

class SignetErrorResponse(BaseModel):
    error: SignetRefusal

def decode_claims(token: str) -> dict:
    """Read a JWT token's claims without verifying signature."""
    try:
        parts = token.split(".")
        if len(parts) < 2:
            raise ValueError("Token does not have a valid JWT structure")
        payload = parts[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload.encode("utf-8")).decode("utf-8"))
    except Exception as exc:
        raise SignetAuthError(f"Signet returned an unreadable token: {exc}") from exc

def signet_refusal(headers: dict, body: dict) -> Optional[SignetRefusal]:
    """Attribution helper for Signet gateway responses."""
    has_signet_header = any(k.lower() == "x-signet-request-id" for k in headers.keys())
    if not has_signet_header:
        return None
    try:
        refusal = SignetErrorResponse.model_validate(body).error
        if refusal.type != "signet_policy":
            return None
        return refusal
    except Exception:
        return None

def refusal_message(refusal: SignetRefusal) -> str:
    """User-facing message for Signet policy refusals."""
    if refusal.code == "safety_unavailable":
        return "Chat paused by Signet. The safety check is unavailable. Please try again later."
    return "Chat blocked by Signet. This request or response could not pass the safety policy. Please ask for safe, lawful information."

async def ensure_identity_store() -> None:
    """Ensures signet_workload_identity table exists in Neon PostgreSQL."""
    await db_client.execute("""
        CREATE TABLE IF NOT EXISTS signet_workload_identity (
            agent_id TEXT PRIMARY KEY,
            workload_token TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    agent_id = get_setting("SIGNET_AGENT_ID")
    if agent_id:
        await db_client.execute(
            "INSERT INTO signet_workload_identity (agent_id) VALUES (%s) ON CONFLICT DO NOTHING;",
            [agent_id]
        )

async def exchange_deployment_token() -> str:
    """Exchange the deployment credential with Signet Control URL."""
    base_control = required_setting("SIGNET_CONTROL_URL").rstrip("/")
    url = f"{base_control}/api/v1/identity/deployment-token"
    credential = required_setting("SIGNET_DEPLOYMENT_CREDENTIAL")

    async with httpx.AsyncClient(timeout=15.0) as client:
        for attempt in range(1, 4):
            try:
                resp = await client.post(url, json={"deployment_credential": credential})
                if resp.status_code >= 400:
                    raise httpx.HTTPStatusError(
                        f"Signet POST {url} failed ({resp.status_code}): {resp.text}",
                        request=resp.request,
                        response=resp
                    )
                return DeploymentToken.model_validate(resp.json()).token
            except (httpx.TransportError, httpx.HTTPStatusError) as error:
                if isinstance(error, httpx.HTTPStatusError) and error.response.status_code < 500:
                    raise
                if attempt == 3:
                    raise
                logger.warning("Signet token exchange attempt %s failed: %s", attempt, error)

    raise RuntimeError("Signet deployment token exchange exhausted retries.")

async def get_workload_token() -> str:
    """Returns an active shared workload token, refreshing if expiring or absent."""
    agent_id = required_setting("SIGNET_AGENT_ID")
    await ensure_identity_store()

    rows = await db_client.query(
        "SELECT workload_token FROM signet_workload_identity WHERE agent_id = %s;",
        [agent_id]
    )

    stored_token = rows[0].get("workload_token") if rows else None
    if stored_token and isinstance(stored_token, str):
        try:
            claims = WorkloadClaims.model_validate(decode_claims(stored_token))
            if claims.agent_id == agent_id and claims.exp > time.time() + 120:
                return stored_token
        except Exception:
            logger.info("Stored Signet token invalid or expired, refreshing...")

    # Exchange deployment token
    new_token = await exchange_deployment_token()
    claims = WorkloadClaims.model_validate(decode_claims(new_token))
    if claims.agent_id != agent_id:
        raise SignetAuthError("Deployment credential belongs to a different Signet agent.")

    await db_client.execute("""
        INSERT INTO signet_workload_identity (agent_id, workload_token, updated_at)
        VALUES (%s, %s, NOW())
        ON CONFLICT (agent_id) DO UPDATE 
        SET workload_token = EXCLUDED.workload_token, updated_at = NOW();
    """, [agent_id, new_token])

    return new_token
