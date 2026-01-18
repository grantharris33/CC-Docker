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


class DiscordInteraction(Base):
    """Discord interaction database model."""

    __tablename__ = "discord_interactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.id"), nullable=False
    )
    discord_thread_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    discord_message_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    interaction_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'question' or 'notification'
    message: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # 'pending', 'answered', 'timeout', 'failed'
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    priority: Mapped[str] = mapped_column(
        String(20), nullable=False, default="normal"
    )  # 'normal' or 'urgent'
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    answered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    timeout_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_discord_session", "session_id"),
        Index("idx_discord_status", "status"),
        Index("idx_discord_thread", "discord_thread_id"),
    )


class Task(Base):
    """Automated task definition model."""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    task_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Template System
    template_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    required_parameters: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    optional_parameters: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Scheduling
    schedule_cron: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    schedule_timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="UTC")
    enabled: Mapped[bool] = mapped_column(Integer, nullable=False, default=1)
    paused: Mapped[bool] = mapped_column(Integer, nullable=False, default=0)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Configuration
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Discord
    discord_channel_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    discord_category_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    discord_thread_id_current: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False)

    # Dependencies
    depends_on_tasks: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    dependency_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="all")

    # Notifications
    pushover_enabled: Mapped[bool] = mapped_column(Integer, nullable=False, default=0)
    pushover_user_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    notify_on_complete: Mapped[bool] = mapped_column(Integer, nullable=False, default=1)
    notify_on_error: Mapped[bool] = mapped_column(Integer, nullable=False, default=1)

    # Metadata
    run_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Audit
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    task_runs: Mapped[list["TaskRun"]] = relationship("TaskRun", back_populates="task", cascade="all, delete-orphan")
    dependencies: Mapped[list["TaskDependency"]] = relationship("TaskDependency", foreign_keys="TaskDependency.task_id", back_populates="task")
    schedule_history: Mapped[list["ScheduleHistory"]] = relationship("ScheduleHistory", back_populates="task", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_tasks_owner", "owner_user_id"),
        Index("idx_tasks_next_run", "next_run_at"),
        Index("idx_tasks_discord_channel", "discord_channel_id"),
    )


class TaskRun(Base):
    """Task execution run model."""

    __tablename__ = "task_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("tasks.id"), nullable=False)
    session_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("sessions.id"), nullable=True)

    # Execution details
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="scheduled")
    trigger: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    parameters: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Discord tracking
    discord_channel_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    discord_thread_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    discord_messages: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Results
    result_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    output_files: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    minio_artifacts: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Error handling
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_stacktrace: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_screenshot_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retry_of: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("task_runs.id"), nullable=True)

    # Human intervention
    required_intervention: Mapped[bool] = mapped_column(Integer, nullable=False, default=0)
    intervention_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    intervention_resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    vnc_session_active: Mapped[bool] = mapped_column(Integer, nullable=False, default=0)
    vnc_accessed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Metrics
    tokens_used: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    compute_time_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    api_calls_made: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pages_loaded: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    http_requests_made: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    data_transferred_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    step_timings: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Audit
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    task: Mapped["Task"] = relationship("Task", back_populates="task_runs")
    session: Mapped[Optional["Session"]] = relationship("Session")

    __table_args__ = (
        Index("idx_task_runs_task_id", "task_id"),
        Index("idx_task_runs_status", "status"),
        Index("idx_task_runs_started_at", "started_at"),
        Index("idx_task_runs_discord_thread", "discord_thread_id"),
    )


class TaskTemplate(Base):
    """Task template for shared library."""

    __tablename__ = "task_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    template_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    template_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    template_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    required_parameters: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    optional_parameters: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    default_config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    author_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    is_public: Mapped[bool] = mapped_column(Integer, nullable=False, default=0)
    use_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rating_average: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        Index("idx_task_templates_type", "template_type"),
        Index("idx_task_templates_public", "is_public"),
        Index("idx_task_templates_author", "author_user_id"),
    )


class TaskDependency(Base):
    """Task dependency relationship."""

    __tablename__ = "task_dependencies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("tasks.id"), nullable=False)
    depends_on_task_id: Mapped[str] = mapped_column(String(36), ForeignKey("tasks.id"), nullable=False)
    required: Mapped[bool] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    created_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Relationships
    task: Mapped["Task"] = relationship("Task", foreign_keys=[task_id], back_populates="dependencies")

    __table_args__ = (
        Index("idx_task_dependencies_task", "task_id"),
        Index("idx_task_dependencies_depends", "depends_on_task_id"),
    )


class DiscordChannel(Base):
    """Discord channel registry."""

    __tablename__ = "discord_channels"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    channel_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    channel_name: Mapped[str] = mapped_column(String(100), nullable=False)
    category_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    category_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    channel_type: Mapped[str] = mapped_column(String(20), nullable=False)

    task_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("tasks.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    extra_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("idx_discord_channels_task", "task_id"),
        Index("idx_discord_channels_category", "category_id"),
    )


class DiscordThread(Base):
    """Discord thread registry."""

    __tablename__ = "discord_threads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    thread_name: Mapped[str] = mapped_column(String(100), nullable=False)
    parent_channel_id: Mapped[str] = mapped_column(String(64), nullable=False)

    task_run_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("task_runs.id"), nullable=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("sessions.id"), nullable=True)

    status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    extra_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Relationships
    task_run: Mapped[Optional["TaskRun"]] = relationship("TaskRun")

    __table_args__ = (
        Index("idx_discord_threads_task_run", "task_run_id"),
        Index("idx_discord_threads_status", "status"),
    )


class DiscordMessage(Base):
    """Discord message log."""

    __tablename__ = "discord_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    message_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    channel_id: Mapped[str] = mapped_column(String(64), nullable=False)
    thread_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    task_run_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("task_runs.id"), nullable=True)
    interaction_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("discord_interactions.id"), nullable=True)

    message_type: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    embeds: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    attachments: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    buttons: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    sent_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    task_run: Mapped[Optional["TaskRun"]] = relationship("TaskRun")

    __table_args__ = (
        Index("idx_discord_messages_task_run", "task_run_id"),
        Index("idx_discord_messages_channel", "channel_id"),
        Index("idx_discord_messages_type", "message_type"),
    )


class ScheduleHistory(Base):
    """Schedule change history."""

    __tablename__ = "schedule_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("tasks.id"), nullable=False)

    action: Mapped[str] = mapped_column(String(50), nullable=False)
    schedule_before: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    schedule_after: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    triggered_by: Mapped[str] = mapped_column(String(20), nullable=False)
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    extra_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Relationships
    task: Mapped["Task"] = relationship("Task", back_populates="schedule_history")

    __table_args__ = (
        Index("idx_schedule_history_task", "task_id"),
        Index("idx_schedule_history_action", "action"),
    )


class PushoverNotification(Base):
    """Pushover notification log."""

    __tablename__ = "pushover_notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_run_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("task_runs.id"), nullable=True)

    user_key: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    sent_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    pushover_response: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    success: Mapped[Optional[bool]] = mapped_column(Integer, nullable=True)

    # Relationships
    task_run: Mapped[Optional["TaskRun"]] = relationship("TaskRun")

    __table_args__ = (
        Index("idx_pushover_notifications_task_run", "task_run_id"),
        Index("idx_pushover_notifications_sent_at", "sent_at"),
    )
