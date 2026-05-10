"""Runtime controller for queueing Lift Studio training jobs."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import tempfile
import threading
import time
from typing import Any
from uuid import uuid4

import lichtfeld as lf

try:
    from .queue_core import (
        build_runtime_state,
        CompletionDecision,
        QueueJob,
        RUNNABLE_STATUSES,
        STATUS_COMPLETED,
        STATUS_FAILED,
        STATUS_INTERRUPTED,
        STATUS_LOADING,
        STATUS_TRAINING,
        classify_training_end,
        deserialize_queue_state,
        find_next_runnable_job_index,
        is_trainer_ready_state,
        make_job_output_dir,
        next_model_name,
        normalize_path,
        serialize_queue_state,
        should_finalize_training_end,
    )
except ImportError:
    from queue_core import (
        build_runtime_state,
        CompletionDecision,
        QueueJob,
        RUNNABLE_STATUSES,
        STATUS_COMPLETED,
        STATUS_FAILED,
        STATUS_INTERRUPTED,
        STATUS_LOADING,
        STATUS_TRAINING,
        classify_training_end,
        deserialize_queue_state,
        find_next_runnable_job_index,
        is_trainer_ready_state,
        make_job_output_dir,
        next_model_name,
        normalize_path,
        serialize_queue_state,
        should_finalize_training_end,
    )


PLUGIN_ID = "lfs_queue"
SETTINGS_KEY = "queue_state"
MUTABLE_DATASET_FIELDS = ("resize_factor", "max_width", "use_cpu_cache", "use_fs_cache")
DEBUG_EVENT_LIMIT = 250
DEBUG_TRACE_PATH = Path(__file__).resolve().parent / "live_queue_debug_trace.jsonl"
TRAINING_POLL_SECONDS = 0.1
QUEUE_ADVANCE_DELAY_SECONDS = 0.25
QUEUE_READY_TIMEOUT_SECONDS = 60.0
QUEUE_READY_POLL_SECONDS = 0.25

OPTIMIZATION_KEY_REPLAY_MAP = {
    "iterations": "iterations",
    "means_lr": "means_lr",
    "shs_lr": "shs_lr",
    "opacity_lr": "opacity_lr",
    "scaling_lr": "scaling_lr",
    "rotation_lr": "rotation_lr",
    "lambda_dssim": "lambda_dssim",
    "sh_degree": "sh_degree",
    "max_cap": "max_cap",
    "tile_mode": "tile_mode",
    "steps_scaler": "steps_scaler",
    "gut": "gut",
    "use_bilateral_grid": "use_bilateral_grid",
    "enable_sparsity": "enable_sparsity",
    "mip_filter": "mip_filter",
    "ppisp_use_controller": "ppisp_use_controller",
    "ppisp_controller_activation_step": "ppisp_controller_activation_step",
    "ppisp_controller_lr": "ppisp_controller_lr",
    "bg_color": "bg_color",
    "random": "random",
    "invert_masks": "invert_masks",
    "use_alpha_as_mask": "use_alpha_as_mask",
    "undistort": "undistort",
    "revised_opacity": "revised_opacity",
}

OPTIMIZATION_SPECIAL_REPLAY_KEYS = {
    "strategy",
    "save_steps",
    "bg_mode",
    "mask_mode",
    "use_ppisp",
    "ppisp_freeze_gaussians_on_distill",
}

_controller: "QueueController | None" = None


def get_controller() -> "QueueController":
    global _controller
    if _controller is None:
        _controller = QueueController()
    return _controller


def shutdown_controller() -> None:
    global _controller
    if _controller is not None:
        _controller.shutdown()
        _controller = None


class QueueController:
    """Owns queue state, persistence, and LFS runtime integration."""

    def __init__(self) -> None:
        self._settings = lf.plugins.settings(PLUGIN_ID)
        persisted_jobs = deserialize_queue_state(self._settings.get(SETTINGS_KEY, {}))
        self._jobs: list[QueueJob] = []
        self._status_message = "Queue ready."
        self._auto_run = False
        self._active_job_id: str | None = None
        self._phase = "idle"
        self._stop_requested = False
        self._debug_events: list[dict[str, Any]] = []
        self._completion_handled_job_id: str | None = None
        self._run_token = 0
        self._training_started_observed = False
        self._finish_reason_baseline = ""
        self._runtime_event_baseline_seq = 0
        self._runtime_event_consumed_seq = 0
        self._training_handlers = lf.ScopedHandler()
        self._training_handlers.on_training_start(self._handle_training_start)
        self._training_handlers.on_training_end(self._handle_training_end)
        self._completed_output_paths: dict[str, str] = {}
        self._native_artifact_baselines: dict[str, dict[str, float]] = {}
        self._reset_debug_trace()
        if persisted_jobs:
            self._record_event("persisted_jobs_discarded", jobs=len(persisted_jobs))
        self._clear_persisted_state()
        self._record_event("controller_initialized", jobs=len(self._jobs))

    @property
    def jobs(self) -> list[QueueJob]:
        return self._jobs

    @property
    def status_message(self) -> str:
        return self._status_message

    @property
    def active_job(self) -> QueueJob | None:
        return self.get_job_by_id(self._active_job_id)

    @property
    def is_running(self) -> bool:
        return self._active_job_id is not None

    def can_add_current_job(self) -> bool:
        return self._native_start_training_ready()

    def export_state(self) -> dict[str, Any]:
        state = build_runtime_state(
            self._jobs,
            status_message=self._status_message,
            active_job_id=self._active_job_id,
            phase=self._phase,
            auto_run=self._auto_run,
            is_running=self.is_running,
            debug_event_count=len(self._debug_events),
        )
        state.update(
            {
                "run_token": self._run_token,
                "training_started_observed": self._training_started_observed,
                "trainer_state": self._trainer_state(),
                "finish_reason_baseline": self._finish_reason_baseline,
            }
        )
        return state

    def get_debug_events(self, limit: int = 50) -> list[dict[str, Any]]:
        capped_limit = max(0, min(int(limit), DEBUG_EVENT_LIMIT))
        if capped_limit == 0:
            return []
        return list(self._debug_events[-capped_limit:])

    def shutdown(self) -> None:
        self._record_event("controller_shutdown")
        self._training_handlers.clear()
        self._release_frame_callback()

    def add_current_job(self) -> bool:
        ready = self.can_add_current_job()
        self._record_event(
            "queue.add_attempt",
            ready=ready,
            has_trainer=self._has_trainer(),
            trainer_state=self._trainer_state(),
        )
        if not ready:
            self._record_event("queue.add_blocked_not_ready")
            self._set_status("Add to Queue is available when LFS Start Training is available.", error=True)
            return False
        try:
            config_json = self._capture_current_config()
            dataset_path, base_output_dir, dataset_overrides = self._capture_dataset_snapshot()
        except Exception as exc:
            self._record_event("add_current_failed", error=str(exc))
            self._set_status(f"Unable to capture current settings: {exc}", error=True)
            return False

        label = next_model_name([job.model_name for job in self._jobs])
        output_dir = make_job_output_dir(
            base_output_dir,
            label,
            existing_paths=[job.job_output_dir for job in self._jobs],
        )
        job = QueueJob.new(
            label=label,
            dataset_path=dataset_path,
            base_output_dir=base_output_dir,
            job_output_dir=output_dir,
            created_at=self._timestamp(),
            config_json=config_json,
            dataset_overrides=dataset_overrides,
        )
        self._jobs.append(job)
        self._persist()
        self._record_event(
            "queue.job_added",
            job_id=job.id,
            label=job.label,
            dataset_path=job.dataset_path,
            job_output_dir=job.job_output_dir,
        )
        self._set_status(f"Queued {job.label}.")
        return True

    def update_job_label(self, job_id: str, label: str) -> bool:
        job = self.get_job_by_id(job_id)
        if job is None:
            return False

        new_label = label.strip() or job.label
        if new_label == job.label:
            return False

        previous_label = job.label
        job.label = new_label
        job.model_name = new_label
        if job.status != STATUS_COMPLETED:
            taken_paths = [item.job_output_dir for item in self._jobs if item.id != job.id]
            job.job_output_dir = make_job_output_dir(job.base_output_dir, new_label, taken_paths)
        self._persist()
        self._record_event("job_renamed", job_id=job.id, from_label=previous_label, to_label=new_label)
        self._request_redraw()
        return True

    def move_job(self, job_id: str, direction: int) -> bool:
        index = self._job_index(job_id)
        if index is None:
            return False
        other_index = index + direction
        if other_index < 0 or other_index >= len(self._jobs):
            return False
        self._jobs[index], self._jobs[other_index] = self._jobs[other_index], self._jobs[index]
        self._persist()
        self._record_event("job_moved", job_id=job_id, direction=direction)
        return True

    def delete_job(self, job_id: str) -> bool:
        index = self._job_index(job_id)
        if index is None:
            return False
        if self._active_job_id == job_id:
            self.stop_queue()
        self._record_event("job_deleted", job_id=job_id)
        del self._jobs[index]
        self._persist()
        self._set_status("Job removed.")
        return True

    def clear_finished_and_failed(self) -> int:
        before = len(self._jobs)
        self._jobs = [job for job in self._jobs if job.status not in {STATUS_COMPLETED, STATUS_FAILED}]
        removed = before - len(self._jobs)
        if removed:
            self._persist()
            self._record_event("jobs_cleared", removed=removed)
        self._set_status(f"Removed {removed} finished job(s)." if removed else "Nothing to clear.")
        return removed

    def clear_queue(self) -> int:
        if self.is_running:
            self._set_status("Stop the queue before clearing jobs.", error=True)
            return 0
        removed = len(self._jobs)
        self._jobs = []
        self._persist()
        self._record_event("queue_cleared", removed=removed)
        self._set_status(f"Cleared {removed} queued job(s)." if removed else "Queue already empty.")
        return removed

    def run_selected(self, job_id: str) -> bool:
        if self.is_running:
            self._set_status("Queue is already running.", error=True)
            return False

        job = self.get_job_by_id(job_id)
        if job is None:
            self._set_status("Select a job first.", error=True)
            return False
        if job.status not in RUNNABLE_STATUSES:
            self._set_status(f"{job.label} is not runnable in its current state.", error=True)
            return False

        self._auto_run = False
        self._record_event("queue.run_selected_requested", job_id=job.id, label=job.label)
        return self._start_job(job)

    def run_all_pending(self) -> bool:
        if self.is_running:
            self._set_status("Queue is already running.", error=True)
            return False

        next_index = find_next_runnable_job_index(self._jobs)
        if next_index is None:
            self._set_status("No pending, failed, or interrupted jobs to run.", error=True)
            return False

        self._auto_run = True
        self._record_event("queue.run_all_requested", start_job_id=self._jobs[next_index].id)
        return self._start_job(self._jobs[next_index])

    def stop_queue(self) -> bool:
        if not self.is_running:
            self._auto_run = False
            self._set_status("Queue is not running.")
            return False

        self._auto_run = False
        self._stop_requested = True
        self._record_event("stop_requested", active_job_id=self._active_job_id, phase=self._phase)
        active_job = self.active_job
        if active_job is not None and active_job.status == STATUS_LOADING:
            current_index = self._job_index(active_job.id)
            self._mark_job(active_job, STATUS_INTERRUPTED, error="Queue stopped before training started.")
            self._finish_current_job(current_index=current_index)
        else:
            try:
                lf.stop_training()
            except Exception as exc:
                self._set_status(f"Unable to stop training cleanly: {exc}", error=True)
                return False
        self._set_status("Stopping queue...")
        return True

    def get_job_by_id(self, job_id: str | None) -> QueueJob | None:
        if not job_id:
            return None
        for job in self._jobs:
            if job.id == job_id:
                return job
        return None

    def _job_index(self, job_id: str) -> int | None:
        for index, job in enumerate(self._jobs):
            if job.id == job_id:
                return index
        return None

    def _start_job(self, job: QueueJob) -> bool:
        try:
            Path(job.job_output_dir).mkdir(parents=True, exist_ok=True)
            if not self._dataset_ready(job):
                raise RuntimeError("The queued dataset is no longer the active LFS dataset.")
            job.status = STATUS_LOADING
            job.error = ""
            job.last_run_at = self._timestamp()
            self._active_job_id = job.id
            self._stop_requested = False
            self._completion_handled_job_id = None
            self._run_token += 1
            self._training_started_observed = False
            self._finish_reason_baseline = ""
            self._runtime_event_baseline_seq = 0
            self._runtime_event_consumed_seq = 0
            self._native_artifact_baselines[job.id] = self._snapshot_native_artifacts(job.base_output_dir)
            self._phase = "starting"
            self._persist()
            self._set_status(f"Starting {job.label}...")
            lf.log.info(
                f"{PLUGIN_ID}: starting job {job.label}; "
                f"dataset={job.dataset_path}; "
                f"base_output={job.base_output_dir}; "
                f"job_output={job.job_output_dir}"
            )
            self._record_event(
                "queue.job_started",
                job_id=job.id,
                label=job.label,
                dataset_path=job.dataset_path,
                base_output_dir=job.base_output_dir,
                job_output_dir=job.job_output_dir,
                auto_run=self._auto_run,
                run_token=self._run_token,
            )
            if self._job_ready_to_start(job):
                self._begin_training_for_job(job)
            else:
                raise RuntimeError("LFS Start Training is not available for the active dataset.")
            return True
        except Exception as exc:
            self._active_job_id = None
            self._phase = "idle"
            job.status = STATUS_FAILED
            job.error = f"Unable to start job: {exc}"
            self._persist()
            self._record_event("queue.job_failed", job_id=job.id, label=job.label, error=str(exc))
            self._set_status(job.error, error=True)
            self._release_frame_callback()
            return False

    def _handle_training_start(self, _payload: Any | None = None) -> None:
        active_job = self.active_job
        self._record_event(
            "training_start_callback_entered",
            job_id=(active_job.id if active_job is not None else ""),
            label=(active_job.label if active_job is not None else ""),
        )
        if not self._can_accept_training_start():
            if active_job is not None:
                self._record_event(
                    "training_start_ignored",
                    job_id=active_job.id,
                    label=active_job.label,
                    phase=self._phase,
                    run_token=self._run_token,
                    trainer_state=self._trainer_state(),
                )
            return
        self._observe_training_start(source="hook")

    def _handle_training_end(self, _payload: Any | None = None) -> None:
        active_job = self.active_job
        trainer_state = self._trainer_state()
        finish_reason = lf.finish_reason()
        trainer_error = lf.trainer_error()
        self._record_event(
            "training_end_callback_entered",
            job_id=(active_job.id if active_job is not None else ""),
            label=(active_job.label if active_job is not None else ""),
            finish_reason=finish_reason,
            trainer_error=trainer_error,
            trainer_state=trainer_state,
        )
        if self._phase not in {"starting_training", "training"}:
            if active_job is not None:
                self._record_event(
                    "training_end_ignored_phase",
                    job_id=active_job.id,
                    label=active_job.label,
                    phase=self._phase,
                    run_token=self._run_token,
                    trainer_state=trainer_state,
                    finish_reason=finish_reason,
                    trainer_error=trainer_error,
                )
            return
        if not self._training_started_observed and not self._can_finalize_without_start():
            if active_job is not None:
                self._record_event(
                    "training_end_ignored_pre_start",
                    job_id=active_job.id,
                    label=active_job.label,
                    trainer_state=trainer_state,
                    finish_reason=finish_reason,
                    trainer_error=trainer_error,
                )
            return
        terminal_detected = should_finalize_training_end(
            trainer_state=trainer_state,
            trainer_error=trainer_error,
            finish_reason=finish_reason,
            finish_reason_baseline=self._finish_reason_baseline,
        )
        if not terminal_detected:
            if active_job is not None:
                self._record_event(
                    "training_end_ignored_non_terminal",
                    job_id=active_job.id,
                    label=active_job.label,
                    run_token=self._run_token,
                    trainer_state=trainer_state,
                    finish_reason=finish_reason,
                    trainer_error=trainer_error,
                )
            return

        self._finalize_active_job(source="hook")

    def _finalize_active_job(self, *, source: str, decision_override: CompletionDecision | None = None) -> None:
        active_job = self.active_job
        if active_job is None:
            return
        if self._completion_handled_job_id == active_job.id:
            self._record_event("training_end_duplicate_ignored", job_id=active_job.id, source=source)
            return
        self._completion_handled_job_id = active_job.id

        decision = decision_override or classify_training_end(
            lf.finish_reason(),
            lf.trainer_error(),
            stop_requested=self._stop_requested,
            auto_run=self._auto_run,
        )
        self._phase = "finalizing"
        self._record_event(
            "queue.training_finished",
            job_id=active_job.id,
            label=active_job.label,
            source=source,
            run_token=self._run_token,
            training_started_observed=self._training_started_observed,
            trainer_state=self._trainer_state(),
            finish_reason=lf.finish_reason(),
            trainer_error=lf.trainer_error(),
            decision_status=decision.status,
            continue_queue=decision.continue_queue,
        )

        if decision.status == STATUS_COMPLETED:
            preserve_error = self._preserve_completed_result(active_job)
            if preserve_error:
                decision = CompletionDecision(
                    status=STATUS_FAILED,
                    continue_queue=decision.continue_queue,
                    error=preserve_error,
                )
            else:
                self._claim_native_training_artifacts(active_job)

        current_index = self._job_index(active_job.id)
        self._mark_job(active_job, decision.status, error=decision.error)
        if decision.status == STATUS_COMPLETED:
            self._set_status(f"Completed {active_job.label}.")
        elif decision.status == STATUS_INTERRUPTED:
            self._set_status(f"Interrupted {active_job.label}.")
        else:
            self._set_status(f"Failed {active_job.label}: {active_job.error}", error=True)

        self._finish_current_job(continue_queue=decision.continue_queue, current_index=current_index)

    def _finish_current_job(self, *, continue_queue: bool = False, current_index: int | None = None) -> None:
        self._active_job_id = None
        self._phase = "idle"
        self._stop_requested = False
        self._training_started_observed = False
        self._finish_reason_baseline = ""
        self._runtime_event_baseline_seq = 0
        self._runtime_event_consumed_seq = 0
        self._persist()
        self._release_frame_callback()
        self._record_event(
            "queue.job_finished",
            continue_queue=continue_queue,
            next_start_index=(0 if current_index is None else current_index + 1),
        )

        if continue_queue:
            start_index = 0 if current_index is None else current_index + 1
            next_index = find_next_runnable_job_index(self._jobs, start_index=start_index)
            if next_index is not None:
                self._record_event("queue.job_advance", next_job_id=self._jobs[next_index].id)
                self._prepare_for_next_job()
                self._defer_start_job(self._jobs[next_index])
                return

        self._auto_run = False
        self._load_completed_outputs()
        self._request_redraw()

    def _mark_job(self, job: QueueJob, status: str, *, error: str = "") -> None:
        job.status = status
        job.error = error
        if status == STATUS_COMPLETED:
            job.completed_at = self._timestamp()
        self._persist()
        self._record_event("job_marked", job_id=job.id, label=job.label, status=status, error=error)
        self._request_redraw()

    def _capture_current_config(self) -> dict[str, Any]:
        temp_path = self._temp_json_path("capture")
        try:
            lf.save_config_file(str(temp_path))
            with temp_path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        finally:
            temp_path.unlink(missing_ok=True)

    def _capture_dataset_snapshot(self) -> tuple[str, str, dict[str, Any]]:
        dataset = lf.dataset_params()
        dataset_path = str(getattr(dataset, "data_path", "") or "").strip()
        current_output_dir = str(getattr(dataset, "output_path", "") or "").strip()
        base_output_dir = self._canonical_base_output_dir(current_output_dir)
        if not dataset_path:
            raise RuntimeError("No dataset is currently loaded.")
        if not base_output_dir:
            raise RuntimeError("The current dataset has no output directory.")

        overrides = {
            name: getattr(dataset, name)
            for name in MUTABLE_DATASET_FIELDS
            if hasattr(dataset, name)
        }
        self._record_event(
            "dataset_snapshot_captured",
            dataset_path=dataset_path,
            base_output_dir=base_output_dir,
            dataset_override_keys=sorted(overrides.keys()),
        )
        return dataset_path, base_output_dir, overrides

    def _dataset_ready(self, job: QueueJob) -> bool:
        if not lf.has_scene():
            return False
        dataset = lf.dataset_params()
        current_path = str(getattr(dataset, "data_path", "") or "")
        if normalize_path(current_path) != normalize_path(job.dataset_path):
            return False
        return True

    def _job_ready_to_start(self, job: QueueJob) -> bool:
        dataset_ready = self._dataset_ready(job)
        has_trainer = self._has_trainer()
        trainer_state = self._trainer_state()
        ready = dataset_ready and is_trainer_ready_state(
            has_trainer=has_trainer,
            trainer_state=trainer_state,
        )
        self._record_event(
            "job_ready_check",
            job_id=job.id,
            label=job.label,
            dataset_ready=dataset_ready,
            has_trainer=has_trainer,
            trainer_state=trainer_state,
            ready=ready,
        )
        return ready

    def _apply_job_config(self, job: QueueJob) -> None:
        self._record_event("job_config_apply_begin", job_id=job.id, label=job.label)
        optimization = lf.optimization_params()
        optimization_payload = job.config_json.get("optimization") or {}
        applied_keys: list[str] = []
        skipped_keys: list[str] = []
        skipped_errors: dict[str, str] = {}
        for name, value in optimization_payload.items():
            if name not in OPTIMIZATION_KEY_REPLAY_MAP and name not in OPTIMIZATION_SPECIAL_REPLAY_KEYS:
                skipped_keys.append(name)
                skipped_errors[name] = "unsupported replay key"
                continue
            try:
                self._apply_optimization_value(optimization, name, value)
                applied_keys.append(name)
            except Exception as exc:
                skipped_keys.append(name)
                skipped_errors[name] = str(exc)

        dataset = lf.dataset_params()
        for name, value in job.dataset_overrides.items():
            try:
                setattr(dataset, name, value)
            except Exception as exc:
                skipped_errors[name] = str(exc)
        self._record_event(
            "job_config_applied",
            job_id=job.id,
            label=job.label,
            dataset_override_keys=sorted(job.dataset_overrides.keys()),
            optimization_keys=sorted(applied_keys),
            optimization_skipped_keys=sorted(skipped_keys),
            skipped_errors=skipped_errors,
        )

    def _apply_optimization_value(self, optimization: Any, name: str, value: Any) -> None:
        if name == "strategy":
            optimization.set_strategy(str(value))
            return
        if name == "save_steps":
            optimization.clear_save_steps()
            for step in list(value or []):
                optimization.add_save_step(int(step))
            return
        if name == "bg_mode":
            mode_name = str(value or "").strip().upper()
            optimization.bg_mode = getattr(lf.BackgroundMode, mode_name)
            return
        if name == "mask_mode":
            mode_name = str(value or "").strip().upper()
            optimization.mask_mode = getattr(lf.MaskMode, mode_name)
            return
        if name == "use_ppisp":
            optimization.ppisp = bool(value)
            return
        if name == "ppisp_freeze_gaussians_on_distill":
            optimization.ppisp_freeze_gaussians = bool(value)
            return

        target_name = OPTIMIZATION_KEY_REPLAY_MAP[name]
        setattr(optimization, target_name, value)

    def _begin_training_for_job(self, job: QueueJob) -> None:
        try:
            self._phase = "starting_training"
            job.status = STATUS_TRAINING
            dataset = lf.dataset_params()
            current_output = str(getattr(dataset, "output_path", "") or "")
            lf.log.info(
                f"{PLUGIN_ID}: dataset ready for {job.label}; "
                f"current_output={current_output or '<empty>'}; "
                f"job_output={job.job_output_dir}"
            )
            self._record_event(
                "dataset_ready",
                job_id=job.id,
                label=job.label,
                current_output=current_output,
                job_output=job.job_output_dir,
                run_token=self._run_token,
            )
            self._apply_job_config(job)
            validation_error = self._validate_training_params()
            self._record_event(
                "training_params_validated",
                job_id=job.id,
                label=job.label,
                validation_error=validation_error,
            )
            if validation_error:
                self._record_event(
                    "job_config_invalid",
                    job_id=job.id,
                    label=job.label,
                    trainer_state=self._trainer_state(),
                    error=validation_error,
                )
                current_index = self._job_index(job.id)
                self._mark_job(job, STATUS_FAILED, error=f"Invalid training configuration: {validation_error}")
                self._set_status(f"Failed {job.label}: {job.error}", error=True)
                self._finish_current_job(continue_queue=self._auto_run, current_index=current_index)
                return
            self._training_started_observed = False
            self._finish_reason_baseline = str(lf.finish_reason() or "").strip()
            self._record_event(
                "start_training_begin",
                job_id=job.id,
                label=job.label,
                finish_reason_baseline=self._finish_reason_baseline,
            )
            lf.start_training()
            self._record_event(
                "start_training_returned",
                job_id=job.id,
                label=job.label,
            )
            self._persist()
            self._record_event(
                "queue.training_started",
                job_id=job.id,
                label=job.label,
                run_token=self._run_token,
                finish_reason_baseline=self._finish_reason_baseline,
                trainer_state=self._trainer_state(),
                has_trainer=self._has_trainer(),
            )
            self._start_training_poll_thread(job.id, self._run_token)
            self._set_status(f"Training {job.label}...")
        except Exception as exc:
            current_index = self._job_index(job.id)
            self._mark_job(job, STATUS_FAILED, error=f"Unable to start job: {exc}")
            self._set_status(f"Failed {job.label}: {job.error}", error=True)
            self._finish_current_job(continue_queue=self._auto_run, current_index=current_index)

    def _defer_start_job(self, job: QueueJob) -> None:
        job_id = job.id
        run_token = self._run_token

        def worker() -> None:
            time.sleep(QUEUE_ADVANCE_DELAY_SECONDS)
            next_job = self.get_job_by_id(job_id)
            if next_job is None or self.is_running or not self._auto_run:
                return
            if not self._wait_for_native_start_ready(job_id=job_id, previous_run_token=run_token):
                if next_job.status in RUNNABLE_STATUSES:
                    next_job.status = STATUS_FAILED
                    next_job.error = "Timed out waiting for LFS Start Training to become available."
                    self._record_event("queue.job_failed", job_id=job_id, label=next_job.label, error=next_job.error)
                    self._set_status(f"Unable to start {next_job.label}: {next_job.error}", error=True)
                self._auto_run = False
                return
            self._record_event("queue.deferred_start", job_id=job_id, previous_run_token=run_token)
            self._start_job(next_job)

        threading.Thread(
            target=worker,
            name=f"{PLUGIN_ID}-advance-{run_token}",
            daemon=True,
        ).start()

    def _prepare_for_next_job(self) -> None:
        try:
            self._record_event("queue.reset_training_requested")
            lf.reset_training()
        except Exception as exc:
            self._record_event("queue.reset_training_failed", error=str(exc))

    def _wait_for_native_start_ready(self, *, job_id: str, previous_run_token: int) -> bool:
        deadline = time.monotonic() + QUEUE_READY_TIMEOUT_SECONDS
        checks = 0
        while time.monotonic() < deadline:
            checks += 1
            if self.is_running or not self._auto_run:
                return False
            if self._native_start_training_ready():
                self._record_event(
                    "queue.ready_for_next_job",
                    job_id=job_id,
                    previous_run_token=previous_run_token,
                    checks=checks,
                    trainer_state=self._trainer_state(),
                )
                return True
            time.sleep(QUEUE_READY_POLL_SECONDS)
        self._record_event(
            "queue.ready_for_next_job_timeout",
            job_id=job_id,
            previous_run_token=previous_run_token,
            checks=checks,
            trainer_state=self._trainer_state(),
            has_trainer=self._has_trainer(),
        )
        return False

    def _start_training_poll_thread(self, job_id: str, run_token: int) -> None:
        def worker() -> None:
            while True:
                active_job = self.active_job
                if active_job is None or active_job.id != job_id or self._run_token != run_token:
                    return
                if self._phase not in {"starting_training", "training"}:
                    return
                self._poll_training_state(active_job)
                time.sleep(TRAINING_POLL_SECONDS)

        threading.Thread(
            target=worker,
            name=f"{PLUGIN_ID}-training-poll-{run_token}",
            daemon=True,
        ).start()

    def _preserve_completed_result(self, job: QueueJob) -> str:
        scene = lf.get_scene()
        if scene is None:
            return "No scene is available to preserve the completed model."

        source_name = self._find_training_model_name(scene)
        if not source_name:
            return "Unable to find the trained model in the scene."

        output_path = str(Path(job.job_output_dir) / f"{job.model_name}.ply")
        try:
            Path(job.job_output_dir).mkdir(parents=True, exist_ok=True)
            node = scene.get_node(source_name)
            if node is None:
                return f"Unable to find trained model node {source_name}."
            splat_data = node.splat_data()
            if splat_data is None:
                return f"Unable to read splat data from {source_name}."
            lf.io.save_ply(splat_data, output_path)
            self._completed_output_paths[job.id] = output_path
            self._record_event(
                "queue.model_preserved",
                job_id=job.id,
                label=job.label,
                source_name=source_name,
                output_path=output_path,
            )
            return ""
        except Exception as exc:
            return f"Unable to save trained model: {exc}"

    def _capture_splat_node(self, node_name: str) -> dict[str, Any] | None:
        scene = lf.get_scene()
        if scene is None:
            return None
        node = scene.get_node(node_name)
        if node is None:
            return None
        splat_data = node.splat_data()
        if splat_data is None:
            return None
        return {
            "means": splat_data.means_raw.clone().cpu(),
            "sh0": splat_data.sh0_raw.clone().cpu(),
            "shN": splat_data.shN_raw.clone().cpu(),
            "scaling": splat_data.scaling_raw.clone().cpu(),
            "rotation": splat_data.rotation_raw.clone().cpu(),
            "opacity": splat_data.opacity_raw.clone().cpu(),
        }

    def _load_completed_outputs(self) -> None:
        if not self._completed_output_paths:
            return
        loaded_paths: list[str] = []
        try:
            lf.switch_to_edit_mode()
        except Exception as exc:
            self._record_event("queue.switch_to_edit_mode_failed", error=str(exc))

        self._remove_live_training_model()

        for job in self._jobs:
            if job.status != STATUS_COMPLETED:
                continue
            output_path = self._completed_output_paths.get(job.id, "")
            if not output_path or not Path(output_path).exists():
                continue
            try:
                lf.load_file(output_path)
                loaded_paths.append(output_path)
            except Exception as exc:
                self._record_event("queue.output_load_failed", job_id=job.id, label=job.label, output_path=output_path, error=str(exc))

        if loaded_paths:
            self._record_event("queue.completed_outputs_loaded", paths=loaded_paths)

    def _snapshot_native_artifacts(self, base_output_dir: str) -> dict[str, float]:
        base_path = Path(base_output_dir)
        paths = list(base_path.glob("splat_*.ply"))
        paths.append(base_path / "checkpoints" / "checkpoint.resume")
        snapshot: dict[str, float] = {}
        for path in paths:
            try:
                if path.is_file():
                    snapshot[str(path.resolve()).lower()] = path.stat().st_mtime
            except OSError:
                continue
        return snapshot

    def _is_new_or_updated_artifact(self, path: Path, baseline: dict[str, float]) -> bool:
        try:
            key = str(path.resolve()).lower()
            current_mtime = path.stat().st_mtime
        except OSError:
            return False
        previous_mtime = baseline.get(key)
        return previous_mtime is None or current_mtime > previous_mtime + 0.001

    def _claim_native_training_artifacts(self, job: QueueJob) -> None:
        base_path = Path(job.base_output_dir)
        job_path = Path(job.job_output_dir)
        baseline = self._native_artifact_baselines.pop(job.id, {})
        claimed: list[str] = []
        removed: list[str] = []

        checkpoint_path = base_path / "checkpoints" / "checkpoint.resume"
        if checkpoint_path.is_file() and self._is_new_or_updated_artifact(checkpoint_path, baseline):
            target_path = job_path / "checkpoints" / "checkpoint.resume"
            try:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                if target_path.exists():
                    target_path.unlink()
                shutil.move(str(checkpoint_path), str(target_path))
                claimed.append(str(target_path))
            except Exception as exc:
                self._record_event(
                    "queue.checkpoint_claim_failed",
                    job_id=job.id,
                    label=job.label,
                    source_path=str(checkpoint_path),
                    target_path=str(target_path),
                    error=str(exc),
                )

        for splat_path in base_path.glob("splat_*.ply"):
            if not splat_path.is_file() or not self._is_new_or_updated_artifact(splat_path, baseline):
                continue
            try:
                splat_path.unlink()
                removed.append(str(splat_path))
            except Exception as exc:
                self._record_event(
                    "queue.native_splat_cleanup_failed",
                    job_id=job.id,
                    label=job.label,
                    path=str(splat_path),
                    error=str(exc),
                )

        if claimed or removed:
            self._record_event(
                "queue.native_artifacts_claimed",
                job_id=job.id,
                label=job.label,
                claimed_paths=claimed,
                removed_paths=removed,
            )

    def _remove_live_training_model(self) -> None:
        scene = lf.get_scene()
        if scene is None:
            return
        source_name = self._find_training_model_name(scene)
        if not source_name:
            return
        try:
            lf.remove_node(source_name)
            self._record_event("queue.live_training_model_removed", name=source_name)
        except Exception as exc:
            self._record_event("queue.live_training_model_remove_failed", name=source_name, error=str(exc))

    def _find_training_model_name(self, scene) -> str:
        candidates = []
        training_name = getattr(scene, "training_model_node_name", "")
        if training_name:
            candidates.append(training_name)
        candidates.extend(["Model", "loaded_model"])

        for candidate in candidates:
            if scene.get_node(candidate) is not None:
                return candidate

        for node in scene.get_nodes():
            if node.type == lf.scene.NodeType.SPLAT and node.gaussian_count > 0:
                return node.name
        return ""

    def _unique_scene_name(self, desired_name: str) -> str:
        scene = lf.get_scene()
        if scene is None:
            return desired_name

        base_name = desired_name.strip() or "model"
        candidate = base_name
        suffix = 2
        while scene.get_node(candidate) is not None:
            candidate = f"{base_name} {suffix}"
            suffix += 1
        return candidate

    def _ensure_frame_callback(self) -> None:
        return

    def _release_frame_callback(self) -> None:
        return

    def _persist(self) -> None:
        return

    def _clear_persisted_state(self) -> None:
        try:
            self._settings.set(SETTINGS_KEY, serialize_queue_state([]))
        except Exception as exc:
            self._record_event("persisted_state_clear_failed", error=str(exc))

    def _set_status(self, message: str, *, error: bool = False) -> None:
        self._status_message = message
        self._record_event("status", message=message, error=error)
        if error:
            lf.log.error(f"{PLUGIN_ID}: {message}")
        else:
            lf.log.info(f"{PLUGIN_ID}: {message}")
        self._request_redraw()

    def _request_redraw(self) -> None:
        if hasattr(lf.ui, "request_redraw"):
            lf.ui.request_redraw()

    def _temp_json_path(self, prefix: str) -> Path:
        return Path(tempfile.gettempdir()) / f"{PLUGIN_ID}_{prefix}_{uuid4().hex}.json"

    def _timestamp(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    def _canonical_base_output_dir(self, output_dir: str) -> str:
        raw_path = Path(output_dir)
        parts = list(raw_path.parts)
        lowered_parts = [part.lower() for part in parts]
        if "queue" not in lowered_parts:
            return str(raw_path)

        queue_index = lowered_parts.index("queue")
        if queue_index <= 0:
            return str(raw_path)
        return str(Path(*parts[:queue_index]))

    def _normalize_persisted_jobs(self) -> None:
        normalized_output_paths: list[str] = []
        for job in self._jobs:
            if job.base_output_dir:
                job.base_output_dir = self._canonical_base_output_dir(job.base_output_dir)
            elif job.job_output_dir:
                job.base_output_dir = self._canonical_base_output_dir(job.job_output_dir)

            if job.status != STATUS_COMPLETED and job.base_output_dir:
                job.job_output_dir = make_job_output_dir(
                    job.base_output_dir,
                    job.model_name,
                    existing_paths=normalized_output_paths,
                    path_exists=lambda _path: False,
                )

            if job.job_output_dir:
                normalized_output_paths.append(job.job_output_dir)

    def _has_trainer(self) -> bool:
        try:
            return bool(lf.has_trainer())
        except Exception:
            return False

    def _trainer_state(self) -> str:
        try:
            return str(lf.trainer_state() or "").strip().lower()
        except Exception:
            return ""

    def _native_start_training_ready(self) -> bool:
        return is_trainer_ready_state(
            has_trainer=self._has_trainer(),
            trainer_state=self._trainer_state(),
        )

    def _validate_training_params(self) -> str:
        params = lf.optimization_params()
        if params is None:
            return ""
        if hasattr(params, "has_params") and not params.has_params():
            return ""
        validate = getattr(params, "validate", None)
        if validate is None:
            return ""
        return str(validate() or "").strip()

    def _context_is_training(self) -> bool:
        try:
            return bool(getattr(lf.context(), "is_training", False))
        except Exception:
            return False

    def _can_finalize_without_start(self) -> bool:
        if self._stop_requested:
            return True
        return should_finalize_training_end(
            trainer_state=self._trainer_state(),
            trainer_error=lf.trainer_error(),
            finish_reason=lf.finish_reason(),
            finish_reason_baseline=self._finish_reason_baseline,
        )

    def _can_accept_training_start(self) -> bool:
        active_job = self.active_job
        if active_job is None:
            return False
        return self._phase == "starting_training"

    def _observe_training_start(self, *, source: str) -> None:
        active_job = self.active_job
        if active_job is None:
            return
        if self._phase not in {"starting_training", "training"}:
            self._record_event(
                "training_start_rejected_phase",
                job_id=active_job.id,
                label=active_job.label,
                source=source,
                phase=self._phase,
                run_token=self._run_token,
                trainer_state=self._trainer_state(),
            )
            return
        if self._training_started_observed:
            return
        self._training_started_observed = True
        self._phase = "training"
        self._record_event(
            "training_start_observed",
            job_id=active_job.id,
            label=active_job.label,
            source=source,
            run_token=self._run_token,
            trainer_state=self._trainer_state(),
        )

    def _poll_training_state(self, job: QueueJob) -> None:
        trainer_state = self._trainer_state()
        trainer_error = str(lf.trainer_error() or "").strip()
        finish_reason = str(lf.finish_reason() or "").strip()
        context_is_training = self._context_is_training()
        self._record_event(
            "training_poll",
            job_id=job.id,
            label=job.label,
            trainer_state=trainer_state,
            trainer_error=trainer_error,
            finish_reason=finish_reason,
            context_is_training=context_is_training,
        )

        if self._phase == "starting_training" and (trainer_state == "running" or context_is_training):
            self._observe_training_start(source="poll")
            return

        if self._phase not in {"starting_training", "training"}:
            return

        terminal_detected = should_finalize_training_end(
            trainer_state=trainer_state,
            trainer_error=trainer_error,
            finish_reason=finish_reason,
            finish_reason_baseline=self._finish_reason_baseline,
        )

        if not self._training_started_observed:
            if terminal_detected:
                self._record_event(
                    "training_terminal_detected_pre_start",
                    job_id=job.id,
                    label=job.label,
                    run_token=self._run_token,
                    trainer_state=trainer_state,
                    finish_reason=finish_reason,
                    trainer_error=trainer_error,
                )
                self._finalize_active_job(source="poll")
                return
            return

        if terminal_detected:
            self._record_event(
                "training_terminal_detected",
                job_id=job.id,
                label=job.label,
                run_token=self._run_token,
                trainer_state=trainer_state,
                finish_reason=finish_reason,
                finish_reason_baseline=self._finish_reason_baseline,
                trainer_error=trainer_error,
            )
            self._finalize_active_job(source="poll")

    def _record_event(self, event: str, **details: Any) -> None:
        payload: dict[str, Any] = {
            "timestamp": self._timestamp(),
            "event": event,
            "phase": self._phase,
            "run_token": self._run_token,
            "active_job_id": self._active_job_id,
        }
        if details:
            payload["details"] = details
        self._debug_events.append(payload)
        if len(self._debug_events) > DEBUG_EVENT_LIMIT:
            del self._debug_events[:-DEBUG_EVENT_LIMIT]
        self._append_debug_trace(payload)

    def _reset_debug_trace(self) -> None:
        try:
            DEBUG_TRACE_PATH.write_text("", encoding="utf-8")
        except Exception:
            pass

    def _append_debug_trace(self, payload: dict[str, Any]) -> None:
        try:
            with DEBUG_TRACE_PATH.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, default=str))
                handle.write("\n")
        except Exception:
            pass
