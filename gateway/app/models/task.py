"""Task-related Pydantic models."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Task run status enum."""

    SCHEDULED = "scheduled"
    WAITING_DEPENDENCY = "waiting_dependency"
    STARTING = "starting"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TriggerType(str, Enum):
    """Task trigger type enum."""

    SCHEDULED = "scheduled"
    MANUAL = "manual"
    DEPENDENCY = "dependency"
    RETRY = "retry"


class TaskConfig(BaseModel):
    """Task configuration."""

    mcp_servers: List[str] = Field(default_factory=lambda: ["playwright", "cc-docker"])
    timeout_seconds: int = Field(default=1800, ge=60, le=7200)
    require_approval: bool = Field(default=False)
    failure_retry_count: int = Field(default=3, ge=0, le=10)
    failure_retry_delay: int = Field(default=300, ge=60)
    max_concurrent_runs: int = Field(default=1, ge=1, le=5)


class TaskCreate(BaseModel):
    """Request body for creating a task."""

    task_name: str = Field(..., min_length=1, max_length=255, pattern="^[a-z0-9-]+$")
    task_type: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = None
    template_prompt: str = Field(..., min_length=1)
    required_parameters: Optional[List[str]] = Field(default_factory=list)
    optional_parameters: Optional[Dict[str, Any]] = Field(default_factory=dict)
    config: TaskConfig = Field(default_factory=TaskConfig)
    schedule_cron: Optional[str] = None
    schedule_timezone: str = Field(default="UTC")
    owner_user_id: str = Field(..., description="Discord user ID")
    discord_category_name: Optional[str] = None


class TaskUpdate(BaseModel):
    """Request body for updating a task."""

    description: Optional[str] = None
    template_prompt: Optional[str] = None
    required_parameters: Optional[List[str]] = None
    optional_parameters: Optional[Dict[str, Any]] = None
    config: Optional[TaskConfig] = None
    schedule_cron: Optional[str] = None
    schedule_timezone: Optional[str] = None
    enabled: Optional[bool] = None
    paused: Optional[bool] = None
    notify_on_complete: Optional[bool] = None
    notify_on_error: Optional[bool] = None


class TaskSchedule(BaseModel):
    """Request body for scheduling a task."""

    schedule_cron: str = Field(..., min_length=9, max_length=100)
    schedule_timezone: str = Field(default="UTC")
    default_parameters: Optional[Dict[str, Any]] = None


class TaskStart(BaseModel):
    """Request body for starting a task."""

    parameters: Dict[str, Any] = Field(default_factory=dict)
    force: bool = Field(default=False, description="Force start even if already running")


class TaskResponse(BaseModel):
    """Response for task operations."""

    id: str
    task_name: str
    task_type: str
    description: Optional[str]
    template_prompt: str
    required_parameters: Optional[List[str]]
    optional_parameters: Optional[Dict[str, Any]]
    schedule_cron: Optional[str]
    schedule_timezone: str
    enabled: bool
    paused: bool
    next_run_at: Optional[datetime]
    last_run_at: Optional[datetime]
    discord_channel_id: Optional[str]
    discord_category_id: Optional[str]
    owner_user_id: str
    run_count: int
    success_count: int
    failure_count: int
    avg_duration_seconds: Optional[int]
    created_at: datetime
    updated_at: datetime


class TaskRunResponse(BaseModel):
    """Response for task run operations."""

    id: str
    task_id: str
    task_name: str
    session_id: Optional[str]
    status: TaskStatus
    trigger: TriggerType
    parameters: Optional[Dict[str, Any]]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_seconds: Optional[int]
    discord_thread_id: Optional[str]
    result_summary: Optional[str]
    error_message: Optional[str]
    retry_count: int
    required_intervention: bool
    intervention_reason: Optional[str]
    tokens_used: Optional[Dict[str, int]]
    compute_time_seconds: Optional[int]
    pages_loaded: Optional[int]
    created_at: datetime


class TaskListResponse(BaseModel):
    """Paginated list of tasks."""

    tasks: List[TaskResponse]
    total: int
    limit: int
    offset: int


class TaskHistoryResponse(BaseModel):
    """Task run history."""

    task_name: str
    runs: List[TaskRunResponse]
    total: int
    limit: int
    offset: int


class TaskTemplateCreate(BaseModel):
    """Request body for creating a task template."""

    template_name: str = Field(..., min_length=1, max_length=255, pattern="^[a-z0-9-]+$")
    template_type: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = None
    template_prompt: str = Field(..., min_length=1)
    required_parameters: Optional[List[str]] = Field(default_factory=list)
    optional_parameters: Optional[Dict[str, Any]] = Field(default_factory=dict)
    default_config: Optional[TaskConfig] = Field(default_factory=TaskConfig)
    is_public: bool = Field(default=False)


class TaskTemplateResponse(BaseModel):
    """Response for task template operations."""

    id: str
    template_name: str
    template_type: str
    description: Optional[str]
    template_prompt: str
    required_parameters: Optional[List[str]]
    optional_parameters: Optional[Dict[str, Any]]
    default_config: Optional[Dict[str, Any]]
    author_user_id: str
    is_public: bool
    use_count: int
    rating_average: Optional[float]
    created_at: datetime
    version: int


class TaskDependencyCreate(BaseModel):
    """Request body for creating a task dependency."""

    depends_on_task_name: str = Field(..., description="Task name that must complete first")
    required: bool = Field(default=True, description="Must succeed (not just complete)")


class TaskDependencyResponse(BaseModel):
    """Response for task dependency."""

    id: str
    task_id: str
    task_name: str
    depends_on_task_id: str
    depends_on_task_name: str
    required: bool
    created_at: datetime


class TaskMetrics(BaseModel):
    """Task performance metrics."""

    task_name: str
    total_runs: int
    successful_runs: int
    failed_runs: int
    success_rate: float
    avg_duration_seconds: Optional[float]
    avg_tokens_used: Optional[int]
    avg_pages_loaded: Optional[float]
    total_compute_time_seconds: int
    last_run_at: Optional[datetime]
    next_run_at: Optional[datetime]


class TaskStatusInfo(BaseModel):
    """Detailed task status information."""

    task: TaskResponse
    current_runs: List[TaskRunResponse]
    next_scheduled_runs: List[datetime]
    dependencies: List[str]
    dependents: List[str]
    recent_history: List[TaskRunResponse]
    metrics: TaskMetrics
