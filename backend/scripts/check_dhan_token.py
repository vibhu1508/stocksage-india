"""Check the Dhan token in the environment before market open. Never prints the token.

Run from backend/:  python -m scripts.check_dhan_token
Exits non-zero if the token is missing, expired, for another client ID, or rejected by Dhan.
"""

import base64
import json
import os
import sys
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv

load_dotenv()

from routers.dhan_market import DHAN_BASE_URL, IST, _get_dhan_headers  # noqa: E402


def token_claims(token: str) -> dict:
    """Read the JWT payload (unverified: only Dhan can verify its own signature)."""
    part = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))


def main() -> int:
    token = os.getenv("DHAN_ACCESS_TOKEN", "").strip()
    client_id = os.getenv("DHAN_CLIENT_ID", "").strip()
    if not token or not client_id:
        print("FAIL  DHAN_ACCESS_TOKEN or DHAN_CLIENT_ID is not set")
        return 1

    try:
        claims = token_claims(token)
    except (IndexError, ValueError):
        print("FAIL  DHAN_ACCESS_TOKEN is not a JWT (copy/paste error?)")
        return 1

    expires = datetime.fromtimestamp(int(claims.get("exp", 0)), timezone.utc)
    hours_left = (expires - datetime.now(timezone.utc)).total_seconds() / 3600
    print(f"info  expires {expires.astimezone(IST):%d %b %Y %H:%M} IST ({hours_left:.1f} h left)")
    if hours_left <= 0:
        print("FAIL  token has expired")
        return 1
    if str(claims.get("dhanClientId", "")) != client_id:
        print("FAIL  token belongs to a different client ID than DHAN_CLIENT_ID")
        return 1

    resp = httpx.get(f"{DHAN_BASE_URL}/profile", headers=_get_dhan_headers(), timeout=15)
    if resp.status_code != 200:
        try:
            body = resp.json()
            why = f"{body.get('errorCode', '')} {body.get('errorMessage', '')}".strip()
        except ValueError:
            why = ""
        print(f"FAIL  Dhan rejected the token (HTTP {resp.status_code}) {why}")
        if resp.status_code == 401:
            print("hint  The token is well-formed and unexpired, so Dhan has revoked or superseded it (for example,")
            print("      a newer token was generated). Generate a fresh one on web.dhan.co and run this again.")
        return 1
    print("ok    Dhan accepted the token")
    return 0


if __name__ == "__main__":
    sys.exit(main())
