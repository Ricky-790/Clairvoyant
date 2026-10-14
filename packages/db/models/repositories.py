from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class OnboardingStatus(StrEnum):
    pending = "pending"
    processing = "processing"
    done = "done"
    failed = "failed"


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    installation_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("installations.installation_id"),
        nullable=False,
        index=True,
    )

    repo_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False, index=True
    )
    repo_full_name: Mapped[str] = mapped_column(String, nullable=False)  # "owner/repo"

    onboarded: Mapped[OnboardingStatus] = mapped_column(
        Enum(OnboardingStatus, name="onboarding_status"),
        default=OnboardingStatus.pending,
        nullable=False,
    )

    graph_data_uri: Mapped[str | None] = mapped_column(
        String, nullable=True
    )  # link to file inside storage bucket
    last_synced_commit: Mapped[str | None] = mapped_column(
        String, nullable=True
    )  # git SHA

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User", back_populates="repositories")
    installation: Mapped["Installation"] = relationship(
        "Installation", back_populates="repositories"
    )
