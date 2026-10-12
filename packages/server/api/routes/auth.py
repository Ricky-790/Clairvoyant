from __future__ import annotations

import os
import secrets
from urllib.parse import urlencode

from api.deps.session import CurrentUser, DbSession
from api.utils import github
from api.utils.utils import encrypt_token
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Request, status
from services import installations_service, users_service
from starlette.responses import RedirectResponse

load_dotenv()

router = APIRouter(prefix="/auth", tags=["Auth"])

FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")
GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
# GITHUB_INSTALL_URL = "https://github.com/apps/YOUR_APP_NAME/installations/new"


def _dashboard_url() -> str:
    return f"{FRONTEND_URL.rstrip('/')}/dashboard"


@router.get("/github/login")
async def login(request: Request):
    state: str = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state
    params = github.authorize_url_params(state)
    return RedirectResponse(f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}")


@router.get("/github/install")
async def install(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(401, "Must be logged in to connect a repository")

    state: str = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state
    return RedirectResponse(f"{github.APP_URL}?state={state}")


@router.get("/github/callback")
async def callback(
    request: Request,
    session: DbSession,
    code: str,
    state: str,
    installation_id: str | None = None,
):
    # Exchange the OAuth code, persist the user, and return to the frontend
    if state != request.session.pop("oauth_state", None):
        raise HTTPException(
            detail="Mismatching session state token",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    try:
        token_data = await github.exchange_code(code)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user_token: str = token_data["access_token"]

    try:
        profile = await github.get_user(user_token)
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Could not load the GitHub profile: {exc}"
        ) from exc

    user = await users_service.upsert_by_github_id(
        session,
        github_id=profile["id"],
        login=profile["login"],
        access_token=encrypt_token(user_token),
        avatar_url=profile.get("avatar_url"),
        refresh_token=token_data.get("refresh_token"),
    )

    try:
        visible = await github.list_user_installations(user_token)
    except Exception as exc:
        # Without this list we cannot populate the dashboard, unless GitHub at least told us which installation was just created.
        if installation_id is None:
            raise HTTPException(
                status_code=502, detail=f"Could not list installations: {exc}"
            ) from exc
        visible = []

    known = {str(i.get("id")) for i in visible}
    if installation_id is not None and installation_id not in known:
        # A brand new installation may not appear in /user/installations yet.
        try:
            visible.append(await github.get_installation(installation_id))
        except Exception:
            pass

    for installation in visible:
        installation_id_value = installation.get("id")
        if installation_id_value is None:
            continue
        account = installation.get("account") or {}
        await installations_service.upsert(
            session,
            installation_id=installation_id_value,
            account_login=account.get("login") or "unknown",
            user_id=user.id,
        )

    await session.commit()

    request.session["user_id"] = user.id
    return RedirectResponse(_dashboard_url())


@router.get("/me")
async def me(user: CurrentUser):
    """Return the signed-in user, so the frontend knows what to render."""
    return {
        "id": user.id,
        "github_id": user.github_id,
        "login": user.login,
        "avatar_url": user.avatar_url,
    }


@router.post("/logout")
async def logout(request: Request):
    """Clear the session cookie."""
    request.session.clear()
    return {"ok": True}
