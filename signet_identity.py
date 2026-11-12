"""Share short-lived Signet tokens across workers using a deployment credential."""

import os
import time
import logging

import httpx
from pydantic import BaseModel, ConfigDict
from signet_sdk import decode_claims
from signet_sdk.errors import SignetAuthError

import database


class WorkloadClaims(BaseModel):
    model_config = ConfigDict(strict=True)
    agent_id: str
    ins: str
    exp: int


def required_setting(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required for the Signet deployment connection")
    return value


def initialize_identity_store() -> None:
    """Store one shared workload token per agent; keep the deployment credential in the environment."""
    connection = database.get_connection()
    try:
        with connection, connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS signet_workload_identity (
                    agent_id TEXT PRIMARY KEY,
                    workload_token TEXT,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            cursor.execute(
                "INSERT INTO signet_workload_identity (agent_id) VALUES (%s) ON CONFLICT DO NOTHING",
                (required_setting("SIGNET_AGENT_ID"),),
            )
    finally:
        connection.close()


class DeploymentToken(BaseModel):
    model_config = ConfigDict(strict=True)
    token: str


def exchange_deployment_token() -> str:
    """Exchange the configured deployment credential, retrying transient service failures."""
    url = required_setting("SIGNET_CONTROL_URL").rstrip("/") + "/api/v1/identity/deployment-token"
    credential = required_setting("SIGNET_DEPLOYMENT_CREDENTIAL")
    with httpx.Client(timeout=15.0) as http:
        for attempt in range(1, 4):
            try:
                response = http.post(url, json={"deployment_credential": credential})
                if response.status_code >= 400:
                    raise httpx.HTTPStatusError(
                        f"Signet POST {url} failed ({response.status_code}): {response.text}",
                        request=response.request, response=response,
                    )
                return DeploymentToken.model_validate(response.json()).token
            except (httpx.TransportError, httpx.HTTPStatusError) as error:
                if isinstance(error, httpx.HTTPStatusError) and error.response.status_code < 500:
                    raise
                if attempt == 3:
                    raise
                logging.getLogger(__name__).warning(
                    "Signet token exchange failed; retrying",
                    extra={"url": url, "attempt": attempt, "error": str(error)},
                )
                time.sleep(attempt)
    raise RuntimeError("Signet deployment token exchange exhausted its attempts")


def workload_token() -> str:
    """Reuse a shared token, obtaining a fresh identity before it expires or after inactivity."""
    agent_id = required_setting("SIGNET_AGENT_ID")
    connection = database.get_connection()
    try:
        with connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT workload_token FROM signet_workload_identity WHERE agent_id = %s FOR UPDATE",
                (agent_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise SignetAuthError(f"Identity store is not initialized for Signet agent {agent_id}")
            stored_token = row[0]
            if stored_token is not None:
                if not isinstance(stored_token, str):
                    raise TypeError("Stored Signet workload token must be a string")
                claims = WorkloadClaims.model_validate(decode_claims(stored_token))
                if claims.agent_id != agent_id:
                    raise SignetAuthError("Stored Signet token belongs to a different agent")
                if claims.exp > time.time() + 120:
                    return stored_token
            token = exchange_deployment_token()
            claims = WorkloadClaims.model_validate(decode_claims(token))
            if claims.agent_id != agent_id:
                raise SignetAuthError("Deployment credential belongs to a different Signet agent")
            cursor.execute(
                "UPDATE signet_workload_identity SET workload_token = %s, updated_at = NOW() WHERE agent_id = %s",
                (token, agent_id),
            )
            return token
    finally:
        connection.close()
