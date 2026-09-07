"""
Thread-safe job manager for tracking grading operations.
"""

import threading
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Job:
    def __init__(self, job_id: str, filename: str, pages: int = 0):
        self.job_id = job_id
        self.filename = filename
        self.pages = pages
        self.status = JobStatus.PENDING
        self.progress = 0.0
        self.current_page = 0
        self.total_pages = pages
        self.result = None
        self.error = None
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.updated_at = self.created_at
        self.completed_at = None

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "filename": self.filename,
            "pages": self.pages,
            "status": self.status.value,
            "progress": self.progress,
            "current_page": self.current_page,
            "total_pages": self.total_pages,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
        }


class JobManager:
    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create_job(self, filename: str, pages: int = 0) -> str:
        """Create a new job and return its ID."""
        job_id = str(uuid.uuid4())
        with self._lock:
            self._jobs[job_id] = Job(job_id, filename, pages)
        return job_id

    def update_progress(self, job_id: str, progress: float, current_page: int = 0) -> None:
        """Update job progress (0.0 to 1.0)."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.progress = min(1.0, max(0.0, progress))
                job.current_page = current_page
                job.status = JobStatus.PROCESSING
                job.updated_at = datetime.now(timezone.utc).isoformat()

    def complete_job(self, job_id: str, result: dict) -> None:
        """Mark job as completed with result."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.status = JobStatus.COMPLETED
                job.progress = 1.0
                job.result = result
                job.completed_at = datetime.now(timezone.utc).isoformat()
                job.updated_at = job.completed_at

    def fail_job(self, job_id: str, error: str) -> None:
        """Mark job as failed with error message."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.status = JobStatus.FAILED
                job.error = error
                job.updated_at = datetime.now(timezone.utc).isoformat()
                job.completed_at = job.updated_at

    def get_job(self, job_id: str) -> Optional[dict]:
        """Get job status and details."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                return job.to_dict()
        return None

    def list_jobs(self, limit: int = 50) -> list[dict]:
        """List recent jobs."""
        with self._lock:
            jobs = sorted(
                self._jobs.values(),
                key=lambda j: j.created_at,
                reverse=True,
            )
            return [j.to_dict() for j in jobs[:limit]]

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending or processing job."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job and job.status in (JobStatus.PENDING, JobStatus.PROCESSING):
                job.status = JobStatus.FAILED
                job.error = "Cancelled by user"
                job.updated_at = datetime.now(timezone.utc).isoformat()
                return True
        return False


# Global singleton
job_manager = JobManager()
