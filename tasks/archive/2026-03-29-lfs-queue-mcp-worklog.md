# lfs-queue-mcp Worklog

## Scope
- Feature: `lfs-queue-mcp`
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
- Verified the minimal GUI MCP control path end-to-end: scene.load_dataset -> runtime.job.wait(import.dataset) -> training.start -> runtime.job.wait(training.main active) -> editor.run(lf.stop_training()).
- On the resist house COLMAP dataset, import completed successfully with 341 images and 362287 points; training entered a real running state and progressed to iteration 456 before a clean user-stop request.
- Decision: For queue execution and queue testing, runtime.job.wait(training.main/import.dataset) and runtime.events.tail are the authoritative state sources; training.get_state stayed zeroed during a real active training run and should not be used as the queue lifecycle gate.
- Decision: lichtfeld://render/current is implemented as a real GUI viewport capture resource, but in the current LFS build it reproducibly crashes LichtFeld-Studio.exe on this machine when called over MCP after initialization.
- Decision: The shutter sound the user hears is consistent with the viewport capture path being invoked; the observed failure is app crash after capture request, not absence of a render-capture feature.
- Validated that lichtfeld://render/camera/0 does not crash the app; with no loaded model it returns a clean MCP error 'No model to render'.
- Decision: The current crash is specific to lichtfeld://render/current live viewport capture, not to MCP image resources in general.
- Source review shows lichtfeld://render/camera/<index> uses scene.getAllCameras()[camera_index] and renders the current training model or first visible splat node from that camera.
- Decision: Inference: render/camera/<index> is the safer MCP path for dataset-camera renders, while render/current is the live interactive viewport capture path and is the one crashing in this build.
