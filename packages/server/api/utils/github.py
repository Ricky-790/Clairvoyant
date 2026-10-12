from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from joserfc import jwt
from joserfc.jwk import RSAKey

load_dotenv()

APP_URL: str = os.getenv("APP_URL", "")
CALLBACK_URL: str = os.getenv("GITHUB_CALLBACK_URL", "")
CLIENT_SECRET: str = os.getenv("GITHUB_CLIENT_SECRET", "")
GITHUB_TOKEN_URL: str = os.getenv("GITHUB_TOKEN_URL", "")
CLIENT_ID: str = os.getenv("GITHUB_CLIENT_ID", "")
APP_ID: str = os.getenv("APP_ID", "")
API_URL: str = os.getenv("GITHUB_API_URL", "https://api.github.com")

API_VERSION = "2022-11-28"
_APP_JWT_TTL = 540  # GitHub caps app JWTs at 10 minutes; backdate to absorb skew.

_private_key: RSAKey | None = None


def _key() -> RSAKey:
    global _private_key
    if _private_key is None:
        path = os.getenv("GITHUB_PRIVATE_KEY_PATH", "")
        if not path:
            raise RuntimeError("GITHUB_PRIVATE_KEY_PATH is not set")
        pem = Path(path).read_text(encoding="utf-8")
        _private_key = RSAKey.import_key(pem)
    return _private_key


def app_jwt() -> str:
    now = int(time.time())
    return jwt.encode(
        {"alg": "RS256", "typ": "JWT", "kid": CLIENT_ID},
        {
            "iat": now - 60,  # backdate to tolerate clock skew
            "exp": now + _APP_JWT_TTL,
            "iss": APP_ID,
        },
        _key(),
    )


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
    }


async def exchange_code(code: str) -> dict[str, Any]:
    """Trade temp code for a user access token from github server"""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            GITHUB_TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "code": code,
            },
        )

    if resp.status_code >= 400:
        raise RuntimeError(f"GitHub token exchange failed: HTTP {resp.status_code}")

    data = resp.json()
    if "error" in data:
        # e.g. "bad_verification_code" if the code expired or was already used
        raise RuntimeError(data.get("error_description") or data["error"])
    if "access_token" not in data:
        raise RuntimeError(f"Unexpected token response: {sorted(data)}")
    return data


async def get_user(access_token: str) -> dict[str, Any]:
    "Get user details from zgithub public api using access token"
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{API_URL}/user", headers=_headers(access_token))
    resp.raise_for_status()
    return resp.json()


async def list_user_installations(access_token: str) -> list[dict[str, Any]]:
    """gives accounts/orgs the user has connected"""
    installations: list[dict[str, Any]] = []
    async with httpx.AsyncClient() as client:
        page = 1
        while True:
            resp = await client.get(
                f"{API_URL}/user/installations",
                headers=_headers(access_token),
                params={"per_page": 100, "page": page},
            )
            resp.raise_for_status()
            installations.extend(resp.json().get("installations", []))

            if 'rel="next"' not in resp.headers.get("link", ""):
                return installations
            page += 1


async def get_installation(installation_id: int | str) -> dict[str, Any]:
    """Fetch a single installation's details.

    Used as a fallback when a freshly created installation has not shown up in
    ``/user/installations`` yet.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_URL}/app/installations/{installation_id}",
            headers=_headers(app_jwt()),
        )
    resp.raise_for_status()
    return resp.json()


async def create_installation_token(installation_id: int) -> str:
    """Mint an installation access token, scoped to one installation's repos."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{API_URL}/app/installations/{installation_id}/access_tokens",
            headers=_headers(app_jwt()),
        )
    resp.raise_for_status()
    return resp.json()["token"]


async def list_installation_repositories(
    installation_token: str, *, per_page: int = 100
) -> list[dict[str, Any]]:
    """List every repository an installation token can reach."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_URL}/installation/repositories",
            headers=_headers(installation_token),
            params={"per_page": per_page},
        )
    resp.raise_for_status()
    return list(resp.json().get("repositories", []))


def authorize_url_params(state: str) -> dict:
    return {
        "client_id": CLIENT_ID,
        "redirect_uri": CALLBACK_URL,
        "state": state,
    }
