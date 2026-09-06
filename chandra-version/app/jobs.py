"""Asynchronous in-memory background job manager for real-time exam grading."""
import threading
import time
import uuid
from typing import Any, Dict, Optional


class JobManager:
    """Thread-safe background job registry."""

    def __init__(self):
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create_job(self) -> str:
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        now = time.time()
        with self._lock:
            self._jobs[job_id] = {
                "job_id": job_id,
                "status": "pending",
                "progress": 0,
                "stage": "Queued",
                "created_at": now,
                "updated_at": now,
                "result": None,
                "error": None,
            }
        return job_id

    def update_progress(self, job_id: str, progress: int, stage: str):
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]["progress"] = max(0, min(100, progress))
                self._jobs[job_id]["stage"] = stage
                self._jobs[job_id]["status"] = "processing"
                self._jobs[job_id]["updated_at"] = time.time()

    def complete_job(self, job_id: str, result: Any):
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]["status"] = "completed"
                self._jobs[job_id]["progress"] = 100
                self._jobs[job_id]["stage"] = "Completed"
                self._jobs[job_id]["result"] = result
                self._jobs[job_id]["updated_at"] = time.time()

    def fail_job(self, job_id: str, error_msg: str):
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]["status"] = "failed"
                self._jobs[job_id]["error"] = error_msg
                self._jobs[job_id]["stage"] = "Failed"
                self._jobs[job_id]["updated_at"] = time.time()

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None


# Global singleton job manager
job_manager = JobManager()
