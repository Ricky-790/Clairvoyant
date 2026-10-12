from __future__ import annotations

from datetime import datetime

from models.users import User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _encode_token(value: str | bytes) -> bytes:
    """Normalise a GitHub token into the ``bytes`` the model column holds."""
    return value if isinstance(value, bytes) else value.encode("utf-8")


class UserService:
    """Persistence operations for :class:`~models.users.User`."""

    async def get_by_id(self, session: AsyncSession, user_id: int) -> User | None:
        """Return the user with this primary key, or ``None`` if unknown."""
        return await session.get(User, user_id)

    async def get_by_github_id(
        self, session: AsyncSession, github_id: int
    ) -> User | None:
        """Return the user with this GitHub account id, or ``None``."""
        result = await session.execute(select(User).where(User.github_id == github_id))
        return result.scalar_one_or_none()

    async def create(
        self,
        session: AsyncSession,
        *,
        github_id: int,
        login: str,
        access_token: str | bytes,
        avatar_url: str | None = None,
        refresh_token: str | bytes | None = None,
        token_expires_at: datetime | None = None,
    ) -> User:
        """Insert a new user and return it, flushed.

        Raises:
            sqlalchemy.exc.IntegrityError: if ``github_id`` already exists.
        """
        user = User(
            github_id=github_id,
            login=login,
            avatar_url=avatar_url,
            access_token=_encode_token(access_token),
            refresh_token=(
                None if refresh_token is None else _encode_token(refresh_token)
            ),
            token_expires_at=token_expires_at,
        )
        session.add(user)
        await session.flush()
        return user

    async def upsert_by_github_id(
        self,
        session: AsyncSession,
        *,
        github_id: int,
        login: str,
        access_token: str | bytes,
        avatar_url: str | None = None,
        refresh_token: str | bytes | None = None,
        token_expires_at: datetime | None = None,
    ) -> User:
        """Find the user by GitHub id, or create them; refresh their tokens.

        This is the write path used by the OAuth callback: a returning user
        keeps their primary key (and therefore their installations) while the
        stored tokens are always replaced with the freshly issued ones.

        ``refresh_token=None`` leaves any existing refresh token untouched
        rather than clearing it, because GitHub only returns a new refresh
        token when one is actually re-issued.
        """
        user = await self.get_by_github_id(session, github_id)
        if user is None:
            return await self.create(
                session,
                github_id=github_id,
                login=login,
                access_token=access_token,
                avatar_url=avatar_url,
                refresh_token=refresh_token,
                token_expires_at=token_expires_at,
            )

        user.login = login
        user.avatar_url = avatar_url
        user.access_token = _encode_token(access_token)
        user.token_expires_at = token_expires_at
        if refresh_token is not None:
            user.refresh_token = _encode_token(refresh_token)

        await session.flush()
        return user

    async def update_tokens(
        self,
        session: AsyncSession,
        user_id: int,
        *,
        access_token: str | bytes,
        token_expires_at: datetime | None = None,
        refresh_token: str | bytes | None = None,
    ) -> User:
        """Replace a user's OAuth tokens and return the updated user.

        ``refresh_token=None`` leaves the existing one untouched.

        Raises:
            LookupError: if no user has this ``user_id``.
        """
        user = await self.get_by_id(session, user_id)
        if user is None:
            raise LookupError(f"No user with id {user_id}")

        user.access_token = _encode_token(access_token)
        user.token_expires_at = token_expires_at
        if refresh_token is not None:
            user.refresh_token = _encode_token(refresh_token)

        await session.flush()
        return user

    async def get_access_token(self, session: AsyncSession, user_id: int) -> str | None:
        """Return the user's access token decoded to ``str``, or ``None``.

        Convenient when only the token is needed, since the model stores it
        as ``bytes``.
        """
        user = await self.get_by_id(session, user_id)
        if user is None or not user.access_token:
            return None
        return bytes(user.access_token).decode("utf-8")

    async def list_all(
        self, session: AsyncSession, *, limit: int = 100, offset: int = 0
    ) -> list[User]:
        """Return a page of users ordered by primary key."""
        result = await session.execute(
            select(User).order_by(User.id).limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    async def delete(self, session: AsyncSession, user_id: int) -> bool:
        """Delete a user and their installations; ``False`` if not found.

        The mapper cascade on ``User.installations`` removes the child rows.
        """
        user = await self.get_by_id(session, user_id)
        if user is None:
            return False
        await session.delete(user)
        await session.flush()
        return True


users_service = UserService()
