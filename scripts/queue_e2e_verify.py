from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

import lichtfeld as lf


REPORT_PATH = Path(r"C:\Dev\3DGS\LFS-plugins\lfs-queue\queue_e2e_verify_report.json")
TIMEOUT_SECONDS = 180.0
POLL_INTERVAL_SECONDS = 0.1
DATASET_PATH = r"C:\Dev\3DGS\_example_datasets\COLMAP-ready-datasets\resist house\colmap"
OUTPUT_PATH = r"C:\Dev\3DGS\_example_datasets\COLMAP-ready-datasets\resist house\colmap\output\lfs_queue_e2e_verify"


def _write_report(payload: dict) -> None:
    REPORT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _serialize_jobs(controller) -> list[dict]:
    return [
        {
            "id": job.id,
            "label": job.label,
            "status": job.status,
            "error": job.error,
            "job_output_dir": job.job_output_dir,
            "completed_at": job.completed_at,
        }
        for job in controller.jobs
    ]


def _find_plugin_module():
    plugin_init_path = Path(r"C:\Users\Azad\.lichtfeld\plugins\lfs_queue\__init__.py").resolve()
    for name, module in list(sys.modules.items()):
        module_file = getattr(module, "__file__", "")
        if not module_file:
            continue
        try:
            if Path(module_file).resolve() == plugin_init_path:
                return name, module
        except Exception:
            continue
    return None, None


def _wait_for_loaded_dataset(timeout_seconds: float) -> bool:
    started = time.monotonic()
    while (time.monotonic() - started) < timeout_seconds:
        if lf.has_scene():
            dataset = lf.dataset_params()
            data_path = str(getattr(dataset, "data_path", "") or "").strip()
            if data_path:
                return True
        time.sleep(POLL_INTERVAL_SECONDS)
    return False


report = {
    "script": str(Path(__file__)),
    "started_at": time.time(),
}

try:
    lf.load_file(DATASET_PATH, is_dataset=True, output_path=OUTPUT_PATH)
    if not _wait_for_loaded_dataset(60.0):
        raise RuntimeError("Dataset did not become ready after lf.load_file().")

    plugin_loaded_before = list(lf.plugins.list_loaded())
    plugin_load_result = bool(lf.plugins.load("lfs_queue"))
    plugin_error = str(lf.plugins.get_error("lfs_queue") or "")

    report["plugins_loaded_before"] = plugin_loaded_before
    report["plugin_load_result"] = plugin_load_result
    report["plugin_error"] = plugin_error

    plugin_module_name, plugin_module = _find_plugin_module()
    report["plugin_module_name"] = plugin_module_name
    if plugin_module is None:
        raise RuntimeError("Unable to find loaded plugin module for lfs_queue.")

    controller = plugin_module.get_controller()
    report["dataset_path"] = str(getattr(lf.dataset_params(), "data_path", "") or "")
    report["output_path"] = str(getattr(lf.dataset_params(), "output_path", "") or "")

    controller._jobs = []
    controller._persist()

    optim = lf.optimization_params()
    optim.iterations = 30
    optim.strategy = "igs+"
    optim.max_cap = 4000000
    optim.init_opacity = 0.1
    controller.add_current_job()

    optim.iterations = 30
    optim.strategy = "mcmc"
    optim.max_cap = 1000000
    optim.init_opacity = 0.5
    controller.add_current_job()

    report["jobs_seeded"] = _serialize_jobs(controller)

    report["run_all_pending"] = bool(controller.run_all_pending())
    report["status_after_run"] = controller.status_message

    started = time.monotonic()
    while controller.is_running and (time.monotonic() - started) < TIMEOUT_SECONDS:
        time.sleep(POLL_INTERVAL_SECONDS)

    report["timed_out"] = bool(controller.is_running)
    report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    report["state_after"] = controller.export_state()
    report["jobs_after"] = _serialize_jobs(controller)
    report["debug_events_tail"] = controller.get_debug_events(120)
    report["finished_at"] = time.time()
    _write_report(report)
except Exception as exc:
    report["exception"] = repr(exc)
    report["traceback"] = traceback.format_exc()
    _write_report(report)
    raise
