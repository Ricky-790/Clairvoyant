from __future__ import annotations

import asyncio
from typing import Any

from api.deps.session import CurrentUser, DbSession
from api.routes.schemas.schemas import StandardResponse
from api.utils import github
from fastapi import APIRouter
from fastapi.exceptions import HTTPException
from models import OnboardingStatus
from services import installations_service, repositories_service
from starlette.requests import Request
from workers.processes.ingestion import ingest_repository_task

from .schemas import StartIngestionRequest

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
        *(_repos_for(i.installation_id, i.account_login) for i in installations)
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


@router.post("/repos/ingest", response_model=StandardResponse)
async def start_ingestion(
    request: Request, body: StartIngestionRequest, session: DbSession
):
    """Queue ingestion for a repository."""
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    installation = await installations_service.get_by_installation_id(
        session, body.installation_id
    )
    # check if app is installed & user is authorized to it.
    if not installation or installation.user_id != user_id:
        raise HTTPException(
            status_code=403,
            detail="Installation not found/unauthorized",
        )
    repo = await repositories_service.get_by_repo_id(session, body.repo_id)
    if repo is None:
        repo = await repositories_service.create(
            session,
            user_id=user_id,
            installation_id=body.installation_id,
            repo_id=body.repo_id,
            repo_full_name=body.repo_full_name,
            onboarded=OnboardingStatus.pending,
        )
    else:
        if repo.onboarded == OnboardingStatus.processing:
            raise HTTPException(status_code=409, detail="Ingestion already in progress")
        await repositories_service.update_onboarding_status(
            session, repo.repo_id, OnboardingStatus.pending
        )

    await session.commit()

    # enqueue the Celery task — only the internal repo id needed, task re-derives the rest
    ingest_repository_task.delay(repo.id)

    return StandardResponse(message="Queued")
