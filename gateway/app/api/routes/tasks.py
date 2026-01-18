"""Task management API routes."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.security import User
from app.db.database import get_db
from app.models.task import (
    TaskCreate,
    TaskUpdate,
    TaskSchedule,
    TaskStart,
    TaskResponse,
    TaskRunResponse,
    TaskListResponse,
    TaskHistoryResponse,
    TaskStatus,
)
from app.services.task import TaskService
from app.services.scheduler import SchedulerService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    task_data: TaskCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a new automated task."""
    try:
        task_service = TaskService(db)
        task = await task_service.create_task(task_data)

        return TaskResponse(
            id=task.id,
            task_name=task.task_name,
            task_type=task.task_type,
            description=task.description,
            template_prompt=task.template_prompt,
            required_parameters=task.required_parameters,
            optional_parameters=task.optional_parameters,
            schedule_cron=task.schedule_cron,
            schedule_timezone=task.schedule_timezone,
            enabled=bool(task.enabled),
            paused=bool(task.paused),
            next_run_at=task.next_run_at,
            last_run_at=task.last_run_at,
            discord_channel_id=task.discord_channel_id,
            discord_category_id=task.discord_category_id,
            owner_user_id=task.owner_user_id,
            run_count=task.run_count,
            success_count=task.success_count,
            failure_count=task.failure_count,
            avg_duration_seconds=task.avg_duration_seconds,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create task: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create task"
        )


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get task by ID."""
    task_service = TaskService(db)
    task = await task_service.get_task(task_id=task_id)

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found"
        )

    return TaskResponse(
        id=task.id,
        task_name=task.task_name,
        task_type=task.task_type,
        description=task.description,
        template_prompt=task.template_prompt,
        required_parameters=task.required_parameters,
        optional_parameters=task.optional_parameters,
        schedule_cron=task.schedule_cron,
        schedule_timezone=task.schedule_timezone,
        enabled=bool(task.enabled),
        paused=bool(task.paused),
        next_run_at=task.next_run_at,
        last_run_at=task.last_run_at,
        discord_channel_id=task.discord_channel_id,
        discord_category_id=task.discord_category_id,
        owner_user_id=task.owner_user_id,
        run_count=task.run_count,
        success_count=task.success_count,
        failure_count=task.failure_count,
        avg_duration_seconds=task.avg_duration_seconds,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


@router.get("/", response_model=TaskListResponse)
async def list_tasks(
    task_type: Optional[str] = Query(None),
    enabled: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List tasks with filters."""
    task_service = TaskService(db)
    tasks, total = await task_service.list_tasks(
        owner_user_id=user.user_id,
        task_type=task_type,
        enabled=enabled,
        limit=limit,
        offset=offset,
    )

    task_responses = [
        TaskResponse(
            id=t.id,
            task_name=t.task_name,
            task_type=t.task_type,
            description=t.description,
            template_prompt=t.template_prompt,
            required_parameters=t.required_parameters,
            optional_parameters=t.optional_parameters,
            schedule_cron=t.schedule_cron,
            schedule_timezone=t.schedule_timezone,
            enabled=bool(t.enabled),
            paused=bool(t.paused),
            next_run_at=t.next_run_at,
            last_run_at=t.last_run_at,
            discord_channel_id=t.discord_channel_id,
            discord_category_id=t.discord_category_id,
            owner_user_id=t.owner_user_id,
            run_count=t.run_count,
            success_count=t.success_count,
            failure_count=t.failure_count,
            avg_duration_seconds=t.avg_duration_seconds,
            created_at=t.created_at,
            updated_at=t.updated_at,
        )
        for t in tasks
    ]

    return TaskListResponse(
        tasks=task_responses,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: str,
    task_data: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update a task."""
    try:
        task_service = TaskService(db)
        task = await task_service.update_task(task_id, task_data)

        return TaskResponse(
            id=task.id,
            task_name=task.task_name,
            task_type=task.task_type,
            description=task.description,
            template_prompt=task.template_prompt,
            required_parameters=task.required_parameters,
            optional_parameters=task.optional_parameters,
            schedule_cron=task.schedule_cron,
            schedule_timezone=task.schedule_timezone,
            enabled=bool(task.enabled),
            paused=bool(task.paused),
            next_run_at=task.next_run_at,
            last_run_at=task.last_run_at,
            discord_channel_id=task.discord_channel_id,
            discord_category_id=task.discord_category_id,
            owner_user_id=task.owner_user_id,
            run_count=task.run_count,
            success_count=task.success_count,
            failure_count=task.failure_count,
            avg_duration_seconds=task.avg_duration_seconds,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: str,
    hard: bool = Query(False, description="Hard delete (cannot be undone)"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete a task (soft delete by default)."""
    task_service = TaskService(db)
    success = await task_service.delete_task(task_id, hard_delete=hard)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found"
        )


@router.post("/{task_id}/start", response_model=TaskRunResponse)
async def start_task(
    task_id: str,
    start_data: TaskStart,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Start a task execution."""
    try:
        task_service = TaskService(db)
        task_run, filled_prompt = await task_service.start_task(
            task_id=task_id,
            parameters=start_data.parameters,
            trigger="manual",
            triggered_by_user_id=user.user_id,
        )

        # TODO: Actually create session and execute task
        # For now just return the task run

        return TaskRunResponse(
            id=task_run.id,
            task_id=task_run.task_id,
            task_name="",  # TODO: fetch task name
            session_id=task_run.session_id,
            status=TaskStatus(task_run.status),
            trigger=task_run.trigger,
            parameters=task_run.parameters,
            started_at=task_run.started_at,
            completed_at=task_run.completed_at,
            duration_seconds=task_run.duration_seconds,
            discord_thread_id=task_run.discord_thread_id,
            result_summary=task_run.result_summary,
            error_message=task_run.error_message,
            retry_count=task_run.retry_count,
            required_intervention=bool(task_run.required_intervention),
            intervention_reason=task_run.intervention_reason,
            tokens_used=task_run.tokens_used,
            compute_time_seconds=task_run.compute_time_seconds,
            pages_loaded=task_run.pages_loaded,
            created_at=task_run.created_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{task_id}/schedule", response_model=TaskResponse)
async def schedule_task(
    task_id: str,
    schedule_data: TaskSchedule,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Set or update task schedule."""
    try:
        task_service = TaskService(db)
        task = await task_service.get_task(task_id=task_id)

        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task {task_id} not found"
            )

        # Update schedule
        update_data = TaskUpdate(
            schedule_cron=schedule_data.schedule_cron,
            schedule_timezone=schedule_data.schedule_timezone,
        )
        task = await task_service.update_task(task_id, update_data)

        # Add to scheduler
        scheduler = SchedulerService()
        await scheduler.add_task_schedule(task, db)

        return TaskResponse(
            id=task.id,
            task_name=task.task_name,
            task_type=task.task_type,
            description=task.description,
            template_prompt=task.template_prompt,
            required_parameters=task.required_parameters,
            optional_parameters=task.optional_parameters,
            schedule_cron=task.schedule_cron,
            schedule_timezone=task.schedule_timezone,
            enabled=bool(task.enabled),
            paused=bool(task.paused),
            next_run_at=task.next_run_at,
            last_run_at=task.last_run_at,
            discord_channel_id=task.discord_channel_id,
            discord_category_id=task.discord_category_id,
            owner_user_id=task.owner_user_id,
            run_count=task.run_count,
            success_count=task.success_count,
            failure_count=task.failure_count,
            avg_duration_seconds=task.avg_duration_seconds,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{task_id}/history", response_model=TaskHistoryResponse)
async def get_task_history(
    task_id: str,
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get task execution history."""
    task_service = TaskService(db)
    task = await task_service.get_task(task_id=task_id)

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found"
        )

    runs, total = await task_service.list_task_runs(
        task_id=task_id,
        limit=limit,
        offset=offset,
    )

    run_responses = [
        TaskRunResponse(
            id=r.id,
            task_id=r.task_id,
            task_name=task.task_name,
            session_id=r.session_id,
            status=TaskStatus(r.status),
            trigger=r.trigger,
            parameters=r.parameters,
            started_at=r.started_at,
            completed_at=r.completed_at,
            duration_seconds=r.duration_seconds,
            discord_thread_id=r.discord_thread_id,
            result_summary=r.result_summary,
            error_message=r.error_message,
            retry_count=r.retry_count,
            required_intervention=bool(r.required_intervention),
            intervention_reason=r.intervention_reason,
            tokens_used=r.tokens_used,
            compute_time_seconds=r.compute_time_seconds,
            pages_loaded=r.pages_loaded,
            created_at=r.created_at,
        )
        for r in runs
    ]

    return TaskHistoryResponse(
        task_name=task.task_name,
        runs=run_responses,
        total=total,
        limit=limit,
        offset=offset,
    )
