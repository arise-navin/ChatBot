"""Tests for Signet identity claims decoding and response attribution."""

import base64
import json
import pytest
from src.security.signet import decode_claims, signet_refusal, refusal_message, SignetRefusal

def test_decode_claims_valid():
    payload = {"agent_id": "test_agent_123", "ins": "ins_abc", "exp": 1899999999}
    token = "header." + base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=") + ".sig"
    decoded = decode_claims(token)
    assert decoded["agent_id"] == "test_agent_123"
    assert decoded["exp"] == 1899999999

def test_signet_refusal_detection():
    headers = {"x-signet-request-id": "req-123", "content-type": "application/json"}
    body = {
        "error": {
            "type": "signet_policy",
            "code": "restricted_content",
            "message": "Policy violation",
            "decision": "deny",
            "record_id": "rec-1",
            "request_id": "req-123",
            "rule_ids": ["rule-1"]
        }
    }
    refusal = signet_refusal(headers, body)
    assert refusal is not None
    assert refusal.code == "restricted_content"
    msg = refusal_message(refusal)
    assert "Chat blocked by Signet" in msg

def test_non_signet_response():
    headers = {"content-type": "application/json"}
    body = {"error": "Internal Server Error"}
    refusal = signet_refusal(headers, body)
    assert refusal is None
