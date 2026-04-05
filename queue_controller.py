"""Runtime controller for queueing Lift Studio training jobs."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import threading
import time
from typing import Any
from uuid import uuid4

import lichtfeld as lf

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


PLUGIN_ID = "lfs_queue"
SETTINGS_KEY = "queue_state"
MUTABLE_DATASET_FIELDS = ("resize_factor", "max_width", "use_cpu_cache", "use_fs_cache")
DEBUG_EVENT_LIMIT = 250
DEBUG_TRACE_PATH = Path(__file__).resolve().parent / "live_queue_debug_trace.jsonl"
LOAD_READY_TIMEOUT_SECONDS = 30.0
LOAD_READY_POLL_SECONDS = 0.1
TRAINING_POLL_SECONDS = 0.1

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
        self._dataset_event_baseline_seq = 0
        self._runtime_event_baseline_seq = 0
        self._runtime_event_consumed_seq = 0
        self._training_handlers = lf.ScopedHandler()
        self._training_handlers.on_training_start(self._handle_training_start)
        self._training_handlers.on_training_end(self._handle_training_end)
        self._preserved_models: dict[str, dict[str, Any]] = {}
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
        self._record_event("add_current_requested")
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
            "job_added",
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
        self._record_event("run_selected_requested", job_id=job.id, label=job.label)
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
        self._record_event("run_all_requested", start_job_id=self._jobs[next_index].id)
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
            self._mark_job(active_job, STATUS_INTERRUPTED, error="Queue stopped during dataset reload.")
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
            job.status = STATUS_LOADING
            job.error = ""
            job.last_run_at = self._timestamp()
            self._active_job_id = job.id
            self._stop_requested = False
            self._completion_handled_job_id = None
            self._run_token += 1
            self._training_started_observed = False
            self._finish_reason_baseline = ""
            self._dataset_event_baseline_seq = 0
            self._runtime_event_baseline_seq = 0
            self._runtime_event_consumed_seq = 0
            self._phase = "loading"
            self._persist()
            self._set_status(f"Loading dataset for {job.label}...")
            lf.log.info(
                f"{PLUGIN_ID}: starting job {job.label}; "
                f"dataset={job.dataset_path}; "
                f"base_output={job.base_output_dir}; "
                f"job_output={job.job_output_dir}"
            )
            self._record_event(
                "job_starting",
                job_id=job.id,
                label=job.label,
                dataset_path=job.dataset_path,
                base_output_dir=job.base_output_dir,
                job_output_dir=job.job_output_dir,
                auto_run=self._auto_run,
                run_token=self._run_token,
            )
            self._record_event(
                "load_file_begin",
                job_id=job.id,
                label=job.label,
                dataset_path=job.dataset_path,
                job_output_dir=job.job_output_dir,
            )
            self._dataset_event_baseline_seq = self._latest_runtime_event_sequence_for("dataset.load_completed")
            lf.load_file(job.dataset_path, is_dataset=True, output_path=job.job_output_dir)
            self._record_event(
                "load_file_returned",
                job_id=job.id,
                label=job.label,
                dataset_path=job.dataset_path,
                job_output_dir=job.job_output_dir,
                dataset_event_baseline_seq=self._dataset_event_baseline_seq,
            )
            if self._job_ready_to_start(job):
                self._record_event("dataset_ready_after_load", job_id=job.id, label=job.label)
                self._begin_training_for_job(job)
            elif self._wait_for_job_ready(job):
                self._record_event("dataset_ready_after_wait", job_id=job.id, label=job.label)
                self._begin_training_for_job(job)
            else:
                self._record_event(
                    "dataset_waiting_for_poll",
                    job_id=job.id,
                    label=job.label,
                    trainer_state=self._trainer_state(),
                    has_trainer=self._has_trainer(),
                )
                self._start_load_poll_thread(job.id, self._run_token)
            return True
        except Exception as exc:
            self._active_job_id = None
            self._phase = "idle"
            job.status = STATUS_FAILED
            job.error = f"Unable to load dataset: {exc}"
            self._persist()
            self._record_event("job_load_failed", job_id=job.id, label=job.label, error=str(exc))
            self._set_status(job.error, error=True)
            self._release_frame_callback()
            return False

    def _wait_for_job_ready(self, job: QueueJob) -> bool:
        self._record_event("job_ready_wait_begin", job_id=job.id, label=job.label)
        deadline = time.monotonic() + LOAD_READY_TIMEOUT_SECONDS
        checks = 0
        while time.monotonic() < deadline:
            checks += 1
            if self._job_ready_to_start(job):
                self._record_event("job_ready_wait_satisfied", job_id=job.id, label=job.label, checks=checks)
                return True
            time.sleep(LOAD_READY_POLL_SECONDS)
        ready = self._job_ready_to_start(job)
        self._record_event("job_ready_wait_timeout", job_id=job.id, label=job.label, checks=checks, ready=ready)
        return ready

    def _start_load_poll_thread(self, job_id: str, run_token: int) -> None:
        self._record_event("load_poll_thread_started", job_id=job_id, run_token=run_token)
        def worker() -> None:
            while True:
                active_job = self.active_job
                if active_job is None or active_job.id != job_id or self._run_token != run_token:
                    self._record_event("load_poll_thread_stopped", job_id=job_id, run_token=run_token)
                    return
                if self._phase != "loading":
                    self._record_event("load_poll_thread_phase_exit", job_id=job_id, run_token=run_token, phase=self._phase)
                    return
                if self._job_ready_to_start(active_job):
                    self._record_event("dataset_ready_after_poll", job_id=active_job.id, label=active_job.label)
                    self._begin_training_for_job(active_job)
                    return
                time.sleep(LOAD_READY_POLL_SECONDS)

        threading.Thread(
            target=worker,
            name=f"{PLUGIN_ID}-load-poll-{run_token}",
            daemon=True,
        ).start()

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
        runtime_terminal_event = self._latest_runtime_terminal_training_event()
        if runtime_terminal_event is not None:
            runtime_sequence = int(runtime_terminal_event.get("sequence") or 0)
            self._runtime_event_consumed_seq = runtime_sequence
            self._record_event(
                "training_end_hook_runtime_terminal",
                job_id=(active_job.id if active_job is not None else ""),
                label=(active_job.label if active_job is not None else ""),
                runtime_event_type=str(runtime_terminal_event.get("type") or ""),
                runtime_event_sequence=runtime_sequence,
            )
            self._finalize_active_job(
                source="hook",
                decision_override=self._completion_decision_from_runtime_event(runtime_terminal_event),
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
        self._record_event(
            "training_ended",
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
        self._dataset_event_baseline_seq = 0
        self._runtime_event_baseline_seq = 0
        self._runtime_event_consumed_seq = 0
        self._persist()
        self._release_frame_callback()
        self._record_event(
            "job_finished",
            continue_queue=continue_queue,
            next_start_index=(0 if current_index is None else current_index + 1),
        )

        if continue_queue:
            start_index = 0 if current_index is None else current_index + 1
            next_index = find_next_runnable_job_index(self._jobs, start_index=start_index)
            if next_index is not None:
                self._start_job(self._jobs[next_index])
                return

        self._auto_run = False
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
        load_completed, dataset_event_sequence = self._dataset_load_completed_since_baseline()
        has_trainer = self._has_trainer()
        trainer_state = self._trainer_state()
        ready = dataset_ready and load_completed and is_trainer_ready_state(
            has_trainer=has_trainer,
            trainer_state=trainer_state,
        )
        self._record_event(
            "job_ready_check",
            job_id=job.id,
            label=job.label,
            dataset_ready=dataset_ready,
            dataset_load_completed=load_completed,
            dataset_event_baseline_seq=self._dataset_event_baseline_seq,
            dataset_event_sequence=dataset_event_sequence,
            has_trainer=has_trainer,
            trainer_state=trainer_state,
            ready=ready,
        )
        return ready

    def _apply_job_config(self, job: QueueJob) -> None:
        self._record_event("job_config_apply_begin", job_id=job.id, label=job.label)
        self._restore_preserved_models()
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
            self._runtime_event_baseline_seq = self._latest_runtime_training_event_sequence()
            self._runtime_event_consumed_seq = self._runtime_event_baseline_seq
            self._record_event(
                "start_training_begin",
                job_id=job.id,
                label=job.label,
                finish_reason_baseline=self._finish_reason_baseline,
                runtime_event_baseline_seq=self._runtime_event_baseline_seq,
            )
            lf.start_training()
            self._record_event(
                "start_training_returned",
                job_id=job.id,
                label=job.label,
            )
            self._persist()
            self._record_event(
                "training_started",
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

        desired_name = self._unique_scene_name(job.model_name)
        try:
            cached_model = self._capture_splat_node(source_name)
            if cached_model is None:
                return f"Unable to snapshot the trained model {source_name} for later restores."
            duplicated_name = scene.duplicate_node(source_name)
            renamed = scene.rename_node(duplicated_name, desired_name)
            if not renamed:
                return f"Duplicated {source_name}, but could not rename it to {desired_name}."
            cached_model["name"] = desired_name
            self._preserved_models[job.id] = cached_model
            self._record_event(
                "model_preserved",
                job_id=job.id,
                label=job.label,
                source_name=source_name,
                duplicated_name=duplicated_name,
                desired_name=desired_name,
            )
            return ""
        except Exception as exc:
            return f"Unable to duplicate the trained model: {exc}"

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

    def _restore_preserved_models(self) -> None:
        if not self._preserved_models:
            return
        scene = lf.get_scene()
        if scene is None:
            return

        restored_names: list[str] = []
        for payload in self._preserved_models.values():
            name = str(payload.get("name") or "").strip()
            if not name or scene.get_node(name) is not None:
                continue
            scene.add_splat(
                name,
                means=payload["means"].cuda(),
                sh0=payload["sh0"].cuda(),
                shN=payload["shN"].cuda(),
                scaling=payload["scaling"].cuda(),
                rotation=payload["rotation"].cuda(),
                opacity=payload["opacity"].cuda(),
            )
            restored_names.append(name)

        if restored_names:
            scene.notify_changed()
            self._record_event("preserved_models_restored", names=restored_names)

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

    def _mcp_resource_payload(self, uri: str) -> dict[str, Any]:
        try:
            payload = lf.mcp.read_resource(uri)
        except Exception as exc:
            self._record_event("runtime_resource_read_failed", uri=uri, error=str(exc))
            return {}

        if isinstance(payload, dict):
            text = payload.get("text")
            if isinstance(text, str):
                try:
                    return json.loads(text)
                except Exception:
                    return {}
            if "events" in payload or "jobs" in payload:
                return payload
            payload = payload.get("contents", payload)

        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        try:
                            return json.loads(text)
                        except Exception:
                            continue
                    if "events" in item or "jobs" in item:
                        return item
                elif isinstance(item, str):
                    try:
                        return json.loads(item)
                    except Exception:
                        continue
        return {}

    def _runtime_training_events(self) -> list[dict[str, Any]]:
        payload = self._mcp_resource_payload("lichtfeld://runtime/events")
        events = payload.get("events") or []
        return [event for event in events if isinstance(event, dict) and str(event.get("type") or "").startswith("training.")]

    def _runtime_events(self) -> list[dict[str, Any]]:
        payload = self._mcp_resource_payload("lichtfeld://runtime/events")
        events = payload.get("events") or []
        return [event for event in events if isinstance(event, dict)]

    def _latest_runtime_event_sequence_for(self, event_type: str) -> int:
        max_sequence = 0
        for event in self._runtime_events():
            if str(event.get("type") or "") != event_type:
                continue
            try:
                max_sequence = max(max_sequence, int(event.get("sequence") or 0))
            except Exception:
                continue
        return max_sequence

    def _latest_runtime_training_event_sequence(self) -> int:
        max_sequence = 0
        for event in self._runtime_training_events():
            try:
                max_sequence = max(max_sequence, int(event.get("sequence") or 0))
            except Exception:
                continue
        return max_sequence

    def _latest_runtime_terminal_training_event(self) -> dict[str, Any] | None:
        latest: dict[str, Any] | None = None
        for event in self._runtime_training_events():
            event_type = str(event.get("type") or "")
            if event_type not in {"training.completed", "training.stopped"}:
                continue
            try:
                sequence = int(event.get("sequence") or 0)
            except Exception:
                continue
            if sequence <= self._runtime_event_consumed_seq:
                continue
            if latest is None or sequence > int(latest.get("sequence") or 0):
                latest = event
        return latest

    def _completion_decision_from_runtime_event(self, event: dict[str, Any]) -> CompletionDecision:
        event_type = str(event.get("type") or "")
        data = event.get("data") or {}
        if not isinstance(data, dict):
            data = {}

        if event_type == "training.stopped":
            return CompletionDecision(status=STATUS_INTERRUPTED, continue_queue=False)

        success = bool(data.get("success"))
        user_stopped = bool(data.get("user_stopped"))
        error = str(data.get("error") or "").strip()
        iteration = int(data.get("iteration") or 0)
        active_job = self.active_job
        optimization = ((active_job.config_json or {}).get("optimization") or {}) if active_job is not None else {}
        expected_iterations = int(optimization.get("iterations") or 0)

        if not success or error:
            return CompletionDecision(
                status=STATUS_FAILED,
                continue_queue=self._auto_run,
                error=error or "Training failed.",
            )
        if user_stopped and self._stop_requested:
            return CompletionDecision(status=STATUS_INTERRUPTED, continue_queue=False)
        if user_stopped and expected_iterations and iteration < expected_iterations:
            return CompletionDecision(
                status=STATUS_INTERRUPTED,
                continue_queue=False,
                error=f"Training stopped unexpectedly at iteration {iteration} of {expected_iterations}.",
            )
        return CompletionDecision(status=STATUS_COMPLETED, continue_queue=self._auto_run)

    def _dataset_load_completed_since_baseline(self) -> tuple[bool, int]:
        latest_sequence = self._latest_runtime_event_sequence_for("dataset.load_completed")
        if self._dataset_event_baseline_seq == 0:
            return latest_sequence > 0, latest_sequence
        return latest_sequence > self._dataset_event_baseline_seq, latest_sequence

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

        runtime_terminal_event = self._latest_runtime_terminal_training_event()
        if runtime_terminal_event is not None:
            runtime_sequence = int(runtime_terminal_event.get("sequence") or 0)
            runtime_type = str(runtime_terminal_event.get("type") or "")
            runtime_data = runtime_terminal_event.get("data") or {}
            self._runtime_event_consumed_seq = runtime_sequence
            self._record_event(
                "runtime_training_terminal_detected",
                job_id=job.id,
                label=job.label,
                run_token=self._run_token,
                runtime_event_type=runtime_type,
                runtime_event_sequence=runtime_sequence,
                runtime_event_data=runtime_data,
                trainer_state=trainer_state,
                finish_reason=finish_reason,
                trainer_error=trainer_error,
            )
            decision = self._completion_decision_from_runtime_event(runtime_terminal_event)
            self._finalize_active_job(source="runtime", decision_override=decision)
            return

        finish_reason_changed = bool(finish_reason) and finish_reason != self._finish_reason_baseline
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
