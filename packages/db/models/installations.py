from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

# from .users import User


class Installation(Base):
    __tablename__ = "installations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    installation_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False, index=True
    )
    """
    installation_id is the credential for calling GitHub’s API as this installation
    POST /app/installations/{installation_id}/access_tokens
    It mints a short-lived installation access token with which we can call:
    - GET /installation/repositories — the repos this installation can access
    - POST /repos/{owner}/{repo}/pulls — open a PR
    - POST /repos/{owner}/{repo}/issues/{number}/comments
    """
    account_login: Mapped[str] = mapped_column(String, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User", back_populates="installations")

    repositories: Mapped[list["Repository"]] = relationship(
        "Repository", back_populates="installation", cascade="all, delete-orphan"
    )
