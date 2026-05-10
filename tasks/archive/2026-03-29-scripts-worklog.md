# scripts Worklog

## Scope
- Feature: `scripts`
- Purpose: track implementation details, decisions, and follow-ups when no prior task doc existed.

## Decisions
- Added plugin MCP tools for queue state, add-current, run-all, stop, and debug events via queue_mcp.py and plugin load/unload registration.
- Added controller runtime-state export and debug-event ring buffer so queue behavior can be inspected remotely instead of only through raw logs.
- Added scripts/mcp_probe.py and validated both headless and GUI MCP access; the live GUI MCP HTTP endpoint can call plugin.queue.state and plugin.queue.run_all after initialize plus notifications/initialized.
- Changed queue start flow to be sync-first after load_file(), with on_frame only as a fallback when the dataset is not immediately ready.
- Decision: LFS auto-prefixes Python MCP tools under plugin.*, so the practical tool names are plugin.queue.state, plugin.queue.add_current, plugin.queue.run_all, plugin.queue.stop, and plugin.queue.debug_events.
- Decision: The GUI reload stall was caused by waiting on on_frame after a synchronous load_file() path; immediate post-load readiness handling is now the primary path.
- Decision: Current known issue: GUI training completion is logged by LFS, but the queue training-end callback path is not yet finalizing jobs or advancing to the next queued model.
- Changed: `__init__.py`
- Changed: `queue_controller.py`
- Changed: `queue_core.py`
- Changed: `queue_mcp.py`
- Changed: `README.md`
- Changed: `scripts/mcp_probe.py`

## Next Steps
- Keep this file updated as implementation evolves.

## 2026-03-29
- Added plugin MCP tools for queue state, add-current, run-all, stop, and debug events via queue_mcp.py and plugin load/unload registration.
- Added controller runtime-state export and debug-event ring buffer so queue behavior can be inspected remotely instead of only through raw logs.
- Added scripts/mcp_probe.py and validated both headless and GUI MCP access; the live GUI MCP HTTP endpoint can call plugin.queue.state and plugin.queue.run_all after initialize plus notifications/initialized.
- Changed queue start flow to be sync-first after load_file(), with on_frame only as a fallback when the dataset is not immediately ready.
- Decision: LFS auto-prefixes Python MCP tools under plugin.*, so the practical tool names are plugin.queue.state, plugin.queue.add_current, plugin.queue.run_all, plugin.queue.stop, and plugin.queue.debug_events.
- Decision: The GUI reload stall was caused by waiting on on_frame after a synchronous load_file() path; immediate post-load readiness handling is now the primary path.
- Decision: Current known issue: GUI training completion is logged by LFS, but the queue training-end callback path is not yet finalizing jobs or advancing to the next queued model.
- Changed: `__init__.py`
- Changed: `queue_controller.py`
- Changed: `queue_core.py`
- Changed: `queue_mcp.py`
- Changed: `README.md`
- Changed: `scripts/mcp_probe.py`
