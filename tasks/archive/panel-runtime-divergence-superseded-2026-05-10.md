# Panel Runtime Divergence Handoff

## Why This Exists
- Chat context is nearly exhausted.
- The next agent should start from this file, not from prior chat assumptions.

## Current User-Visible Problem
- Real dogfooding still fails.
- User loaded fresh jobs in the `LFS Queue` panel.
- Queue loaded the first job but did not start training.
- This is effectively the same user-visible failure the session started with.

## What Was Actually Verified
- A specific remote/debug-driven queue execution path was verified earlier:
  - job 1 loaded
  - job 1 trained
  - job 1 finalized
  - job 2 auto-started
  - job 2 trained/finalized
  - preserved models stayed visible in-scene during that same live session
- That means some progress was real, but it was not sufficient for the normal panel-run path and should not be treated as acceptance.

## Most Important New Suspicion
- The live app reportedly showed both module trees loaded:
  - `lfs_queue.*`
  - `lfs_plugins.lfs_queue.*`
- This is a serious red flag.
- Strong suspicion: panel actions and runtime callbacks may not be talking to the same controller singleton.
- If true, that explains why a remote/debug path could appear fixed while the panel-run path still stalls.

## Evidence
- Live editor module listing showed both:
  - `lfs_plugins.lfs_queue.queue_controller`
  - `lfs_queue.queue_controller`
- I also saw separate controller object ids when importing both module paths in the live Python runtime.
- Queue state persistence itself is expected:
  - queue jobs persist across restarts by design
- Preserved model nodes are intentionally session-scoped only:
  - they survive reloads within the current live session
  - they are not intended to persist across app restart

## Current Code State
- `queue_controller.py` now includes:
  - synchronous post-load readiness wait
  - controller-side training completion polling thread
  - in-memory preserved-model restore after dataset reload
- Unit tests still pass:
  - `python -m unittest discover -s tests -p "test_*.py"`

## What The Next Agent Needs To Do
1. Reproduce the failure from the real `LFS Queue` panel, not from a seeded remote/debug harness.
2. Inspect the stalled session directly:
   - visible panel state
   - app logs
   - `live_queue_debug_trace.jsonl`
3. Prove whether panel actions and runtime callbacks are using the same controller instance.
4. If not, fix module/controller canonicalization first.
   - Goal: one true controller singleton for panel and runtime callbacks.
5. Re-test the actual dogfooding flow:
   - load dataset normally
   - add 2 fresh jobs from panel
   - run all pending
   - verify load -> train -> finalize -> auto-advance

## Likely Fix Direction
- Stop treating this as an LFS runtime mystery first.
- Treat it as a live plugin runtime wiring problem until disproven.
- The next fix is likely around import/module identity and shared controller ownership, not around basic LFS load/train commands.

## Files To Read First
- `__init__.py`
- `panels/main_panel.py`
- `queue_controller.py`
- `tasks/done/2026-04-04-queue-execution-and-preservation.md`
- `tasks/planned/next-steps.md`
