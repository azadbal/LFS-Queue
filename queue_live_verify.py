"""Test-only no-MCP live verification runner for LFS Queue."""

from __future__ import annotations

import json
import os
from pathlib import Path
import threading
import time
import traceback

import lichtfeld as lf

from .queue_controller import get_controller


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_DATASET = r"C:\Dev\3DGS\_example_datasets\COLMAP-ready-datasets\360-hobart-short\colmap"


def _env_path(name: str, default: str) -> str:
    return str(os.environ.get(name) or default)


def _write_report(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _wait_for_dataset(dataset_path: str, timeout_seconds: float, poll_seconds: float) -> bool:
    expected = Path(dataset_path).resolve()
    started = time.monotonic()
    while (time.monotonic() - started) < timeout_seconds:
        try:
            if lf.has_scene():
                dataset = lf.dataset_params()
                current = str(getattr(dataset, "data_path", "") or "").strip()
                if current and Path(current).resolve() == expected:
                    return True
        except Exception:
            pass
        time.sleep(poll_seconds)
    return False


def _wait_for_ready(timeout_seconds: float, poll_seconds: float) -> bool:
    started = time.monotonic()
    while (time.monotonic() - started) < timeout_seconds:
        try:
            state = str(lf.trainer_state() or "").strip().lower()
            if bool(lf.has_trainer()) and state in {"idle", "ready"}:
                return True
        except Exception:
            pass
        time.sleep(poll_seconds)
    return False


def _wait_for_queue(controller, timeout_seconds: float, poll_seconds: float) -> bool:
    started = time.monotonic()
    terminal = {"completed", "failed", "interrupted"}
    while (time.monotonic() - started) < timeout_seconds:
        jobs = list(controller.jobs)
        if jobs and not controller.is_running and all(job.status in terminal for job in jobs):
            return True
        time.sleep(poll_seconds)
    return False


def _serialize_jobs(controller) -> list[dict]:
    payload = []
    for job in controller.jobs:
        output_dir = Path(job.job_output_dir)
        payload.append(
            {
                "id": job.id,
                "label": job.label,
                "status": job.status,
                "error": job.error,
                "job_output_dir": job.job_output_dir,
                "output_files": sorted(str(path) for path in output_dir.glob("*") if path.is_file())
                if output_dir.exists()
                else [],
            }
        )
    return payload


def _run_autorun_verify() -> None:
    dataset_path = _env_path("LFS_QUEUE_VERIFY_DATASET", DEFAULT_DATASET)
    output_path = _env_path("LFS_QUEUE_VERIFY_OUTPUT", str(Path(dataset_path) / "output" / "lfs_queue_live_verify"))
    report_path = Path(_env_path("LFS_QUEUE_VERIFY_REPORT", str(REPO_ROOT / "queue_live_verify_report.json")))
    iterations = int(os.environ.get("LFS_QUEUE_VERIFY_ITERATIONS", "300"))
    timeout_seconds = float(os.environ.get("LFS_QUEUE_VERIFY_TIMEOUT_SECONDS", "180"))
    poll_seconds = float(os.environ.get("LFS_QUEUE_VERIFY_POLL_INTERVAL_SECONDS", "0.25"))
    startup_delay = float(os.environ.get("LFS_QUEUE_VERIFY_STARTUP_DELAY_SECONDS", "2.0"))

    report = {
        "dataset_path": dataset_path,
        "output_path": output_path,
        "iterations": iterations,
        "started_at": time.time(),
    }
    try:
        time.sleep(startup_delay)
        lf.log.info(f"lfs_queue autorun verify: loading {dataset_path}")
        lf.load_file(dataset_path, is_dataset=True, output_path=output_path)
        if not _wait_for_dataset(dataset_path, 60, poll_seconds):
            raise RuntimeError("Dataset did not become active after lf.load_file().")
        if not _wait_for_ready(60, poll_seconds):
            raise RuntimeError("LFS did not become training-ready after dataset load.")

        controller = get_controller()
        controller.clear_queue()

        optim = lf.optimization_params()
        optim.iterations = iterations
        report["iterations_job_1"] = int(optim.iterations)
        if not controller.add_current_job():
            raise RuntimeError(f"Failed to add job 1: {controller.status_message}")

        optim.iterations = iterations
        report["iterations_job_2"] = int(optim.iterations)
        if not controller.add_current_job():
            raise RuntimeError(f"Failed to add job 2: {controller.status_message}")

        report["jobs_seeded"] = _serialize_jobs(controller)
        report["run_all_pending"] = bool(controller.run_all_pending())
        report["status_after_run"] = controller.status_message
        report["queue_completed"] = _wait_for_queue(controller, timeout_seconds, poll_seconds)
        report["state_after"] = controller.export_state()
        report["jobs_after"] = _serialize_jobs(controller)
        report["debug_events_tail"] = controller.get_debug_events(180)
        report["finished_at"] = time.time()
        _write_report(report_path, report)
    except Exception as exc:
        report["exception"] = repr(exc)
        report["traceback"] = traceback.format_exc()
        try:
            _write_report(report_path, report)
        finally:
            raise
    finally:
        if os.environ.get("LFS_QUEUE_VERIFY_EXIT", "1") != "0":
            try:
                lf.force_exit()
            except Exception:
                pass


def start_autorun_verify() -> None:
    thread = threading.Thread(target=_run_autorun_verify, name="lfs-queue-autorun-verify", daemon=True)
    thread.start()
