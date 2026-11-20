"""Signet identity maintenance routes."""

import hmac
from fastapi import APIRouter, HTTPException, Request

from ..config import required_setting
from ..security.signet import WorkloadClaims, decode_claims, get_workload_token

router = APIRouter(tags=["Signet"])

@router.post("/api/signet/identity/refresh", response_model=WorkloadClaims)
async def refresh_signet_identity(request: Request) -> WorkloadClaims:
    """Refreshes bootstrap identity using the authenticated Signet maintenance header."""
    expected = required_setting("SIGNET_WORKLOAD_REFRESH_TOKEN")
    supplied = request.headers.get("x-signet-workload-refresh", "")
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Invalid Signet workload refresh credential")
    token = await get_workload_token()
    return WorkloadClaims.model_validate(decode_claims(token))
