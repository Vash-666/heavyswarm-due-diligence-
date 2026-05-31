"""Background task processing for diligence workflows."""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set
from datetime import datetime
from enum import Enum
import traceback

from heavyswarm.core.enums import AgentPhase, DiligenceStatus
from heavyswarm.core.state import DiligenceState, InvestmentThesis
from heavyswarm.services.database import DatabaseService
from heavyswarm.utils.logger import get_logger

logger = get_logger(__name__)


class TaskStatus(Enum):
    """Background task status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskInfo:
    """Information about a background task."""
    task_id: str
    diligence_id: str
    status: TaskStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    current_phase: Optional[str] = None
    progress_percent: float = 0.0
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None


class BackgroundTaskManager:
    """Manages background execution of diligence workflows.
    
    Handles the 6-phase workflow execution in the background,
    tracking progress and updating the database in real-time.
    """
    
    # Phase weights for progress calculation
    PHASE_WEIGHTS = {
        AgentPhase.QUESTION_GENERATOR: 0.10,
        AgentPhase.RESEARCHER: 0.25,
        AgentPhase.FINANCIAL_ANALYST: 0.15,
        AgentPhase.RISK_ANALYST: 0.15,
        AgentPhase.STRATEGIST: 0.15,
        AgentPhase.VERIFIER: 0.10,
        AgentPhase.WRITER: 0.10,
        AgentPhase.QUALITY_GUARDIAN: 0.05,
    }
    
    def __init__(
        self,
        db_service: DatabaseService,
        orchestrator_factory: Callable,
        max_concurrent: int = 10,
    ):
        """Initialize background task manager.
        
        Args:
            db_service: Database service for persistence
            orchestrator_factory: Factory function to create orchestrator
            max_concurrent: Maximum concurrent workflows
        """
        self.db = db_service
        self.orchestrator_factory = orchestrator_factory
        self.max_concurrent = max_concurrent
        
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._tasks: Dict[str, asyncio.Task] = {}
        self._task_info: Dict[str, TaskInfo] = {}
        self._shutdown_event = asyncio.Event()
    
    async def start_diligence(
        self,
        diligence_id: str,
        thesis: InvestmentThesis,
    ) -> TaskInfo:
        """Start a diligence workflow in the background.
        
        Args:
            diligence_id: Diligence ID
            thesis: Investment thesis
            
        Returns:
            Task information
        """
        task_info = TaskInfo(
            task_id=diligence_id,
            diligence_id=diligence_id,
            status=TaskStatus.PENDING,
            created_at=datetime.utcnow(),
        )
        self._task_info[diligence_id] = task_info
        
        # Create and start background task
        task = asyncio.create_task(
            self._run_diligence_workflow(diligence_id, thesis, task_info),
            name=f"diligence-{diligence_id}",
        )
        self._tasks[diligence_id] = task
        
        # Add completion callback
        task.add_done_callback(
            lambda t, did=diligence_id: self._on_task_complete(did, t)
        )
        
        logger.info(
            "Started diligence workflow",
            extra={
                "diligence_id": diligence_id,
                "ticker": thesis.ticker if thesis else None,
            },
        )
        
        return task_info
    
    async def _run_diligence_workflow(
        self,
        diligence_id: str,
        thesis: InvestmentThesis,
        task_info: TaskInfo,
    ) -> None:
        """Execute the full diligence workflow.
        
        Args:
            diligence_id: Diligence ID
            thesis: Investment thesis
            task_info: Task information to update
        """
        async with self._semaphore:
            if self._shutdown_event.is_set():
                task_info.status = TaskStatus.CANCELLED
                return
            
            task_info.status = TaskStatus.RUNNING
            task_info.started_at = datetime.utcnow()
            
            try:
                # Create orchestrator
                orchestrator = self.orchestrator_factory()
                
                # Run the workflow
                final_state = await orchestrator.run_diligence(
                    thesis=thesis,
                    diligence_id=diligence_id,
                )
                
                # Update task info
                task_info.status = TaskStatus.COMPLETED
                task_info.completed_at = datetime.utcnow()
                task_info.progress_percent = 100.0
                task_info.result = {
                    "status": final_state.status.value,
                    "confidence": final_state.overall_confidence,
                    "completed_phases": [p.name for p in final_state.completed_phases],
                }
                
                logger.info(
                    "Diligence workflow completed",
                    extra={
                        "diligence_id": diligence_id,
                        "duration_seconds": (task_info.completed_at - task_info.started_at).total_seconds(),
                        "confidence": final_state.overall_confidence,
                    },
                )
                
            except asyncio.CancelledError:
                task_info.status = TaskStatus.CANCELLED
                logger.info(
                    "Diligence workflow cancelled",
                    extra={"diligence_id": diligence_id},
                )
                raise
                
            except Exception as e:
                task_info.status = TaskStatus.FAILED
                task_info.error = str(e)
                task_info.completed_at = datetime.utcnow()
                
                logger.error(
                    "Diligence workflow failed",
                    extra={
                        "diligence_id": diligence_id,
                        "error": str(e),
                        "traceback": traceback.format_exc(),
                    },
                )
                
                # Update database with failure status
                try:
                    await self.db.update_diligence_status(
                        diligence_id=diligence_id,
                        status=DiligenceStatus.FAILED.value,
                        progress={"error": str(e)},
                    )
                except Exception as db_error:
                    logger.error(
                        "Failed to update database with failure status",
                        extra={
                            "diligence_id": diligence_id,
                            "error": str(db_error),
                        },
                    )
    
    def _on_task_complete(self, diligence_id: str, task: asyncio.Task) -> None:
        """Handle task completion.
        
        Args:
            diligence_id: Diligence ID
            task: Completed task
        """
        # Clean up task tracking
        if diligence_id in self._tasks:
            del self._tasks[diligence_id]
        
        # Check for exceptions
        try:
            task.result()
        except asyncio.CancelledError:
            logger.info(
                "Task was cancelled",
                extra={"diligence_id": diligence_id},
            )
        except Exception as e:
            logger.error(
                "Task failed with exception",
                extra={
                    "diligence_id": diligence_id,
                    "error": str(e),
                },
            )
    
    async def cancel_diligence(self, diligence_id: str) -> bool:
        """Cancel a running diligence.
        
        Args:
            diligence_id: Diligence ID
            
        Returns:
            True if cancelled, False if not found
        """
        if diligence_id not in self._tasks:
            return False
        
        task = self._tasks[diligence_id]
        task.cancel()
        
        try:
            await task
        except asyncio.CancelledError:
            pass
        
        # Update task info
        if diligence_id in self._task_info:
            self._task_info[diligence_id].status = TaskStatus.CANCELLED
        
        # Update database
        try:
            await self.db.update_diligence_status(
                diligence_id=diligence_id,
                status=DiligenceStatus.CANCELLED.value,
            )
        except Exception as e:
            logger.error(
                "Failed to update database with cancelled status",
                extra={
                    "diligence_id": diligence_id,
                    "error": str(e),
                },
            )
        
        logger.info(
            "Diligence cancelled",
            extra={"diligence_id": diligence_id},
        )
        
        return True
    
    def get_task_info(self, diligence_id: str) -> Optional[TaskInfo]:
        """Get task information.
        
        Args:
            diligence_id: Diligence ID
            
        Returns:
            Task info or None
        """
        return self._task_info.get(diligence_id)
    
    def get_all_tasks(
        self,
        status: Optional[TaskStatus] = None,
    ) -> List[TaskInfo]:
        """Get all tasks, optionally filtered by status.
        
        Args:
            status: Filter by status
            
        Returns:
            List of task info
        """
        tasks = list(self._task_info.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        return tasks
    
    def get_running_count(self) -> int:
        """Get count of running tasks.
        
        Returns:
            Number of running tasks
        """
        return sum(
            1 for t in self._task_info.values()
            if t.status == TaskStatus.RUNNING
        )
    
    async def shutdown(self, wait: bool = True, timeout: float = 30.0) -> None:
        """Shutdown the task manager.
        
        Args:
            wait: Whether to wait for running tasks
            timeout: Timeout for waiting
        """
        self._shutdown_event.set()
        
        if wait and self._tasks:
            logger.info(
                "Waiting for tasks to complete",
                extra={"task_count": len(self._tasks)},
            )
            
            # Cancel all running tasks
            for task in self._tasks.values():
                task.cancel()
            
            # Wait for completion with timeout
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._tasks.values(), return_exceptions=True),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "Timeout waiting for tasks to complete",
                    extra={"timeout": timeout},
                )
        
        logger.info("Background task manager shutdown complete")
    
    def calculate_progress(self, completed_phases: List[AgentPhase]) -> float:
        """Calculate progress percentage based on completed phases.
        
        Args:
            completed_phases: List of completed phases
            
        Returns:
            Progress percentage (0-100)
        """
        total_weight = sum(self.PHASE_WEIGHTS.values())
        completed_weight = sum(
            self.PHASE_WEIGHTS.get(phase, 0)
            for phase in completed_phases
        )
        return (completed_weight / total_weight) * 100 if total_weight > 0 else 0


# Global task manager instance (initialized on startup)
_task_manager: Optional[BackgroundTaskManager] = None


def get_task_manager() -> Optional[BackgroundTaskManager]:
    """Get the global task manager instance.
    
    Returns:
        Task manager or None if not initialized
    """
    return _task_manager


def set_task_manager(manager: BackgroundTaskManager) -> None:
    """Set the global task manager instance.
    
    Args:
        manager: Task manager instance
    """
    global _task_manager
    _task_manager = manager
