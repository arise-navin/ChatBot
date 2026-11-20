"""Async Neon PostgreSQL client over HTTP for Cloudflare Workers."""

import json
import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
import httpx

from ..config import required_setting, get_setting

logger = logging.getLogger(__name__)

def convert_placeholders(sql: str) -> str:
    """
    Translates standard %s parameter placeholders to Neon $1, $2, ... positional format.
    Leaves queries that already use $1, $2 untouched.
    """
    if "%s" not in sql:
        return sql
    parts = sql.split("%s")
    out = [parts[0]]
    for idx, part in enumerate(parts[1:], 1):
        out.append(f"${idx}{part}")
    return "".join(out)

class NeonHTTPClient:
    """High-performance async Neon PostgreSQL client executing SQL over HTTPS."""

    def __init__(self, database_url: Optional[str] = None):
        self._custom_url = database_url

    @property
    def database_url(self) -> str:
        return self._custom_url or required_setting("DATABASE_URL")

    @property
    def endpoint_url(self) -> str:
        parsed = urlparse(self.database_url)
        if not parsed.hostname:
            raise ValueError("DATABASE_URL has an invalid hostname.")
        return f"https://{parsed.hostname}/sql"

    def _headers(self) -> Dict[str, str]:
        return {
            "Neon-Connection-String": self.database_url,
            "Content-Type": "application/json"
        }

    def _format_param(self, val: Any) -> Any:
        if isinstance(val, (dict, list)):
            return json.dumps(val)
        return val

    async def query(self, sql: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
        """Executes a single parameterized query and returns matching rows as dicts."""
        formatted_sql = convert_placeholders(sql)
        clean_params = [self._format_param(p) for p in (params or [])]
        payload = {
            "query": formatted_sql,
            "params": clean_params
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                self.endpoint_url,
                headers=self._headers(),
                json=payload
            )

        if resp.status_code >= 400:
            err_data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            err_msg = err_data.get("message") or resp.text
            logger.error("Neon HTTP SQL Error (%s): %s", resp.status_code, err_msg)
            raise RuntimeError(f"Database query failed ({resp.status_code}): {err_msg}")

        data = resp.json()
        return data.get("rows", [])

    async def execute(self, sql: str, params: Optional[List[Any]] = None) -> Dict[str, Any]:
        """Executes an INSERT/UPDATE/DELETE query and returns rowCount and any returned rows."""
        formatted_sql = convert_placeholders(sql)
        clean_params = [self._format_param(p) for p in (params or [])]
        payload = {
            "query": formatted_sql,
            "params": clean_params
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                self.endpoint_url,
                headers=self._headers(),
                json=payload
            )

        if resp.status_code >= 400:
            err_data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            err_msg = err_data.get("message") or resp.text
            logger.error("Neon HTTP SQL Error (%s): %s", resp.status_code, err_msg)
            raise RuntimeError(f"Database execution failed ({resp.status_code}): {err_msg}")

        data = resp.json()
        return {
            "rowCount": data.get("rowCount", 0),
            "rows": data.get("rows", [])
        }

    async def batch(self, queries_and_params: List[tuple]) -> List[List[Dict[str, Any]]]:
        """Executes atomic batch queries using Neon HTTP's native queries array payload."""
        queries_payload = []
        for q, p in queries_and_params:
            queries_payload.append({
                "query": convert_placeholders(q),
                "params": [self._format_param(x) for x in (p or [])]
            })

        payload = {"queries": queries_payload}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                self.endpoint_url,
                headers=self._headers(),
                json=payload
            )

        if resp.status_code >= 400:
            err_data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            err_msg = err_data.get("message") or resp.text
            raise RuntimeError(f"Database batch failed ({resp.status_code}): {err_msg}")

        data = resp.json()
        results = []
        for res_obj in data.get("results", []):
            results.append(res_obj.get("rows", []))
        return results

# Singleton instance
db_client = NeonHTTPClient()
