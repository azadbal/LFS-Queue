from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time
import traceback

import lichtfeld as lf


REPORT_PATH = Path(r"C:\Dev\3DGS\LFS-plugins\lfs-queue\queue_smoke_report.json")
PLUGIN_INIT_PATH = Path(r"C:\Users\Azad\.lichtfeld\plugins\lfs_queue\__init__.py").resolve()
ITERATIONS = int(os.environ.get("LFS_QUEUE_SMOKE_ITERATIONS", "1000"))
TIMEOUT_SECONDS = float(os.environ.get("LFS_QUEUE_SMOKE_TIMEOUT_SECONDS", "180"))
POLL_INTERVAL_SECONDS = float(os.environ.get("LFS_QUEUE_SMOKE_POLL_INTERVAL_SECONDS", "0.1"))


def _write_report(payload: dict) -> None:
    REPORT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _find_plugin_module():
    for name, module in list(sys.modules.items()):
        module_file = getattr(module, "__file__", "")
        if not module_file:
            continue
        try:
            if Path(module_file).resolve() == PLUGIN_INIT_PATH:
                return name, module
        except Exception:
            continue
    return None, None


def _serialize_jobs(controller) -> list[dict]:
    return [
        {
            "id": job.id,
            "label": job.label,
            "status": job.status,
            "job_output_dir": job.job_output_dir,
            "error": job.error,
            "last_run_at": job.last_run_at,
            "completed_at": job.completed_at,
        }
        for job in controller.jobs
    ]


report = {
    "script": str(Path(__file__)),
    "iterations_override": ITERATIONS,
    "timeout_seconds": TIMEOUT_SECONDS,
}

try:
    report["plugins_loaded_before"] = list(lf.plugins.list_loaded())
    report["plugin_load_result"] = bool(lf.plugins.load("lfs_queue"))
    report["plugin_state"] = str(lf.plugins.get_state("lfs_queue"))
    report["plugin_error"] = str(lf.plugins.get_error("lfs_queue") or "")

    plugin_module_name, plugin_module = _find_plugin_module()
    report["plugin_module_name"] = plugin_module_name
    if plugin_module is None:
        raise RuntimeError(f"Unable to find loaded plugin module for {PLUGIN_INIT_PATH}")

    controller = plugin_module.get_controller()
    report["jobs_before"] = _serialize_jobs(controller)
    report["state_before"] = controller.export_state()

    for job in controller.jobs:
        optimization = job.config_json.setdefault("optimization", {})
        optimization["iterations"] = ITERATIONS
    controller._persist()

    report["run_all_pending"] = bool(controller.run_all_pending())
    report["status_after_run"] = controller.status_message

    started_at = time.monotonic()
    while controller.is_running and (time.monotonic() - started_at) < TIMEOUT_SECONDS:
        time.sleep(POLL_INTERVAL_SECONDS)

    report["timed_out"] = bool(controller.is_running)
    report["state_after"] = controller.export_state()
    report["jobs_after"] = _serialize_jobs(controller)
    report["debug_events_tail"] = controller.get_debug_events(80)
    _write_report(report)
except Exception as exc:
    report["exception"] = repr(exc)
    report["traceback"] = traceback.format_exc()
    _write_report(report)
    raise
