from __future__ import annotations

import asyncio
from typing import Any

from api.deps.session import CurrentUser, DbSession
from api.utils import github
from fastapi import APIRouter
from services import installations_service

router = APIRouter(tags=["Repos"])


def _summarise(
    repo: dict[str, Any], installation_id: int, account: str
) -> dict[str, Any]:
    return {
        "id": repo.get("id"),
        "name": repo.get("name"),
        "full_name": repo.get("full_name"),
        "private": bool(repo.get("private")),
        "description": repo.get("description"),
        "language": repo.get("language"),
        "stargazers_count": repo.get("stargazers_count"),
        "default_branch": repo.get("default_branch"),
        "html_url": repo.get("html_url"),
        "installation_id": installation_id,
        "account_login": account,
    }


async def _repos_for(
    installation_id: int, account_login: str
) -> tuple[list[dict[str, Any]], str | None]:
    try:
        token = await github.create_installation_token(installation_id)
        repos = await github.list_installation_repositories(token)
    except Exception as exc:
        return [], str(exc)
    return [_summarise(r, installation_id, account_login) for r in repos], None


@router.get("/repos")
async def list_repos(user: CurrentUser, session: DbSession):
    """List every repository reachable through the user's installations."""
    installations = await installations_service.list_for_user(session, user.id)

    results = await asyncio.gather(
        *(
            _repos_for(i.installation_id, i.account_login)
            for i in installations
        )
    )

    repositories: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for installation, (repos, error) in zip(installations, results, strict=True):
        repositories.extend(repos)
        if error:
            # One broken installation must not hide the repos of the others.
            errors.append(
                {
                    "installation_id": installation.installation_id,
                    "account_login": installation.account_login,
                    "error": error,
                }
            )

    repositories.sort(key=lambda r: (r["account_login"] or "", r["full_name"] or ""))
    return {
        "repositories": repositories,
        "errors": errors,
        "installations": [
            {
                "id": i.id,
                "installation_id": i.installation_id,
                "account_login": i.account_login,
            }
            for i in installations
        ],
    }
