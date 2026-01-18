"""Scheduler service for managing scheduled tasks."""

import logging
from datetime import datetime, timezone
from typing import Dict, Optional
from croniter import croniter
import pytz

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.memory import MemoryJobStore
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Task, ScheduleHistory
from app.services.task import TaskService

logger = logging.getLogger(__name__)


class SchedulerService:
    """Service for managing task schedules with APScheduler."""

    def __init__(self):
        """Initialize scheduler service."""
        self.scheduler = AsyncIOScheduler(
            jobstores={"default": MemoryJobStore()},
            job_defaults={
                "coalesce": True,  # Combine missed runs
                "max_instances": 1,  # Only one instance per task
                "misfire_grace_time": 300,  # 5 minutes grace period
            }
        )
        self._initialized = False

    async def start(self):
        """Start the scheduler."""
        if not self._initialized:
            self.scheduler.start()
            self._initialized = True
            logger.info("APScheduler started")

    async def shutdown(self):
        """Shutdown the scheduler."""
        if self._initialized:
            self.scheduler.shutdown(wait=True)
            self._initialized = False
            logger.info("APScheduler shutdown")

    async def add_task_schedule(
        self,
        task: Task,
        db: AsyncSession
    ) -> Optional[str]:
        """Add or update a task schedule."""
        if not task.schedule_cron:
            logger.warning(f"Task {task.task_name} has no cron schedule")
            return None

        # Validate cron expression
        if not self.validate_cron(task.schedule_cron):
            raise ValueError(f"Invalid cron expression: {task.schedule_cron}")

        # Remove existing job if any
        job_id = f"task_{task.id}"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)

        # Create cron trigger
        try:
            tz = pytz.timezone(task.schedule_timezone)
            trigger = CronTrigger.from_crontab(task.schedule_cron, timezone=tz)
        except Exception as e:
            logger.error(f"Failed to create cron trigger: {e}")
            raise ValueError(f"Invalid cron or timezone: {e}")

        # Add job
        job = self.scheduler.add_job(
            self._execute_scheduled_task,
            trigger=trigger,
            id=job_id,
            name=f"Task: {task.task_name}",
            kwargs={"task_id": task.id},
            replace_existing=True,
        )

        # Calculate next run time
        next_run = job.next_run_time
        if next_run:
            task.next_run_at = next_run

        # Log schedule history
        await self._log_schedule_change(
            db,
            task.id,
            "schedule_created",
            None,
            task.schedule_cron,
            "scheduler",
            None
        )

        logger.info(
            f"Scheduled task {task.task_name}: {task.schedule_cron} "
            f"(next run: {next_run})"
        )

        return job_id

    async def remove_task_schedule(
        self,
        task: Task,
        db: AsyncSession,
        triggered_by: str = "api",
        user_id: Optional[str] = None
    ):
        """Remove a task schedule."""
        job_id = f"task_{task.id}"

        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)

            # Log schedule history
            await self._log_schedule_change(
                db,
                task.id,
                "schedule_removed",
                task.schedule_cron,
                None,
                triggered_by,
                user_id
            )

            logger.info(f"Removed schedule for task {task.task_name}")

    async def pause_task_schedule(self, task: Task):
        """Pause a task schedule."""
        job_id = f"task_{task.id}"
        job = self.scheduler.get_job(job_id)

        if job:
            job.pause()
            logger.info(f"Paused schedule for task {task.task_name}")

    async def resume_task_schedule(self, task: Task):
        """Resume a task schedule."""
        job_id = f"task_{task.id}"
        job = self.scheduler.get_job(job_id)

        if job:
            job.resume()
            logger.info(f"Resumed schedule for task {task.task_name}")

    async def get_next_run_times(
        self,
        cron_expression: str,
        timezone_str: str = "UTC",
        count: int = 5
    ) -> list[datetime]:
        """Get next N run times for a cron expression."""
        try:
            tz = pytz.timezone(timezone_str)
            base_time = datetime.now(tz)
            cron = croniter(cron_expression, base_time)

            run_times = []
            for _ in range(count):
                next_time = cron.get_next(datetime)
                run_times.append(next_time)

            return run_times
        except Exception as e:
            logger.error(f"Failed to calculate next run times: {e}")
            return []

    def validate_cron(self, cron_expression: str) -> bool:
        """Validate a cron expression."""
        try:
            croniter(cron_expression)
            return True
        except Exception:
            return False

    async def _execute_scheduled_task(self, task_id: str):
        """Execute a scheduled task (called by APScheduler)."""
        logger.info(f"Executing scheduled task: {task_id}")

        # Import here to avoid circular dependency
        from app.db.database import get_db
        from app.services.task import TaskService

        async for db in get_db():
            try:
                task_service = TaskService(db)
                task = await task_service.get_task(task_id=task_id)

                if not task:
                    logger.error(f"Task {task_id} not found")
                    return

                if not task.enabled or task.paused:
                    logger.warning(
                        f"Task {task.task_name} is disabled or paused, skipping"
                    )
                    return

                # Get default parameters from task config
                parameters = task.optional_parameters or {}

                # Start the task
                task_run, filled_prompt = await task_service.start_task(
                    task_id=task_id,
                    parameters=parameters,
                    trigger="scheduled"
                )

                logger.info(
                    f"Scheduled task run created: {task.task_name} "
                    f"(run_id={task_run.id})"
                )

                # TODO: Integrate with session creation to actually execute the task
                # For now, just log that we would create a session

            except Exception as e:
                logger.error(f"Failed to execute scheduled task {task_id}: {e}")
            finally:
                break  # Only use first db session

    async def _log_schedule_change(
        self,
        db: AsyncSession,
        task_id: str,
        action: str,
        schedule_before: Optional[str],
        schedule_after: Optional[str],
        triggered_by: str,
        user_id: Optional[str]
    ):
        """Log a schedule change to history."""
        from uuid import uuid4

        history = ScheduleHistory(
            id=str(uuid4()),
            task_id=task_id,
            action=action,
            schedule_before=schedule_before,
            schedule_after=schedule_after,
            triggered_by=triggered_by,
            user_id=user_id,
            timestamp=datetime.now(timezone.utc),
        )

        db.add(history)
        await db.commit()

    async def reload_all_schedules(self, db: AsyncSession):
        """Reload all task schedules from database."""
        from sqlalchemy import select
        from app.db.models import Task

        logger.info("Reloading all task schedules...")

        result = await db.execute(
            select(Task).where(
                Task.enabled == True,
                Task.paused == False,
                Task.deleted_at.is_(None),
                Task.schedule_cron.isnot(None)
            )
        )
        tasks = result.scalars().all()

        count = 0
        for task in tasks:
            try:
                await self.add_task_schedule(task, db)
                count += 1
            except Exception as e:
                logger.error(f"Failed to reload schedule for {task.task_name}: {e}")

        logger.info(f"Reloaded {count} task schedules")
