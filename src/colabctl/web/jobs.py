"""Lightweight thread-safe background job tracker for long-running Colab operations."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

JobState = Literal["running", "succeeded", "failed"]


class JobRecord(BaseModel):
    id: str
    kind: str
    target: str
    title: str
    status: JobState = "running"
    started_at: str
    finished_at: str | None = None
    message: str = ""
    error: str | None = None
    result: dict[str, Any] | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class JobManager:
    """Runs blocking controller operations in daemon threads and tracks their state."""

    def __init__(self, max_history: int = 40) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, JobRecord] = {}
        self._order: list[str] = []
        self._max_history = max_history

    def submit(
        self,
        *,
        kind: str,
        target: str,
        title: str,
        fn: Callable[[], dict[str, Any] | None],
        meta: dict[str, Any] | None = None,
    ) -> JobRecord:
        job_id = uuid.uuid4().hex[:10]
        rec = JobRecord(
            id=job_id,
            kind=kind,
            target=target,
            title=title,
            status="running",
            started_at=datetime.now(UTC).isoformat(),
            message=f"{title}...",
            meta=dict(meta or {}),
        )
        with self._lock:
            self._jobs[job_id] = rec
            self._order.append(job_id)
            while len(self._order) > self._max_history:
                old = self._order.pop(0)
                if self._jobs.get(old) and self._jobs[old].status != "running":
                    self._jobs.pop(old, None)

        def runner() -> None:
            try:
                payload = fn()
                with self._lock:
                    cur = self._jobs[job_id]
                    cur.status = "succeeded"
                    cur.finished_at = datetime.now(UTC).isoformat()
                    cur.result = payload
                    cur.message = f"{title} completed."
            except Exception as exc:
                with self._lock:
                    cur = self._jobs[job_id]
                    cur.status = "failed"
                    cur.finished_at = datetime.now(UTC).isoformat()
                    cur.error = str(exc)
                    cur.message = str(exc)

        thread = threading.Thread(target=runner, name=f"colabctl-job-{job_id}", daemon=True)
        thread.start()
        return rec.model_copy(deep=True)

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            rec = self._jobs.get(job_id)
            return rec.model_copy(deep=True) if rec else None

    def list_recent(self, limit: int = 20) -> list[JobRecord]:
        with self._lock:
            ids = list(reversed(self._order))[:limit]
            return [
                self._jobs[i].model_copy(deep=True) for i in ids if i in self._jobs
            ]
