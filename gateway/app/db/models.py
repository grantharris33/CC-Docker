"""SQLAlchemy ORM models."""

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Float, ForeignKey, Index, Integer, String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Session(Base):
    """Session database model."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="starting")
    container_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    parent_session_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("sessions.id"), nullable=True
    )
    workspace_type: Mapped[str] = mapped_column(String(20), nullable=False)
    workspace_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    stopped_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    total_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_turns: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    parent: Mapped[Optional["Session"]] = relationship(
        "Session",
        remote_side=[id],
        back_populates="children",
        foreign_keys=[parent_session_id],
    )
    children: Mapped[list["Session"]] = relationship(
        "Session",
        back_populates="parent",
        foreign_keys=[parent_session_id],
    )
    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="session", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_sessions_status", "status"),
        Index("idx_sessions_parent", "parent_session_id"),
    )


class Message(Base):
    """Message database model."""

    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    # Relationships
    session: Mapped["Session"] = relationship("Session", back_populates="messages")

    __table_args__ = (Index("idx_messages_session", "session_id"),)
