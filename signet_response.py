"""Validate Signet refusal responses without exposing internal service errors to chat users."""

from pydantic import BaseModel
import requests


class SignetRefusal(BaseModel):
    type: str
    code: str
    message: str
    decision: str
    record_id: str | None
    request_id: str
    rule_ids: list[str]


class SignetErrorResponse(BaseModel):
    error: SignetRefusal


def signet_refusal(response: requests.Response) -> SignetRefusal | None:
    """Only attribute a refusal to Signet when its gateway response identifies itself."""
    if not response.headers.get("x-signet-request-id"):
        return None
    refusal = SignetErrorResponse.model_validate(response.json()).error
    if refusal.type != "signet_policy":
        raise ValueError(f"Unexpected Signet error type: {refusal.type}")
    return refusal


def refusal_message(refusal: SignetRefusal) -> str:
    """Use a clear notice for policy blocks, approval holds and unavailable safety checks."""
    if refusal.code == "safety_unavailable":
        return "Chat paused by Signet. The safety check is unavailable. Please try again later."
    return "Chat blocked by Signet. This request or response could not pass the safety policy. Please ask for safe, lawful information."
