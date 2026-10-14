"""Repository ingestion: clone a repo into a sandbox and extract its graph."""

from __future__ import annotations

import asyncio
import os
import traceback

from celery import Task
from e2b import AsyncSandbox
from models import OnboardingStatus
from resources import SandboxFactory, SandboxService
from services import repositories_service
from session.session import get_session_factory
from workers.celery_app import celery_app

from .utils import (
    bucket_dir,
    build_clone_url,
    export_directory,
    get_installation_token,
)

REPO_DIR = "/home/user/repo"
OUTPUT_DIR = "graphify-out"
# Snapshot with uv + graphify already installed; sandboxes are created from it.
SNAPSHOT_ID = os.getenv("GRAPHIFY_UV_SNAPSHOT_ID", "")
# uv installs under ~/.local/bin, which a fresh shell's PATH does not include.
PATH_PREFIX = 'export PATH="$HOME/.local/bin:$PATH";'


@celery_app.task(bind=True, name="workers.ingest_repository")
def ingest_repository_task(self: Task, repository_id: int) -> None:
    """Ingest a repository by its internal id."""
    try:
        asyncio.run(_ingest(repository_id))
    except Exception as e:
        traceback.print_exc()


async def _ingest(repository_id: int) -> None:
    """Run the ingestion pipeline for one repository."""
    # get_session() is a FastAPI dependency, not a context manager.
    async with get_session_factory()() as session:
        repo = await repositories_service.get_by_id(session, repository_id)
        if repo is None:
            raise LookupError(f"No repository with id {repository_id}")
        if not SNAPSHOT_ID:
            raise RuntimeError("GRAPHIFY_UV_SNAPSHOT_ID is not set")

        await repositories_service.update_onboarding_status(
            session, repo.repo_id, OnboardingStatus.processing
        )
        await session.commit()

        sandbox_id: str | None = None
        try:
            sandbox_id = await SandboxFactory().create_sandbox(template=SNAPSHOT_ID)
            service = SandboxService(sbx_id=sandbox_id)

            token = await get_installation_token(repo.installation_id)

            result = await service.run_command(
                f"git clone --depth 1 "
                f"{build_clone_url(token, repo.repo_full_name)} {REPO_DIR}"
            )
            if result.exit_code != 0:
                raise RuntimeError(f"could not clone the repo: {result.stderr}")

            result = await service.run_command(
                f"{PATH_PREFIX} graphify extract . --code-only", cwd=REPO_DIR
            )
            if result.exit_code != 0:
                raise RuntimeError(f"graphify extract failed: {result.stderr}")

            destination = bucket_dir(repo.user_id, repository_id)
            files = await export_directory(
                await AsyncSandbox.connect(sandbox_id),
                f"{REPO_DIR}/{OUTPUT_DIR}",
                destination,
            )
            if files == 0:
                raise RuntimeError(f"{OUTPUT_DIR} was empty or missing after extract")

            await repositories_service.update(
                session,
                repo.repo_id,
                onboarded=OnboardingStatus.done,
                graph_data_uri=str(destination),
            )
            await session.commit()
        except Exception:
            await repositories_service.update_onboarding_status(
                session, repo.repo_id, OnboardingStatus.failed
            )
            await session.commit()
            raise
        finally:
            if sandbox_id is not None:
                await SandboxService(sbx_id=sandbox_id).close_sandbox()
