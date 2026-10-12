from __future__ import annotations

from models.installations import Installation
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession


class InstallationService:
    """Persistence operations for :class:`~models.installations.Installation`."""

    async def get_by_id(
        self, session: AsyncSession, installation_pk: int
    ) -> Installation | None:
        """Return the installation with this primary key, or ``None``."""
        return await session.get(Installation, installation_pk)

    async def get_by_installation_id(
        self, session: AsyncSession, installation_id: int
    ) -> Installation | None:
        """Return the row for this GitHub installation id, or ``None``.

        ``installation_id`` is the id GitHub sends back on the OAuth callback
        (e.g. ``52733801``), not the local primary key.
        """
        result = await session.execute(
            select(Installation).where(Installation.installation_id == installation_id)
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self, session: AsyncSession, user_id: int
    ) -> list[Installation]:
        """Return every installation owned by a user, ordered by account login."""
        result = await session.execute(
            select(Installation)
            .where(Installation.user_id == user_id)
            .order_by(Installation.account_login, Installation.id)
        )
        return list(result.scalars().all())

    async def create(
        self,
        session: AsyncSession,
        *,
        installation_id: int,
        account_login: str,
        user_id: int,
    ) -> Installation:
        """Insert a new installation and return it, flushed.

        Raises:
            sqlalchemy.exc.IntegrityError: if ``installation_id`` already
                exists, or ``user_id`` references no user.
        """
        installation = Installation(
            installation_id=installation_id,
            account_login=account_login,
            user_id=user_id,
        )
        session.add(installation)
        await session.flush()
        return installation

    async def upsert(
        self,
        session: AsyncSession,
        *,
        installation_id: int,
        account_login: str,
        user_id: int,
    ) -> Installation:
        """Attach an installation to a user, creating it on first sign-in.

        Ownership is sticky: ``installation_id`` is globally unique, so if the
        installation is already recorded the existing row is reused, only
        ``account_login`` is refreshed, and ``user_id`` is *not* reassigned.
        Reassigning would silently move an org's installation away from the
        user who installed it.
        """
        installation = await self.get_by_installation_id(session, installation_id)
        if installation is None:
            return await self.create(
                session,
                installation_id=installation_id,
                account_login=account_login,
                user_id=user_id,
            )

        installation.account_login = account_login
        await session.flush()
        return installation

    async def delete(self, session: AsyncSession, installation_id: int) -> bool:
        """Delete one installation by GitHub id; ``False`` if not found."""
        installation = await self.get_by_installation_id(session, installation_id)
        if installation is None:
            return False
        await session.delete(installation)
        await session.flush()
        return True

    async def delete_for_user(self, session: AsyncSession, user_id: int) -> int:
        """Delete every installation owned by a user, returning the row count."""
        result = await session.execute(
            delete(Installation).where(Installation.user_id == user_id)
        )
        return int(result.rowcount or 0)


installations_service = InstallationService()
