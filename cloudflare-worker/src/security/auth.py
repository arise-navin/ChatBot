"""Authentication dependencies and dynamic API key verification."""

from typing import Any, Dict
from fastapi import HTTPException, Request
from ..database.adapter import validate_request_credentials

async def verify_dynamic_api_key(request: Request) -> Dict[str, Any]:
    """
    Dynamically authenticates incoming requests against Neon PostgreSQL.
    Inspects headers and query parameters against active database profiles.
    """
    token = None
    for h_name, h_val in request.headers.items():
        if h_name.lower() in ["x-api-key", "api-key", "token"]:
            token = h_val
            break

    if not token and "authorization" in request.headers:
        auth_val = request.headers.get("authorization", "")
        if auth_val.lower().startswith("bearer "):
            token = auth_val[7:].strip()

    if not token:
        token = request.query_params.get("api_key") or request.query_params.get("token")

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Missing API key. Provide 'x-api-key' or Bearer token header."
        )

    matched_conn = await validate_request_credentials(token)
    if not matched_conn:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Invalid API key / token. Please provide a valid active token."
        )

    return matched_conn
