"""Integration tests for FastAPI endpoints on Cloudflare Worker."""

import pytest
import os

@pytest.mark.asyncio
async def test_health_check(async_client):
    res = await async_client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ["healthy", "degraded"]
    assert data["runtime"] == "cloudflare_workers"
    assert data["guardrail_engine"] == "active"

@pytest.mark.asyncio
async def test_remote_agents_discovery(async_client):
    res = await async_client.get("/agents")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "agents" in data
    assert "agent" in data
    assert data["agent"]["id"] is not None

@pytest.mark.asyncio
async def test_agent_track_endpoint(async_client):
    res = await async_client.get("/agents/beam-agent-1/track")
    assert res.status_code == 200
    data = res.json()
    assert data["agentId"] == "beam-agent-1"
    assert "metrics" in data
    assert "agent" in data

@pytest.mark.asyncio
async def test_connections_list(async_client):
    res = await async_client.get("/api/connections")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)

@pytest.mark.asyncio
async def test_emergency_stop_killswitch(async_client):
    active_token = os.environ.get("REST_API_KEY", "")
    header_name = os.environ.get("REST_API_HEADER_NAME", "x-api-key")
    headers = {header_name: active_token}

    res = await async_client.post(
        "/api/agent/stop",
        headers=headers,
        json={"session_id": "test_kill_session_1", "reason": "Automated test kill"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "stopped"
    assert data["session_id"] == "test_kill_session_1"
