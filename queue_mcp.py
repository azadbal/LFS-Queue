"""MCP tools for driving and inspecting the queue plugin from LFS."""

from __future__ import annotations

from typing import Any

import lichtfeld as lf

from .queue_controller import get_controller


TOOL_QUEUE_STATE = "queue.state"
TOOL_QUEUE_ADD_CURRENT = "queue.add_current"
TOOL_QUEUE_RUN_ALL = "queue.run_all"
TOOL_QUEUE_STOP = "queue.stop"
TOOL_QUEUE_DEBUG_EVENTS = "queue.debug_events"
TOOL_QUEUE_CLEAR = "queue.clear"

_REGISTERED_TOOL_NAMES: tuple[str, ...] = (
    TOOL_QUEUE_STATE,
    TOOL_QUEUE_ADD_CURRENT,
    TOOL_QUEUE_RUN_ALL,
    TOOL_QUEUE_STOP,
    TOOL_QUEUE_DEBUG_EVENTS,
    TOOL_QUEUE_CLEAR,
)


def register_tools() -> None:
    _safe_unregister_all()
    lf.mcp.register_tool(
        _queue_state,
        name=TOOL_QUEUE_STATE,
        description="Return the current lfs_queue state including jobs, phase, and status message.",
    )
    lf.mcp.register_tool(
        _queue_add_current,
        name=TOOL_QUEUE_ADD_CURRENT,
        description="Snapshot the current dataset and training settings into a new queue job.",
    )
    lf.mcp.register_tool(
        _queue_run_all,
        name=TOOL_QUEUE_RUN_ALL,
        description="Run all pending, failed, or interrupted queue jobs.",
    )
    lf.mcp.register_tool(
        _queue_stop,
        name=TOOL_QUEUE_STOP,
        description="Stop the currently running queue job or disarm queue auto-run.",
    )
    lf.mcp.register_tool(
        _queue_debug_events,
        name=TOOL_QUEUE_DEBUG_EVENTS,
        description="Return recent lfs_queue debug events for diagnosis.",
    )
    lf.mcp.register_tool(
        _queue_clear,
        name=TOOL_QUEUE_CLEAR,
        description="Clear all queued jobs in the current session.",
    )


def unregister_tools() -> None:
    _safe_unregister_all()


def _safe_unregister_all() -> None:
    for name in _REGISTERED_TOOL_NAMES:
        try:
            lf.mcp.unregister_tool(name)
        except Exception:
            pass


def _queue_state() -> dict[str, Any]:
    controller = get_controller()
    return controller.export_state()


def _queue_add_current() -> dict[str, Any]:
    controller = get_controller()
    ok = controller.add_current_job()
    return {
        "ok": ok,
        "status_message": controller.status_message,
        "state": controller.export_state(),
    }


def _queue_run_all() -> dict[str, Any]:
    controller = get_controller()
    ok = controller.run_all_pending()
    return {
        "ok": ok,
        "status_message": controller.status_message,
        "state": controller.export_state(),
    }


def _queue_stop() -> dict[str, Any]:
    controller = get_controller()
    ok = controller.stop_queue()
    return {
        "ok": ok,
        "status_message": controller.status_message,
        "state": controller.export_state(),
    }


def _queue_debug_events(limit: int = 50) -> dict[str, Any]:
    controller = get_controller()
    try:
        normalized_limit = int(limit)
    except (TypeError, ValueError):
        normalized_limit = 50
    events = controller.get_debug_events(normalized_limit)
    return {
        "count": len(events),
        "events": events,
    }


def _queue_clear() -> dict[str, Any]:
    controller = get_controller()
    removed = controller.clear_queue()
    return {
        "ok": True,
        "removed": removed,
        "status_message": controller.status_message,
        "state": controller.export_state(),
    }
