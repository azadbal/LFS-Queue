# Queue Execution And Preservation

## Status
- This file is a historical implementation summary, not the current acceptance status.
- The real panel dogfooding path later regressed or remained unresolved, so this file must not be treated as proof that the queue is fixed.
- Preserved models are intentionally session-scoped only. They survive dataset reloads during the current live queue run and are not intended to persist across app restarts.

## Verified Acceptance
- Verified in the real GUI through the MCP HTTP server at `http://127.0.0.1:45677/mcp`.
- Verified baseline LFS recipe flow from the docs:
  - `scene.load_dataset`
  - `training.start`
  - export flow
- Verified queue flow on the resist house dataset with two queued jobs:
  - job 1 loaded
  - job 1 trained
  - job 1 finalized
  - job 1 auto-advanced into job 2
  - job 2 loaded
  - job 2 trained
  - job 2 finalized
  - final scene contained `model 1`, `Model`, and `model 2`

## What Changed
- Replaced the fragile post-load `on_frame` dependency with a synchronous readiness wait after `lf.load_file(...)`.
- Added controller-side training completion polling so finalization does not depend solely on GUI hook delivery.
- Restored preserved models after dataset reload by caching completed splat tensors in memory for the current live session.

## Important Notes
- Queue state is intended to be session-scoped only.
- Preserved models do not need to persist across restarts and are not documented as a cross-session feature.
- `training.get_state` should not be used as the queue lifecycle gate; runtime jobs/events and queue debug events are the reliable sources.

## Current Follow-Ups
- Add controller-focused tests for:
  - synchronous load readiness wait
  - terminal training detection without hook delivery
  - preserved-model restore on second job start
- Stress-test longer queues and larger datasets.
- Revisit `_apply_job_config(job)` only if future replay mismatches appear.

## Historical Docs
- Detailed implementation notes and stale intermediate worklogs were moved to `tasks/done/archive/`.
