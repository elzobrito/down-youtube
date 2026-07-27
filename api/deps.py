"""Optional API authentication."""

from __future__ import annotations

import os
from typing import Optional

from fastapi import Header, HTTPException, status


def get_configured_token() -> Optional[str]:
    return os.environ.get("DOWN_YOUTUBE_API_TOKEN") or None


async def require_api_token(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    authorization: Optional[str] = Header(default=None),
) -> None:
    """If DOWN_YOUTUBE_API_TOKEN is set, require matching X-API-Key or Bearer token."""
    expected = get_configured_token()
    if not expected:
        return

    provided = x_api_key
    if not provided and authorization:
        parts = authorization.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            provided = parts[1].strip()
        else:
            provided = authorization.strip()

    if provided != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API token",
        )
