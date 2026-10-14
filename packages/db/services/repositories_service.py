"""Persistence operations for :class:`models.repositories.Repository`.

Transaction policy
------------------
Same contract as :mod:`services.users_service`: the caller passes in the
:class:`~sqlalchemy.ext.asyncio.AsyncSession`, and these methods only
``flush()`` -- committing is the caller's decision.
"""

from __future__ import annotations

from typing import Any

from models.repositories import OnboardingStatus, Repository
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Sentinel so that ``update`` can tell "leave this column alone" apart from
# "set this nullable column back to NULL".
_UNSET: Any = object()


def _coerce(value: OnboardingStatus | str | None) -> OnboardingStatus | None:
    """Accept either the enum or its raw string value."""
    return None if value is None else OnboardingStatus(value)


class RepositoryService:
    """Persistence operations for :class:`~models.repositories.Repository`."""

    async def get_by_id(
        self, session: AsyncSession, repository_id: int
    ) -> Repository | None:
        """Return the row with this local primary key, or ``None``."""
        return await session.get(Repository, repository_id)

    async def get_by_repo_id(
        self, session: AsyncSession, repo_id: int
    ) -> Repository | None:
        """Return the row for this GitHub repository id, or ``None``.

        ``repo_id`` is the numeric id GitHub assigns a repository, not the
        local primary key.
        """
        result = await session.execute(
            select(Repository).where(Repository.repo_id == repo_id)
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self,
        session: AsyncSession,
        user_id: int,
        *,
        onboarded: OnboardingStatus | str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Repository]:
        """Return a user's repositories ordered by full name.

        Args:
            onboarded: when given, only rows in that onboarding state.
        """
        stmt = select(Repository).where(Repository.user_id == user_id)
        status = _coerce(onboarded)
        if status is not None:
            stmt = stmt.where(Repository.onboarded == status)
        result = await session.execute(
            stmt.order_by(Repository.repo_full_name, Repository.id)
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def list_for_installation(
        self,
        session: AsyncSession,
        installation_id: int,
        *,
        onboarded: OnboardingStatus | str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Repository]:
        """Return an installation's repositories ordered by full name.

        Args:
            installation_id: the *GitHub* installation id, which is what
                ``Repository.installation_id`` foreign keys to -- not
                ``Installation.id``.
        """
        stmt = select(Repository).where(Repository.installation_id == installation_id)
        status = _coerce(onboarded)
        if status is not None:
            stmt = stmt.where(Repository.onboarded == status)
        result = await session.execute(
            stmt.order_by(Repository.repo_full_name, Repository.id)
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count_for_user(
        self,
        session: AsyncSession,
        user_id: int,
        *,
        onboarded: OnboardingStatus | str | None = None,
    ) -> int:
        """Count a user's repositories, optionally filtered by state."""
        stmt = select(func.count()).select_from(Repository).where(
            Repository.user_id == user_id
        )
        status = _coerce(onboarded)
        if status is not None:
            stmt = stmt.where(Repository.onboarded == status)
        result = await session.execute(stmt)
        return int(result.scalar_one())

    async def create(
        self,
        session: AsyncSession,
        *,
        repo_id: int,
        repo_full_name: str,
        user_id: int,
        installation_id: int,
        onboarded: OnboardingStatus | str = OnboardingStatus.pending,
        graph_data_uri: str | None = None,
        last_synced_commit: str | None = None,
    ) -> Repository:
        """Insert a new repository and return it, flushed.

        Raises:
            sqlalchemy.exc.IntegrityError: if ``repo_id`` already exists, or
                either foreign key does not resolve to a user/installation.
        """
        repository = Repository(
            repo_id=repo_id,
            repo_full_name=repo_full_name,
            user_id=user_id,
            installation_id=installation_id,
            onboarded=_coerce(onboarded),  # type: ignore[arg-type]
            graph_data_uri=graph_data_uri,
            last_synced_commit=last_synced_commit,
        )
        session.add(repository)
        await session.flush()
        return repository

    async def upsert_by_repo_id(
        self,
        session: AsyncSession,
        *,
        repo_id: int,
        repo_full_name: str,
        user_id: int,
        installation_id: int,
    ) -> Repository:
        """Record a repository, creating it the first time it is seen.

        This is the sync path: the ``onboarded`` state and the sync metadata
        are deliberately left alone so that a re-sync does not reset a
        repository that is already being processed.

        Ownership is sticky: ``repo_id`` is globally unique, so an existing
        row is reused and only ``repo_full_name`` is refreshed -- ``user_id``
        and ``installation_id`` are not reassigned. Reassigning would
        silently move a repository away from the user who onboarded it.
        """
        repository = await self.get_by_repo_id(session, repo_id)
        if repository is None:
            return await self.create(
                session,
                repo_id=repo_id,
                repo_full_name=repo_full_name,
                user_id=user_id,
                installation_id=installation_id,
            )

        repository.repo_full_name = repo_full_name
        await session.flush()
        return repository

    async def update(
        self,
        session: AsyncSession,
        repo_id: int,
        *,
        onboarded: OnboardingStatus | str | None = None,
        repo_full_name: str | None = None,
        graph_data_uri: Any = _UNSET,
        last_synced_commit: Any = _UNSET,
    ) -> Repository:
        """Update the mutable columns of a repository and return it.

        Columns left out are untouched; passing ``None`` for ``graph_data_uri``
        or ``last_synced_commit`` explicitly clears them.

        Raises:
            LookupError: if no repository has this GitHub ``repo_id``.
        """
        repository = await self.get_by_repo_id(session, repo_id)
        if repository is None:
            raise LookupError(f"No repository with repo_id {repo_id}")

        status = _coerce(onboarded)
        if status is not None:
            repository.onboarded = status
        if repo_full_name is not None:
            repository.repo_full_name = repo_full_name
        if graph_data_uri is not _UNSET:
            repository.graph_data_uri = graph_data_uri
        if last_synced_commit is not _UNSET:
            repository.last_synced_commit = last_synced_commit

        await session.flush()
        return repository

    async def update_onboarding_status(
        self, session: AsyncSession, repo_id: int, onboarded: OnboardingStatus | str
    ) -> Repository:
        """Move a repository to a new onboarding state.

        Raises:
            LookupError: if no repository has this GitHub ``repo_id``.
        """
        return await self.update(session, repo_id, onboarded=onboarded)

    async def delete(self, session: AsyncSession, repo_id: int) -> bool:
        """Delete one repository by GitHub id; ``False`` if not found."""
        repository = await self.get_by_repo_id(session, repo_id)
        if repository is None:
            return False
        await session.delete(repository)
        await session.flush()
        return True

    async def delete_for_user(self, session: AsyncSession, user_id: int) -> int:
        """Delete every repository owned by a user, returning the row count."""
        result = await session.execute(
            delete(Repository).where(Repository.user_id == user_id)
        )
        return int(result.rowcount or 0)

    async def delete_for_installation(
        self, session: AsyncSession, installation_id: int
    ) -> int:
        """Delete every repository under an installation, returning the count.

        ``installation_id`` is the GitHub installation id.
        """
        result = await session.execute(
            delete(Repository).where(Repository.installation_id == installation_id)
        )
        return int(result.rowcount or 0)


repositories_service = RepositoryService()