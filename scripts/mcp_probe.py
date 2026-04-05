from __future__ import annotations

import json
from pathlib import Path
import traceback

import lichtfeld as lf


REPORT_PATH = Path(r"C:\Dev\3DGS\LFS-plugins\lfs-queue\mcp_probe_report.json")


def _safe_call(name: str, args=None):
    try:
        return {
            "ok": True,
            "result": lf.mcp.call_tool(name, args),
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": repr(exc),
        }


def _resolve_tool_name(preferred_name: str, available_tools: list[str]) -> str:
    if preferred_name in available_tools:
        return preferred_name
    plugin_name = f"plugin.{preferred_name}"
    if plugin_name in available_tools:
        return plugin_name
    for name in available_tools:
        if name.endswith(preferred_name):
            return name
    return preferred_name


report = {
    "script": str(Path(__file__)),
}

try:
    report["plugins_loaded"] = lf.plugins.list_loaded()
    report["all_tools"] = lf.mcp.list_tools()
    report["python_tools"] = lf.mcp.list_python_tools()
    resolved_names = {
        name: _resolve_tool_name(name, report["all_tools"])
        for name in (
            "queue.state",
            "queue.add_current",
            "queue.run_all",
            "queue.stop",
            "queue.debug_events",
        )
    }
    report["resolved_tool_names"] = resolved_names
    report["queue_tools_present"] = {
        name: (resolved_names[name] in report["all_tools"])
        for name in resolved_names
    }
    report["queue_state"] = _safe_call(resolved_names["queue.state"])
    report["queue_debug_events"] = _safe_call(resolved_names["queue.debug_events"], {"limit": 10})
    report["queue_add_current"] = _safe_call(resolved_names["queue.add_current"])
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
except Exception as exc:
    report["exception"] = repr(exc)
    report["traceback"] = traceback.format_exc()
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    raise
