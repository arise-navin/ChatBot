"""Application configuration helper supporting both Cloudflare Worker env scope and os.environ."""

import os
from typing import Optional, Any

_RUNTIME_ENV: dict[str, Any] = {}

def update_runtime_env(env: Any) -> None:
    """Updates runtime environment from Cloudflare Worker request scope."""
    global _RUNTIME_ENV
    if not env:
        return
    if isinstance(env, dict):
        _RUNTIME_ENV.update(env)
        for k, v in env.items():
            if isinstance(v, str):
                os.environ[k] = v
    else:
        for attr in dir(env):
            if not attr.startswith("_"):
                val = getattr(env, attr, None)
                if isinstance(val, (str, int, float, bool)):
                    _RUNTIME_ENV[attr] = val
                    if isinstance(val, str):
                        os.environ[attr] = val

def get_setting(name: str, default: str = "") -> str:
    """Retrieves setting from Cloudflare scope cache or os.environ."""
    val = _RUNTIME_ENV.get(name)
    if val is not None:
        return str(val).strip()
    return os.environ.get(name, default).strip()

def required_setting(name: str) -> str:
    """Retrieves a required setting or raises ValueError."""
    val = get_setting(name)
    if not val:
        raise ValueError(f"Required setting '{name}' is missing. Configure it via Cloudflare Secrets or environment.")
    return val
