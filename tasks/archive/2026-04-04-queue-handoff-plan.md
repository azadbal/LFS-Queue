# Queue Handoff Plan

## Purpose
- This file is a direct handoff for the next agent.
- Assume the next agent starts with a full context window but no reliable chat history.
- The goal is to resume `lfs_queue` work without reconstructing state from the conversation.

## Project State
- Repo: `C:\Dev\3DGS\LFS-plugins\lfs-queue`
- Plugin purpose: queue multiple training variants from the same dataset snapshot in LFS.
- Main files:
  - `queue_controller.py`
  - `queue_core.py`
  - `queue_mcp.py`
  - `panels/main_panel.py`
  - `tests/test_queue_core.py`

## What Is Implemented
- Queue jobs can be captured from the current dataset + config.
- Historical note: this handoff originally assumed queue persistence, but the intended product behavior is now session-scoped queue state only.
- MCP tools exist and are registered:
  - `plugin.queue.state`
  - `plugin.queue.add_current`
  - `plugin.queue.run_all`
  - `plugin.queue.stop`
  - `plugin.queue.debug_events`
- Debug-event ring buffer exists for queue lifecycle inspection.
- Queue load progression now uses a synchronous post-`lf.load_file(...)` readiness wait instead of depending on `on_frame`.
- Queue training completion now has a controller-side polling thread instead of depending on `on_frame` or `on_training_end` alone.
- Completed model splats are cached in memory and restored after the next dataset reload so prior queue results remain in-scene.
- Pure logic tests pass with:
  - `python -m unittest discover -s tests -p "test_*.py"`

## Important Code Facts
- Current job sequence in controller is:
  1. `lf.load_file(...)`
  2. `_apply_job_config(job)`
  3. `lf.start_training()`
- Relevant lines in `queue_controller.py`:
  - dataset load: `lf.load_file(...)`
  - config replay: `_apply_job_config(job)`
  - training start: `lf.start_training()`
- `_apply_job_config(job)` currently calls `lf.load_config_file(...)` and then applies mutable dataset overrides.

## What Was Verified
- The basic GUI MCP control path was verified earlier outside the queue:
  - dataset import works
  - training start works
  - runtime job/event APIs are usable and more trustworthy than `training.get_state`
- Earlier GUI log evidence showed queue order as:
  - job start
  - dataset ready
  - imported params
  - training started
- On April 4, 2026, a live two-job GUI MCP acceptance run passed on the resist house dataset:
  - job 1 loaded
  - job 1 trained
  - job 1 finalized
  - job 1 auto-advanced into job 2
  - job 2 loaded
  - job 2 trained
  - job 2 finalized
  - final scene contained `model 1`, `Model`, and `model 2`
- The decisive live event sequence now observed is:
  - `job_starting`
  - `dataset_ready_after_wait`
  - `dataset_ready`
  - `job_config_applied`
  - `training_started`
  - `training_start_observed`
  - `training_ended`
  - `model_preserved`
  - `job_finished`

## What Is Still Not Reliably Verified
- Longer queues and larger datasets have not been stress-tested.
- Preserved models are intentionally live-session-only queue artifacts; cross-session restoration is not a goal.
- There are still no direct controller unit tests for the live-load/training state machine.

## Current Resolved Issues
- The queue previously stalled after dataset import because the controller depended on `lf.on_frame(...)` to resume after `lf.load_file(...)`.
- The queue also previously stalled after training because it depended on `on_frame`/hooks to notice terminal trainer state.
- Preserved duplicated models were previously lost on the next dataset reload because scene duplication alone does not survive `lf.load_file(...)`.

## Recommended Next Steps
1. Add direct controller tests for the live queue state machine.
   - Cover synchronous load wait success.
   - Cover training terminal detection without hook delivery.
   - Cover preserved-model restore on second job start.
2. Re-run the two-job GUI MCP acceptance test after any controller change.
   - Keep using `plugin.queue.state`, `plugin.queue.debug_events`, and `scene.list_nodes`.
3. If config replay causes quality or parameter mismatches later, revisit `_apply_job_config(job)` separately.
   - That is no longer the primary blocker for queue execution.

## Suggested First Task For The Next Agent
- Start from regression protection, not from failure triage.
- Add controller-focused tests around the three verified fixes:
  - synchronous load readiness wait
  - training completion polling
  - preserved-model restoration
- Then rerun the same two-job GUI MCP flow to confirm no regression.

## Files To Read First
- `README.md`
- `tasks/planned/next-steps.md`
- `tasks/active/2026-03-29-queue-controller-py-worklog.md`
- `tasks/active/2026-03-29-lfs-queue-mcp-worklog.md`
- `queue_controller.py`
- `queue_core.py`
- `tests/test_queue_core.py`

## Notes About Prior Attempts
- The reliable verifier path is the GUI MCP HTTP server at `http://127.0.0.1:45677/mcp`.
- The basic MCP recipe flow (`scene.load_dataset -> training.start -> export`) was verified separately before queue debugging.
- The queue is now verified through the real app lifecycle rather than through `--python-script` launcher experiments.

## Stop Condition
- Only claim regressions or follow-up fixes after rerunning the same two-job GUI MCP acceptance flow.
