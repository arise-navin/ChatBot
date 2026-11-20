"""Tests for Safety Guardrails engine."""

import pytest
from src.database.adapter import evaluate_content_guardrails

@pytest.mark.asyncio
async def test_safe_content():
    result = await evaluate_content_guardrails("Tell me a bedtime story about the stars.")
    assert result["is_safe"] is True
    assert result["rule_name"] is None

@pytest.mark.asyncio
async def test_sql_injection_guardrail():
    result = await evaluate_content_guardrails("DROP TABLE chat_sessions; SELECT * FROM users;")
    assert result["is_safe"] is False
    assert result["rule_name"] == "Destructive SQL Prevention"
    assert "INTERCEPTED" in result["fallback_message"]

@pytest.mark.asyncio
async def test_secret_leak_guardrail():
    result = await evaluate_content_guardrails("The secret token is sk-123456789012345678901234567890")
    assert result["is_safe"] is False
    assert result["rule_name"] == "Secret & Credential Leakage"

@pytest.mark.asyncio
async def test_thinking_trace_guardrail():
    result = await evaluate_content_guardrails("Normal answer", thinking="I am completely guessing this answer")
    assert result["is_safe"] is False
    assert result["rule_name"] == "Hallucination Flag Indicator"
