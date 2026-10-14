"""Helpers for the repository ingestion task."""

from __future__ import annotations

import os
import time
from pathlib import Path

import httpx
from dotenv import find_dotenv, load_dotenv
from e2b import AsyncSandbox
from e2b.sandbox.filesystem.filesystem import FileType
from joserfc import jwt
from joserfc.jwk import RSAKey

load_dotenv()

GITHUB_API_URL: str = os.getenv("GITHUB_API_URL", "https://api.github.com")
APP_ID: str = os.getenv("APP_ID", "")

_key: RSAKey | None = None


def _private_key() -> RSAKey:
    """Load the GitHub App private key, caching it between calls."""
    global _key
    if _key is None:
        path = Path(os.getenv("GITHUB_PRIVATE_KEY_PATH", ""))
        if not path.is_absolute():
            # The configured path is relative; anchor it to the repo root that
            # holds .env so a worker started elsewhere still finds the key.
            path = Path(find_dotenv()).parent / path
        _key = RSAKey.import_key(path.read_text(encoding="utf-8"))
    return _key


def generate_app_jwt() -> str:
    """Sign a short-lived App JWT for authenticating as the GitHub App."""
    now = int(time.time())
    return jwt.encode(
        {"alg": "RS256", "kid": os.getenv("GITHUB_CLIENT_ID", "")},
        {"iat": now - 60, "exp": now + 540, "iss": APP_ID},
        _private_key(),
    )


async def get_installation_token(installation_id: int) -> str:
    """Mint an installation token scoped to one installation."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GITHUB_API_URL}/app/installations/{installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {generate_app_jwt()}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
    resp.raise_for_status()
    return resp.json()["token"]


def build_clone_url(installation_token: str, repo_full_name: str) -> str:
    """Authenticated clone URL for a repo the installation can read."""
    return (
        f"https://x-access-token:{installation_token}"
        f"@github.com/{repo_full_name}.git"
    )


async def export_directory(
    sandbox: AsyncSandbox, remote_dir: str, local_dir: Path
) -> int:
    """Copy a sandbox directory to local disk; returns the files written."""
    local_dir.mkdir(parents=True, exist_ok=True)
    written = 0

    for entry in await sandbox.files.list(remote_dir, depth=1):
        target = local_dir / entry.name
        if entry.type is FileType.DIR:
            written += await export_directory(sandbox, entry.path, target)
        elif entry.type is FileType.FILE:
            # Read as bytes: graph output is not reliably text.
            data = await sandbox.files.read(entry.path, format="bytes")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            written += 1

    return written


def bucket_dir(user_id: int, repository_id: int) -> Path:
    """Local destination for one repository's graph output."""
    return (
        Path(os.getenv("BUCKET_URI", "/data/graphs/"))
        / f"{user_id}-{repository_id}"
        / "graphify-out"
    )