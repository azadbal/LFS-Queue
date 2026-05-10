"""Pure queue models and helpers used by the LFS Queue plugin."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any
from uuid import uuid4


QUEUE_STATE_VERSION = 1

STATUS_PENDING = "pending"
STATUS_LOADING = "loading"
STATUS_TRAINING = "training"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_INTERRUPTED = "interrupted"

RUNNABLE_STATUSES = {STATUS_PENDING, STATUS_FAILED, STATUS_INTERRUPTED}
TRANSIENT_STATUSES = {STATUS_LOADING, STATUS_TRAINING}
READY_TRAINER_STATES = {"idle", "ready"}
TERMINAL_TRAINER_STATES = {"completed", "stopped", "error"}

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
_MODEL_NAME_RE = re.compile(r"^model(?:[\s_-]+)(\d+)$", re.IGNORECASE)


@dataclass(slots=True)
class QueueJob:
    id: str
    label: str
    model_name: str
    status: str
    dataset_path: str
    base_output_dir: str
    job_output_dir: str
    created_at: str
    config_json: dict[str, Any]
    dataset_overrides: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    last_run_at: str = ""
    completed_at: str = ""

    @classmethod
    def new(
        cls,
        *,
        label: str,
        dataset_path: str,
        base_output_dir: str,
        job_output_dir: str,
        created_at: str,
        config_json: dict[str, Any],
        dataset_overrides: dict[str, Any],
    ) -> "QueueJob":
        return cls(
            id=uuid4().hex,
            label=label,
            model_name=label,
            status=STATUS_PENDING,
            dataset_path=dataset_path,
            base_output_dir=base_output_dir,
            job_output_dir=job_output_dir,
            created_at=created_at,
            config_json=config_json,
            dataset_overrides=dataset_overrides,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QueueJob":
        label = str(data.get("label") or data.get("model_name") or "model")
        return cls(
            id=str(data.get("id") or uuid4().hex),
            label=label,
            model_name=str(data.get("model_name") or label),
            status=normalize_status(str(data.get("status") or STATUS_PENDING)),
            dataset_path=str(data.get("dataset_path") or ""),
            base_output_dir=str(data.get("base_output_dir") or ""),
            job_output_dir=str(data.get("job_output_dir") or ""),
            created_at=str(data.get("created_at") or ""),
            config_json=dict(data.get("config_json") or {}),
            dataset_overrides=dict(data.get("dataset_overrides") or {}),
            error=str(data.get("error") or ""),
            last_run_at=str(data.get("last_run_at") or ""),
            completed_at=str(data.get("completed_at") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "model_name": self.model_name,
            "status": self.status,
            "dataset_path": self.dataset_path,
            "base_output_dir": self.base_output_dir,
            "job_output_dir": self.job_output_dir,
            "created_at": self.created_at,
            "config_json": self.config_json,
            "dataset_overrides": self.dataset_overrides,
            "error": self.error,
            "last_run_at": self.last_run_at,
            "completed_at": self.completed_at,
        }


@dataclass(slots=True, frozen=True)
class CompletionDecision:
    status: str
    continue_queue: bool
    error: str = ""


def sanitize_label(name: str, default: str = "model") -> str:
    cleaned = _INVALID_FILENAME_CHARS.sub("_", name or "")
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip(" ._-")
    return cleaned or default


def next_model_name(existing_names: list[str]) -> str:
    max_index = 0
    for name in existing_names:
        match = _MODEL_NAME_RE.match(name.strip())
        if match:
            max_index = max(max_index, int(match.group(1)))
    return f"model-{max_index + 1}"


def normalize_path(path: str | Path) -> str:
    return str(Path(path)).replace("/", "\\").rstrip("\\").lower()


def make_job_output_dir(
    base_output_dir: str,
    model_name: str,
    existing_paths: list[str] | set[str],
    path_exists: Any = None,
) -> str:
    queue_root = Path(base_output_dir) / "queue"
    slug = sanitize_label(model_name)
    taken = {normalize_path(path) for path in existing_paths}
    path_exists = path_exists or (lambda path: Path(path).exists())

    candidate = queue_root / slug
    suffix = 2
    while normalize_path(candidate) in taken or path_exists(candidate):
        candidate = queue_root / f"{slug}_{suffix}"
        suffix += 1
    return str(candidate)


def normalize_status(status: str) -> str:
    lowered = (status or "").strip().lower()
    if lowered in TRANSIENT_STATUSES:
        return STATUS_INTERRUPTED
    if lowered in {
        STATUS_PENDING,
        STATUS_COMPLETED,
        STATUS_FAILED,
        STATUS_INTERRUPTED,
    }:
        return lowered
    return STATUS_PENDING


def normalize_trainer_state(state: str | None) -> str:
    return (state or "").strip().lower()


def is_trainer_ready_state(*, has_trainer: bool, trainer_state: str | None) -> bool:
    normalized_state = normalize_trainer_state(trainer_state)
    if normalized_state in READY_TRAINER_STATES:
        return True
    return bool(has_trainer) and not normalized_state


def is_terminal_trainer_state(trainer_state: str | None) -> bool:
    return normalize_trainer_state(trainer_state) in TERMINAL_TRAINER_STATES


def should_finalize_training_end(
    *,
    trainer_state: str | None,
    trainer_error: str | None,
    finish_reason: str | None,
    finish_reason_baseline: str | None,
) -> bool:
    reason = (finish_reason or "").strip()
    baseline = (finish_reason_baseline or "").strip()
    error = (trainer_error or "").strip()
    return bool(error) or (bool(reason) and reason != baseline) or is_terminal_trainer_state(trainer_state)


def serialize_queue_state(jobs: list[QueueJob]) -> dict[str, Any]:
    return {
        "version": QUEUE_STATE_VERSION,
        "jobs": [job.to_dict() for job in jobs],
    }


def build_runtime_state(
    jobs: list[QueueJob],
    *,
    status_message: str,
    active_job_id: str | None,
    phase: str,
    auto_run: bool,
    is_running: bool,
    debug_event_count: int,
) -> dict[str, Any]:
    state = serialize_queue_state(jobs)
    state.update(
        {
            "status_message": status_message,
            "active_job_id": active_job_id,
            "phase": phase,
            "auto_run": auto_run,
            "is_running": is_running,
            "debug_event_count": debug_event_count,
        }
    )
    return state


def deserialize_queue_state(payload: dict[str, Any] | None) -> list[QueueJob]:
    if not payload:
        return []
    jobs = payload.get("jobs", [])
    if not isinstance(jobs, list):
        return []
    return [QueueJob.from_dict(item) for item in jobs if isinstance(item, dict)]


def find_next_runnable_job_index(jobs: list[QueueJob], start_index: int = 0) -> int | None:
    for index in range(max(0, start_index), len(jobs)):
        if jobs[index].status in RUNNABLE_STATUSES:
            return index
    return None


def classify_training_end(
    finish_reason: str | None,
    trainer_error: str | None,
    *,
    stop_requested: bool,
    auto_run: bool,
) -> CompletionDecision:
    reason = (finish_reason or "").strip().lower()
    error = (trainer_error or "").strip()

    if stop_requested or any(token in reason for token in ("stop", "cancel", "abort", "interrupt", "reset")):
        return CompletionDecision(status=STATUS_INTERRUPTED, continue_queue=False)
    if error or any(token in reason for token in ("error", "fail", "exception")):
        return CompletionDecision(
            status=STATUS_FAILED,
            continue_queue=auto_run,
            error=error or finish_reason or "Training failed.",
        )
    return CompletionDecision(status=STATUS_COMPLETED, continue_queue=auto_run)
