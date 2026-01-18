"""Task service for managing automated tasks."""

import logging
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Task, TaskRun, DiscordChannel, ScheduleHistory
from app.models.task import TaskCreate, TaskUpdate, TaskSchedule, TaskStart

logger = logging.getLogger(__name__)


class TaskService:
    """Service for managing automated tasks."""

    def __init__(self, db: AsyncSession):
        """Initialize task service."""
        self.db = db

    async def create_task(self, task_data: TaskCreate) -> Task:
        """Create a new task."""
        # Validate task name uniqueness
        result = await self.db.execute(
            select(Task).where(Task.task_name == task_data.task_name)
        )
        existing = result.scalar_one_or_none()
        if existing:
            raise ValueError(f"Task with name '{task_data.task_name}' already exists")

        # Validate parameters in template
        self._validate_template_parameters(
            task_data.template_prompt,
            task_data.required_parameters or []
        )

        # Create task
        task = Task(
            id=str(uuid4()),
            task_name=task_data.task_name,
            task_type=task_data.task_type,
            description=task_data.description,
            template_prompt=task_data.template_prompt,
            required_parameters=task_data.required_parameters,
            optional_parameters=task_data.optional_parameters,
            schedule_cron=task_data.schedule_cron,
            schedule_timezone=task_data.schedule_timezone,
            config=task_data.config.model_dump(),
            owner_user_id=task_data.owner_user_id,
            created_by=task_data.owner_user_id,
        )

        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)

        logger.info(f"Created task: {task.task_name} (ID: {task.id})")
        return task

    async def get_task(self, task_id: Optional[str] = None, task_name: Optional[str] = None) -> Optional[Task]:
        """Get task by ID or name."""
        if task_id:
            result = await self.db.execute(
                select(Task).where(Task.id == task_id, Task.deleted_at.is_(None))
            )
        elif task_name:
            result = await self.db.execute(
                select(Task).where(Task.task_name == task_name, Task.deleted_at.is_(None))
            )
        else:
            raise ValueError("Must provide either task_id or task_name")

        return result.scalar_one_or_none()

    async def list_tasks(
        self,
        owner_user_id: Optional[str] = None,
        task_type: Optional[str] = None,
        enabled: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0
    ) -> tuple[List[Task], int]:
        """List tasks with filters."""
        query = select(Task).where(Task.deleted_at.is_(None))

        if owner_user_id:
            query = query.where(Task.owner_user_id == owner_user_id)
        if task_type:
            query = query.where(Task.task_type == task_type)
        if enabled is not None:
            query = query.where(Task.enabled == enabled)

        # Count total
        count_result = await self.db.execute(select(Task).where(Task.deleted_at.is_(None)))
        total = len(count_result.scalars().all())

        # Get page
        query = query.order_by(Task.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(query)
        tasks = result.scalars().all()

        return list(tasks), total

    async def update_task(self, task_id: str, task_data: TaskUpdate) -> Task:
        """Update a task."""
        task = await self.get_task(task_id=task_id)
        if not task:
            raise ValueError(f"Task with ID '{task_id}' not found")

        # Update fields
        if task_data.description is not None:
            task.description = task_data.description
        if task_data.template_prompt is not None:
            task.template_prompt = task_data.template_prompt
        if task_data.required_parameters is not None:
            task.required_parameters = task_data.required_parameters
        if task_data.optional_parameters is not None:
            task.optional_parameters = task_data.optional_parameters
        if task_data.config is not None:
            task.config = task_data.config.model_dump()
        if task_data.schedule_cron is not None:
            task.schedule_cron = task_data.schedule_cron
        if task_data.schedule_timezone is not None:
            task.schedule_timezone = task_data.schedule_timezone
        if task_data.enabled is not None:
            task.enabled = task_data.enabled
        if task_data.paused is not None:
            task.paused = task_data.paused
        if task_data.notify_on_complete is not None:
            task.notify_on_complete = task_data.notify_on_complete
        if task_data.notify_on_error is not None:
            task.notify_on_error = task_data.notify_on_error

        task.updated_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(task)

        logger.info(f"Updated task: {task.task_name}")
        return task

    async def delete_task(self, task_id: str, hard_delete: bool = False) -> bool:
        """Delete a task (soft or hard)."""
        task = await self.get_task(task_id=task_id)
        if not task:
            return False

        if hard_delete:
            await self.db.delete(task)
        else:
            task.deleted_at = datetime.now(timezone.utc)
            task.enabled = False

        await self.db.commit()
        logger.info(f"Deleted task: {task.task_name} (hard={hard_delete})")
        return True

    async def start_task(
        self,
        task_id: str,
        parameters: Dict[str, any],
        trigger: str = "manual",
        triggered_by_user_id: Optional[str] = None
    ) -> TaskRun:
        """Start a task execution."""
        task = await self.get_task(task_id=task_id)
        if not task:
            raise ValueError(f"Task with ID '{task_id}' not found")

        if not task.enabled:
            raise ValueError(f"Task '{task.task_name}' is disabled")

        if task.paused:
            raise ValueError(f"Task '{task.task_name}' is paused")

        # Validate parameters
        self._validate_task_parameters(task, parameters)

        # Fill in prompt template
        filled_prompt = self._fill_template(task.template_prompt, parameters)

        # Create task run
        task_run = TaskRun(
            id=str(uuid4()),
            task_id=task.id,
            status="starting",
            trigger=trigger,
            parameters=parameters,
            discord_channel_id=task.discord_channel_id,
            created_at=datetime.now(timezone.utc),
        )

        self.db.add(task_run)

        # Update task stats
        task.run_count += 1
        task.last_run_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(task_run)

        logger.info(f"Started task run: {task.task_name} (run_id={task_run.id})")
        return task_run, filled_prompt

    async def get_task_run(self, run_id: str) -> Optional[TaskRun]:
        """Get task run by ID."""
        result = await self.db.execute(
            select(TaskRun).where(TaskRun.id == run_id)
        )
        return result.scalar_one_or_none()

    async def update_task_run(
        self,
        run_id: str,
        status: Optional[str] = None,
        session_id: Optional[str] = None,
        discord_thread_id: Optional[str] = None,
        result_summary: Optional[str] = None,
        result_data: Optional[Dict] = None,
        error_message: Optional[str] = None,
        **kwargs
    ) -> TaskRun:
        """Update task run status and results."""
        task_run = await self.get_task_run(run_id)
        if not task_run:
            raise ValueError(f"Task run with ID '{run_id}' not found")

        if status:
            task_run.status = status
        if session_id:
            task_run.session_id = session_id
        if discord_thread_id:
            task_run.discord_thread_id = discord_thread_id
        if result_summary:
            task_run.result_summary = result_summary
        if result_data:
            task_run.result_data = result_data
        if error_message:
            task_run.error_message = error_message

        # Update any additional fields
        for key, value in kwargs.items():
            if hasattr(task_run, key):
                setattr(task_run, key, value)

        # Handle completion
        if status in ["completed", "failed", "cancelled"]:
            task_run.completed_at = datetime.now(timezone.utc)
            if task_run.started_at:
                duration = (task_run.completed_at - task_run.started_at).total_seconds()
                task_run.duration_seconds = int(duration)

            # Update task stats
            task = await self.get_task(task_id=task_run.task_id)
            if task:
                if status == "completed":
                    task.success_count += 1
                elif status == "failed":
                    task.failure_count += 1

                # Update average duration
                if task_run.duration_seconds:
                    if task.avg_duration_seconds:
                        task.avg_duration_seconds = int(
                            (task.avg_duration_seconds * (task.run_count - 1) + task_run.duration_seconds) / task.run_count
                        )
                    else:
                        task.avg_duration_seconds = task_run.duration_seconds

        task_run.updated_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(task_run)

        return task_run

    async def list_task_runs(
        self,
        task_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> tuple[List[TaskRun], int]:
        """List task runs with filters."""
        query = select(TaskRun)

        if task_id:
            query = query.where(TaskRun.task_id == task_id)
        if status:
            query = query.where(TaskRun.status == status)

        # Count total
        count_result = await self.db.execute(query)
        total = len(count_result.scalars().all())

        # Get page
        query = query.order_by(TaskRun.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(query)
        runs = result.scalars().all()

        return list(runs), total

    def _validate_template_parameters(self, template: str, required_params: List[str]):
        """Validate that all required parameters exist in template."""
        # Find all {parameter} placeholders
        placeholders = set(re.findall(r'\{(\w+)\}', template))

        # Check that all required params are in template
        for param in required_params:
            if param not in placeholders:
                raise ValueError(
                    f"Required parameter '{param}' not found in template"
                )

    def _validate_task_parameters(self, task: Task, parameters: Dict[str, any]):
        """Validate provided parameters against task requirements."""
        required = task.required_parameters or []
        optional = task.optional_parameters or {}

        # Check all required parameters are provided
        missing = [p for p in required if p not in parameters]
        if missing:
            raise ValueError(
                f"Missing required parameters: {', '.join(missing)}"
            )

        # Fill in optional parameters with defaults
        for param, default_value in optional.items():
            if param not in parameters:
                parameters[param] = default_value

    def _fill_template(self, template: str, parameters: Dict[str, any]) -> str:
        """Fill template placeholders with parameter values."""
        filled = template
        for key, value in parameters.items():
            placeholder = f"{{{key}}}"
            filled = filled.replace(placeholder, str(value))

        # Check for unfilled placeholders
        remaining = re.findall(r'\{(\w+)\}', filled)
        if remaining:
            raise ValueError(
                f"Template has unfilled placeholders: {', '.join(remaining)}"
            )

        return filled
