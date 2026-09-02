"""Thin Meta Graph API client.

Deliberately small: one place that knows how to make a call, surface an error
usefully, and stop retrying. Everything platform-specific lives in
instagram.py / facebook.py.
"""
from __future__ import annotations

import os
import time

import requests

VERSION = os.environ.get("GRAPH_VERSION", "v23.0")
BASE = f"https://graph.facebook.com/{VERSION}"

# Retry only what is worth retrying. A 400 means the request is wrong and will
# stay wrong; retrying it burns the hourly call budget for nothing.
RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3


class GraphError(RuntimeError):
    """A Graph API error, with the fields you actually need to debug it."""

    def __init__(self, payload: dict, status: int):
        err = (payload or {}).get("error", {})
        self.code = err.get("code")
        self.subcode = err.get("error_subcode")
        self.trace = err.get("fbtrace_id")
        self.status = status
        self.type = err.get("type")
        msg = err.get("message") or f"HTTP {status}"
        super().__init__(
            f"{msg} (code={self.code} subcode={self.subcode} "
            f"http={status} trace={self.trace})"
        )


def _request(method: str, path: str, token: str, **params) -> dict:
    url = f"{BASE}/{path.lstrip('/')}"
    payload = {k: v for k, v in params.items() if v is not None}
    payload["access_token"] = token

    last: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            if method == "GET":
                r = requests.get(url, params=payload, timeout=60)
            else:
                r = requests.post(url, data=payload, timeout=120)
        except requests.RequestException as exc:
            last = exc
            if attempt == MAX_ATTEMPTS:
                raise
            time.sleep(2 ** attempt)
            continue

        if r.status_code in RETRY_STATUS and attempt < MAX_ATTEMPTS:
            time.sleep(2 ** attempt)
            continue

        try:
            body = r.json()
        except ValueError:
            body = {}

        if not r.ok or "error" in body:
            raise GraphError(body, r.status_code)
        return body

    raise last if last else GraphError({}, 0)


def get(path: str, token: str, **params) -> dict:
    return _request("GET", path, token, **params)


def post(path: str, token: str, **params) -> dict:
    return _request("POST", path, token, **params)


def page_token(user_token: str, page_id: str) -> str:
    """Exchange a user token for the Page token that /{page-id}/feed needs.

    Instagram publishing uses the user/system-user token; Facebook Page
    publishing needs the Page's own token. Mixing them up is a common
    "(#200) Permissions error" with no further explanation.
    """
    accounts = get("me/accounts", user_token, fields="id,name,access_token")
    for acct in accounts.get("data", []):
        if acct["id"] == page_id:
            return acct["access_token"]
    have = ", ".join(a["id"] for a in accounts.get("data", [])) or "none"
    raise GraphError(
        {"error": {"message": f"page {page_id} not in /me/accounts (found: {have})"}},
        404,
    )


def check_token(token: str) -> dict:
    """Cheap daily health check. An expired token is the classic silent stop."""
    return get("me", token, fields="id,name")
