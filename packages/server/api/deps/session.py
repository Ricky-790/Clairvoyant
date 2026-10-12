"""Request-scoped dependencies: database session and the signed-in user."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from models import User
from services import users_service
from session import get_session
from sqlalchemy.ext.asyncio import AsyncSession

DbSession = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(request: Request, session: DbSession) -> User:
    """Load the signed-in user from the session cookie.

    The cookie only carries the user's primary key; the row is read on every
    request so that a deleted or modified account takes effect immediately.

    Raises:
        fastapi.HTTPException: 401 when there is no valid session.
    """
    user_id = request.session.get("user_id")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not signed in",
        )

    user = await users_service.get_by_id(session, user_id)
    if user is None:
        # Stale cookie pointing at a row that no longer exists.
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not signed in",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


__all__ = ["CurrentUser", "DbSession", "get_current_user", "get_session"]