"""Task state tracking for plugin tasks.

Tracks the lifecycle of tasks initiated by plugins:
PENDING → IN_PROGRESS → COMPLETED/FAILED

Thread-safe for concurrent access from multiple plugins.
"""

import threading
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class TaskState(Enum):
    """Possible states for a plugin task."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


# Valid state transitions
_VALID_TRANSITIONS = {
    TaskState.PENDING: {TaskState.IN_PROGRESS, TaskState.FAILED},
    TaskState.IN_PROGRESS: {TaskState.COMPLETED, TaskState.FAILED},
    TaskState.COMPLETED: set(),  # Terminal state
    TaskState.FAILED: set(),  # Terminal state
}


class TaskTracker:
    """Tracks the state of plugin tasks.

    Thread-safe: all operations are locked.

    Example:
        tracker = TaskTracker()
        tracker.start_task("task-1", "my-plugin", "refresh")
        tracker.update_task("task-1", TaskState.IN_PROGRESS)
        tracker.update_task("task-1", TaskState.COMPLETED, result={"status": "ok"})
    """

    def __init__(self):
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def start_task(
        self, task_id: str, plugin_name: str, task_type: str
    ) -> Dict[str, Any]:
        """Start a new task.

        Args:
            task_id: Unique task identifier
            plugin_name: Name of the plugin that owns this task
            task_type: Type of task (e.g., "refresh", "export", "validate")

        Returns:
            The created task dict

        Raises:
            ValueError: If task_id already exists
        """
        now = datetime.now(timezone.utc)
        with self._lock:
            if task_id in self._tasks:
                raise ValueError(f"Task {task_id} already exists")

            task = {
                "id": task_id,
                "plugin_name": plugin_name,
                "task_type": task_type,
                "state": TaskState.PENDING,
                "created_at": now,
                "updated_at": now,
                "result": None,
            }
            self._tasks[task_id] = task
            return dict(task)

    def update_task(
        self,
        task_id: str,
        state: TaskState,
        result: Any = None,
    ) -> Dict[str, Any]:
        """Update a task's state.

        Args:
            task_id: The task to update
            state: The new state
            result: Optional result data (for COMPLETED/FAILED)

        Returns:
            The updated task dict

        Raises:
            KeyError: If task_id doesn't exist
            ValueError: If the state transition is invalid
        """
        with self._lock:
            if task_id not in self._tasks:
                raise KeyError(f"Task {task_id} not found")

            task = self._tasks[task_id]
            current_state = task["state"]

            # Validate transition
            if state not in _VALID_TRANSITIONS.get(current_state, set()):
                raise ValueError(
                    f"Invalid transition: {current_state.value} → {state.value}"
                )

            task["state"] = state
            task["updated_at"] = datetime.now(timezone.utc)
            if result is not None:
                task["result"] = result

            return dict(task)

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get a task by ID.

        Args:
            task_id: The task ID

        Returns:
            Task dict, or None if not found
        """
        with self._lock:
            task = self._tasks.get(task_id)
            return dict(task) if task else None

    def list_tasks(
        self, plugin_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List tasks, optionally filtered by plugin name.

        Args:
            plugin_name: If provided, only return tasks from this plugin

        Returns:
            List of task dicts (newest first)
        """
        with self._lock:
            tasks = list(self._tasks.values())
            if plugin_name:
                tasks = [t for t in tasks if t["plugin_name"] == plugin_name]
            # Sort by created_at descending (newest first)
            tasks.sort(key=lambda t: t["created_at"], reverse=True)
            return [dict(t) for t in tasks]

    def abandon_task(self, task_id: str) -> Dict[str, Any]:
        """Abandon a task (mark as FAILED).

        Args:
            task_id: The task to abandon

        Returns:
            The updated task dict

        Raises:
            KeyError: If task_id doesn't exist
            ValueError: If the task is already in a terminal state
        """
        return self.update_task(task_id, TaskState.FAILED, result="abandoned")

    def is_task_active(self, task_id: str) -> bool:
        """Check if a task is active (PENDING or IN_PROGRESS).

        Args:
            task_id: The task ID

        Returns:
            True if active, False otherwise (including if not found)
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            return task["state"] in (TaskState.PENDING, TaskState.IN_PROGRESS)

    def cleanup_completed(self, max_age_hours: int = 24) -> int:
        """Remove completed/failed tasks older than max_age_hours.

        Args:
            max_age_hours: Maximum age in hours for completed tasks

        Returns:
            Number of tasks removed
        """
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        removed = 0

        with self._lock:
            to_remove = []
            for task_id, task in self._tasks.items():
                if task["state"] in (TaskState.COMPLETED, TaskState.FAILED):
                    if task["updated_at"] < cutoff:
                        to_remove.append(task_id)

            for task_id in to_remove:
                del self._tasks[task_id]
                removed += 1

        return removed
