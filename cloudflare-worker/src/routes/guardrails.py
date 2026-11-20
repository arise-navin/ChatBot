"""Guardrail rules management routes."""

from typing import Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..database.adapter import (
    get_guardrail_rules,
    create_guardrail_rule,
    toggle_guardrail_rule,
    delete_guardrail_rule
)
from ..security.auth import verify_dynamic_api_key

router = APIRouter(tags=["Guardrails"])

class GuardrailRuleRequest(BaseModel):
    rule_name: str
    pattern: str
    rule_type: Optional[str] = "regex"
    action: Optional[str] = "block"
    fallback_message: Optional[str] = None

@router.get("/api/guardrails", dependencies=[Depends(verify_dynamic_api_key)])
async def list_guardrail_rules():
    """Returns all active and configured guardrail rules stored in Neon DB."""
    return await get_guardrail_rules(active_only=False)

@router.post("/api/guardrails", dependencies=[Depends(verify_dynamic_api_key)])
async def add_guardrail_rule(rule: GuardrailRuleRequest):
    """Creates a new guardrail rule dynamically in Neon PostgreSQL."""
    created = await create_guardrail_rule(
        rule_name=rule.rule_name,
        pattern=rule.pattern,
        rule_type=rule.rule_type or "regex",
        action=rule.action or "block",
        fallback_message=rule.fallback_message
    )
    return {"status": "created", "rule": created}

@router.post("/api/guardrails/{rule_id}/toggle", dependencies=[Depends(verify_dynamic_api_key)])
async def toggle_guardrail(rule_id: int, is_active: bool = Query(...)):
    """Enables or disables a guardrail rule."""
    await toggle_guardrail_rule(rule_id, is_active)
    return {"status": "updated", "rule_id": rule_id, "is_active": is_active}

@router.delete("/api/guardrails/{rule_id}", dependencies=[Depends(verify_dynamic_api_key)])
async def delete_guardrail(rule_id: int):
    """Deletes a guardrail rule from Neon DB."""
    await delete_guardrail_rule(rule_id)
    return {"status": "deleted", "rule_id": rule_id}
