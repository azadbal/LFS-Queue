# Fix Panel Queue Run Flow

- Status: ready for review
- Last updated: 2026-04-04 16:52 local

## User ask

- Make `lfs_queue` work for the real LFS Stable user flow.
- Queue entries must be session-only, not persisted across restarts.
- Fix it and verify it ourselves, not by handing verification back to the user.

## Current objective

- Make the full panel flow work:
  - fresh LFS launch
  - empty queue
  - load dataset manually in LFS
  - add 2 fresh jobs from the `LFS Queue` panel
  - run all pending
  - job 1 loads, trains, finalizes
  - job 2 auto-starts, trains, finalizes

## Why this task exists

- The plugin still fails at its core purpose. The panel can queue jobs, but the live queue runtime still does not reliably execute the saved jobs from start to finish.
- The product contract is simple: save what is currently set in LFS when `Add Current` is clicked, then later load, apply those settings, train, finish, and continue.

## Relevant context / known facts

- Ground truth:
  - queue is not supposed to persist across restarts
  - MCP-only success is not acceptance
  - the real acceptance path is the panel flow in a live LFS session
- The user sees the yellow `HI` marker/button, so LFS is loading this repo's current code.
- Plugin path in LFS is a junction to this repo:
  - `C:\Users\Azad\.lichtfeld\plugins\lfs_queue`
- `queue_controller.py` is the real problem area.
- `queue_core` tests passing is not evidence for this bug.

## Constraints / assumptions

- Keep work centered on `queue_controller.py` and the real panel/runtime path.
- Do not use the `update-docs` skill.
- Avoid broad side work unless it directly supports fixing the live queue path.
- Verification must come from a live queue run, not only unit tests or seeded-controller scripts.

## What has already been done

- Added loud panel marker in `panels/main_panel.py`:
  - yellow text `HI - LFS QUEUE LIVE CODE`
  - big yellow `HI` button
- Made queue session-only:
  - controller discards persisted jobs
  - `_persist()` is a no-op
  - `settings.json` queue jobs were cleared
  - panel has `Clear Queue`
- Added live trace artifact:
  - `live_queue_debug_trace.jsonl`
- Fixed stale verifier scripts to stop using dead `on_frame(...)` calls and ambiguous module imports.
- Corrected false persistence language in `README.md` and stale task docs.
- Fixed the real async reload race:
  - the queue now waits for a fresh `dataset.load_completed` runtime event after each `lf.load_file(...)`
  - it no longer treats the previous scene/trainer as proof that the new job is ready
- Fixed stale completion handling:
  - a late `on_training_end` callback from the previous job no longer completes the next job
  - hook-based completion is ignored unless there is a fresh terminal runtime event or a real terminal trainer state
- Added one regression test in `tests/test_queue_core.py` to keep non-terminal running state from being treated as a finish signal.

## Current repo/code/file state

- `queue_controller.py` now emits detailed live trace events around:
  - add current
  - dataset snapshot capture
  - load start/return
  - readiness checks
  - config apply
  - validation
  - before/after `lf.start_training()`
  - training callbacks
  - training polling
- Replay logic was moved away from `lf.load_config_file(...)` and into explicit optimization replay.
- Queue progression is now keyed to LFS runtime events:
  - `dataset.load_completed` gates start after reload
  - `training.completed` / `training.stopped` are treated as authoritative terminal signals
- `tasks/active/current-task.md` is the canonical handoff file.

## Open questions / uncertainties

- The strongest verified path is still the live app through MCP tools hitting the same plugin/controller methods as the panel:
  - `plugin.queue.add_current`
  - `plugin.queue.run_all`
- A literal manual panel click-through should still be run after these last two controller fixes.

## Next recommended actions

1. Do one manual panel smoke check in LFS Stable with two identical jobs from the panel.
2. If that passes, move this task out of active work and archive the handoff.
3. If it fails, compare the manual run trace against the verified `codex_post_patch_duplicate_verify_report.json` run before changing code again.

## Risks / blockers

- The replay map is now explicit for this LFS build's supported `OptimizationParams` API, but future host changes could require keeping that map in sync.
- Until a manual panel smoke check also passes, there is still a narrow UI-path residual risk even though the live plugin/controller path now completes two queued jobs autonomously.

## Important files / paths / commands / artifacts

- `C:\Dev\3DGS\LFS-plugins\lfs-queue\queue_controller.py`: queue runtime and replay logic
- `C:\Dev\3DGS\LFS-plugins\lfs-queue\panels\main_panel.py`: panel path, yellow live-code marker, `Clear Queue`
- `C:\Dev\3DGS\LFS-plugins\lfs-queue\live_queue_debug_trace.jsonl`: authoritative trace from the real panel run
- `C:\Dev\3DGS\LFS-plugins\lfs-queue\codex_post_patch_duplicate_verify_report.json`: fresh live verification showing two identical queued jobs completing in sequence
- `C:\Dev\3DGS\LFS-plugins\lfs-queue\codex_fresh_verify_app.log`: host-side log for the same verification run
- `C:\Users\Azad\Documents\_apps\LichtFeld_Studio\LFS_Stable\bin\lichtfeld\__init__.pyi`: exact `OptimizationParams` surface for this build
- `python -m unittest discover -s tests -p "test_*.py"`: sanity only, not acceptance

## Last updated

Self-verified in a fresh live LFS Stable session after the latest controller fixes: loaded the dataset, added two identical jobs, ran the queue through the live app MCP path, and both jobs completed in sequence. The two key fixes were waiting for a fresh `dataset.load_completed` event before starting training and rejecting stale non-terminal `on_training_end` callbacks.
