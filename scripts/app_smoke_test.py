from __future__ import annotations

import json
from pathlib import Path
import sys
import traceback

import lichtfeld as lf


REPORT_PATH = Path(r"C:\Dev\3DGS\LFS-plugins\lfs-queue\smoke_test_report.json")
PLUGIN_INIT_PATH = Path(r"C:\Users\Azad\.lichtfeld\plugins\lfs_queue\__init__.py").resolve()


def _safe_repr(value):
    try:
        return repr(value)
    except Exception as exc:
        return f"<repr failed: {exc}>"


def _write_report(payload):
    REPORT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


report = {
    "script": str(Path(__file__)),
}

try:
    report["plugin_discover"] = _safe_repr(lf.plugins.discover())
    report["plugins_loaded_before"] = _safe_repr(lf.plugins.list_loaded())
    report["plugin_load_result"] = bool(lf.plugins.load("lfs_queue"))
    report["plugin_state"] = _safe_repr(lf.plugins.get_state("lfs_queue"))
    report["plugin_error"] = _safe_repr(lf.plugins.get_error("lfs_queue"))

    plugin_module_name = None
    plugin_module = None
    for name, module in list(sys.modules.items()):
        module_file = getattr(module, "__file__", "")
        if not module_file:
            continue
        try:
            if Path(module_file).resolve() == PLUGIN_INIT_PATH:
                plugin_module_name = name
                plugin_module = module
                break
        except Exception:
            continue

    report["plugin_module_name"] = plugin_module_name
    if plugin_module is None:
        raise RuntimeError(f"Unable to find loaded plugin module for {PLUGIN_INIT_PATH}")

    controller = plugin_module.get_controller()
    report["jobs_before"] = len(controller.jobs)

    optim = lf.optimization_params()
    report["iterations_before"] = int(optim.iterations)
    optim.iterations = 1000
    report["iterations_after"] = int(optim.iterations)

    added = controller.add_current_job()
    report["add_current_job"] = bool(added)
    report["status_message"] = controller.status_message
    report["jobs_after"] = len(controller.jobs)

    if controller.jobs:
        last_job = controller.jobs[-1]
        report["last_job"] = {
            "id": last_job.id,
            "label": last_job.label,
            "status": last_job.status,
            "dataset_path": last_job.dataset_path,
            "base_output_dir": last_job.base_output_dir,
            "job_output_dir": last_job.job_output_dir,
        }

    _write_report(report)
except Exception as exc:
    report["exception"] = repr(exc)
    report["traceback"] = traceback.format_exc()
    _write_report(report)
    raise
