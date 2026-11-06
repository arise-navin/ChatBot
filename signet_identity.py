"""Persist bootstrap identity across Vercel workers; renew it from Signet maintenance."""

import os
import time
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
from pydantic import BaseModel, ConfigDict
from signet_sdk import SignetConfig, TokenManager, decode_claims
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
        raise ValueError(f"{name} is required for the Signet bootstrap connection")
    return value


def initialize_identity_store() -> None:
    """Store one shared workload identity per agent; never persist the bootstrap secret."""
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


def workload_token() -> str:
    """Serialize SDK token refresh through PostgreSQL so cold starts reuse the same identity."""
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
                if claims.exp <= time.time() + 5:
                    raise SignetAuthError(
                        "Signet workload token expired: check the maintenance refresh job, then enroll a new bootstrap identity"
                    )
            with TemporaryDirectory(prefix="signet-identity-") as directory:
                cache_path = Path(directory) / "token"
                if stored_token is not None:
                    cache_path.write_text(stored_token, encoding="utf-8")
                config = replace(
                    SignetConfig.from_env(), token_cache=str(cache_path), client_id=None, client_secret=None
                )
                with httpx.Client(timeout=15.0) as http:
                    token = TokenManager(config, http=http).token()
                claims = WorkloadClaims.model_validate(decode_claims(token))
                if claims.agent_id != agent_id:
                    raise SignetAuthError("Bootstrap credential belongs to a different Signet agent")
                if token != stored_token:
                    cursor.execute(
                        "UPDATE signet_workload_identity SET workload_token = %s, updated_at = NOW() WHERE agent_id = %s",
                        (token, agent_id),
                    )
                return token
    finally:
        connection.close()
