"""Tests for Neon PostgreSQL HTTP client."""

import pytest
from src.database.neon_http import convert_placeholders, db_client

def test_convert_placeholders():
    sql1 = "SELECT * FROM users WHERE id = %s AND name = %s;"
    converted1 = convert_placeholders(sql1)
    assert converted1 == "SELECT * FROM users WHERE id = $1 AND name = $2;"

    sql2 = "SELECT * FROM users WHERE id = $1;"
    converted2 = convert_placeholders(sql2)
    assert converted2 == "SELECT * FROM users WHERE id = $1;"

@pytest.mark.asyncio
async def test_neon_http_query_live():
    """Executes a simple live query over HTTP against Neon."""
    rows = await db_client.query("SELECT 1 AS test_val, 'cf-worker' AS source;")
    assert len(rows) == 1
    assert rows[0]["test_val"] == 1
    assert rows[0]["source"] == "cf-worker"

@pytest.mark.asyncio
async def test_neon_http_tables_exist():
    """Verifies existing tables in public schema."""
    rows = await db_client.query(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = $1;",
        ["public"]
    )
    table_names = [r["table_name"] for r in rows]
    assert "chat_sessions" in table_names
    assert "guardrail_rules" in table_names
    assert "rest_api_connections" in table_names
