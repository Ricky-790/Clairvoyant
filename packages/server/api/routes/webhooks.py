from api.deps import DbSession
from api.utils import verify_signature
from fastapi import APIRouter, HTTPException, Request, status
from services.installations_service import installations_service
from services.users_service import users_service

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post("/github")
async def github_webhook(request: Request, session: DbSession):
    body = await request.body()
    verify_signature(body, request.headers.get("X-Hub-Signature-256"))

    event = request.headers["X-GitHub-Event"]
    payload = await request.json()

    if event == "installation" and payload["action"] == "deleted":
        await handle_installation_deleted(session, payload)

    elif event == "issues" and payload["action"] == "opened":
        await handle_issue_opened(session, payload)

    elif event == "issue_comment" and payload["action"] == "created":
        await handle_issue_comment_created(session, payload)

    return {"ok": True}


async def handle_installation_deleted(session: DbSession, payload: dict):
    """User uninstalled the App: remove from db"""
    installation_id = payload["installation"]["id"]
    await installations_service.delete(session, installation_id)
    await session.commit()


async def handle_issue_opened(session: DbSession, payload: dict):
    installation_id = payload["installation"]["id"]
    repo_full_name = payload["repository"]["full_name"]
    issue_number = payload["issue"]["number"]
    issue_title = payload["issue"]["title"]
    issue_body = payload["issue"]["body"]

    installation = await installations_service.get_by_installation_id(
        session, installation_id
    )
    if installation is None:
        # webhook for an installation we don't know about — ignore
        return
    print("An issue has been created")
    await enqueue_agent_job(
        kind="issue_opened",
        user_id=installation.user_id,
        installation_id=installation_id,
        repo=repo_full_name,
        issue_number=issue_number,
        issue_title=issue_title,
        issue_body=issue_body,
    )


async def handle_issue_comment_created(session: DbSession, payload: dict):
    """A comment was posted on an issue.

    GitHub fires `issue_comment` for comments on BOTH issues and pull
    requests, because PRs are internally a type of issue. `issue.pull_request`
    is only present when it's actually a PR — filter those out here, since
    we only want genuine issue comments for this handler.
    """
    if "pull_request" in payload["issue"]:
        return  # this is a comment on a PR, not a plain issue — ignore

    installation_id = payload["installation"]["id"]
    repo_full_name = payload["repository"]["full_name"]
    issue_number = payload["issue"]["number"]
    comment_body = payload["comment"]["body"]
    comment_author = payload["comment"]["user"]["login"]

    installation = await installations_service.get_by_installation_id(
        session, installation_id
    )
    if installation is None:
        return

    await enqueue_agent_job(
        kind="issue_comment",
        user_id=installation.user_id,
        installation_id=installation_id,
        repo=repo_full_name,
        issue_number=issue_number,
        comment_body=comment_body,
        comment_author=comment_author,
    )


async def enqueue_agent_job(**kwargs):
    """Stub — swap for Cloud Tasks/Pub/Sub later, or asyncio.create_task for local dev."""
    print(f"Agent job triggered: {kwargs}")
