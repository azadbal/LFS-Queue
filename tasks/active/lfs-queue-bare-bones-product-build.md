# LFS Queue Bare-Bones Product Build

- Status: active
- Last updated: 2026-05-10 queue artifact cleanup checkpoint

## User ask

- Build the actual LFS queue plugin first, before shipping polish or analytics.
- For whatever LFS state is already ready to train, let the user change training settings, click `Add to Queue`, change settings again, and add more jobs.
- The queue should mirror the native `Start Training` readiness: if `Start Training` is unavailable, adding to the queue should be unavailable too.
- Run queued jobs one after another and keep completed splats loaded in the same LFS session for comparison.
- Use this named active task plus `docs/00-product-requirements.md` as the handoff source of truth.

## Current objective

- Deliver a bare-bones queue:
  - add jobs from the current training-ready LFS state/settings
  - use simple incrementing names like `model-1`, `model-2`
  - run jobs sequentially
  - preserve or reload each completed `.ply` in-scene
  - keep queue state session-only
- Add plugin-owned trace/log evidence so an agent can validate a user-driven GUI run afterward without MCP.
- Supersede older debugging plans that centered on dataset reload, MCP tooling, or remote/debug harnesses.

## Why this task exists

- The plugin is meant to make repeated LFS training experiments practical: set settings, enqueue, set different settings, enqueue again, then compare the resulting splats.
- It is not meant to import or prepare datasets. LFS must already be in a state where training can start.
- Shipping/installability and experiment metrics matter, but they come after the core queue works reliably.

## Relevant context / known facts

- Ground truth:
  - queue is not supposed to persist across LFS restarts
  - native `Start Training` readiness is the gate for whether `Add to Queue` should be available
  - MCP is not an accepted dependency, implementation path, or verification path
  - the real acceptance path is the panel flow in a live LFS session
- Concrete local dogfood dataset for agent-driven testing:
  - Fixture root: `C:\Dev\3DGS\_example_datasets\COLMAP-ready-datasets`
  - Use a scene subfolder's nested `colmap` folder.
  - Currently discovered fixtures:
    - `C:\Dev\3DGS\_example_datasets\COLMAP-ready-datasets\360-hobart-short\colmap`
    - `C:\Dev\3DGS\_example_datasets\COLMAP-ready-datasets\ferry building drone\colmap`
  - These paths are for verification setup only. The panel plugin itself should not own dataset import/loading as part of queue behavior.
- The temporary yellow `HI` marker/button has been removed from the panel code.
- Plugin path in LFS is a junction to this repo:
  - `C:\Users\Azad\.lichtfeld\plugins\lfs_queue`
- `queue_controller.py` is the real problem area.
- `queue_core` tests passing is not evidence for this bug.

## Constraints / assumptions

- Keep work centered on the real UI/panel/runtime path.
- Do not use the `update-docs` skill.
- Avoid broad side work unless it directly supports fixing the live queue path.
- Verification must come from a live queue run, not only unit tests or seeded-controller scripts.
- Do not use MCP as the queue verifier. Historical MCP notes are not acceptance criteria.
- Do not prioritize stats, logging dashboards, PSNR/SSIM, marketplace packaging, or rich naming until the bare queue works.
- Do not build dataset import/loading into this plugin.
- The plugin should write enough local trace evidence that a future agent can inspect what happened after the user manually dogfoods the GUI.

## What has already been done

- Product direction was clarified and written into:
  - `docs/00-product-requirements.md`
  - `tasks/todo.md`
- Older active divergence handoff was archived to:
  - `tasks/archive/panel-runtime-divergence-superseded-2026-05-10.md`
- Removed the temporary loud panel marker from `panels/main_panel.py`.
- Made queue session-only:
  - controller discards persisted jobs
  - `_persist()` is a no-op
  - `settings.json` queue jobs were cleared
  - panel has `Clear Queue`
- Added live trace artifact:
  - `live_queue_debug_trace.jsonl`
- Fixed stale verifier scripts to stop using dead `on_frame(...)` calls and ambiguous module imports.
- Corrected false persistence language in `README.md` and stale task docs.
- Removed the dataset-reload execution path from the active controller:
  - queued jobs now assume the same active LFS dataset
  - the controller no longer calls `lf.load_file(...)` to run queue jobs
- User live-run feedback showed `DatasetParams.output_path` is read-only in LFS Python:
  - previous attempt to set job output dir before training failed with `property of 'DatasetParams' object has no setter`
  - LFS saved to the base dataset output during training
- Patched output handling:
  - completed jobs save the live trained `Model` splat to `<job_output_dir>\<model-name>.ply` using `lf.io.save_ply(...)`
  - the queue requests `lf.reset_training()` before starting the next job
  - the queue waits for native training readiness before auto-advancing
  - after the queue finishes, completed `.ply` outputs are loaded back with `lf.load_file(...)` for comparison
- Added initial no-MCP CLI helper:
  - `queue_cli.py`
  - `scripts/queue_cli.py`
  - normal Python can run `python .\scripts\queue_cli.py fixtures`
  - LFS Python/script context can call `state`, `add-current`, `run-all`, and `clear`
- Fixed stale completion handling:
  - a late `on_training_end` callback from the previous job no longer completes the next job
  - hook-based completion is ignored unless there is a fresh terminal runtime event or a real terminal trainer state
- Added one regression test in `tests/test_queue_core.py` to keep non-terminal running state from being treated as a finish signal.
- Initialized git for this checkout, added a conservative `.gitignore`, committed the current plugin state, and pushed it to:
  - `https://github.com/azadbal/LFS-Queue`
- Verified repo hygiene before push:
  - no `queue/` outputs
  - no `.ply`
  - no raw images
  - no generated logs or JSON report artifacts were staged

## Current repo/code/file state

- Current code now has the first PRD-aligned implementation pass:
  - `__init__.py` no longer imports/registers `queue_mcp`
  - `__init__.py` has an env-gated live verifier autorun hook for tests only
  - `queue_controller.py` no longer reads MCP runtime resources in the active path
  - `queue_controller.py` no longer reloads datasets with `lf.load_file(...)`
  - job names now increment as `model-1`, `model-2`, etc.
  - panel button is now `Add to Queue` and is disabled unless native training readiness is true
  - completed job checkpoints are moved into `queue\<job>\checkpoints\checkpoint.resume`
  - ambiguous native top-level `splat_*.ply` files are deleted after the named queue PLY is saved
  - the live final training model is removed before completed queue outputs are reloaded
- Latest live run against LFS Nightly succeeded:
  - launched `C:\Users\Azad\Documents\_apps\LichtFeld_Studio\LFS_Nightly\bin\LichtFeld-Studio.exe`
  - used fixture `C:\Dev\3DGS\_example_datasets\COLMAP-ready-datasets\360-hobart-short\colmap`
  - set verifier iterations to `300`
  - queued two jobs, `model-1` and `model-2`
  - both jobs reached `completed`
  - final queue state was `phase=idle`, `is_running=False`, `trainer_state=idle`
  - both outputs were written and then loaded by the PLY loader
- User verified the run and observed the expected queue outputs, plus one duplicate live `Trained Model` from the final native LFS training state.
- User also observed top-level native LFS artifacts in the base output folder:
  - `splat_300.ply`
  - `checkpoints\checkpoint.resume`
- `queue_controller.py` now emits detailed live trace events around:
  - add attempts
  - dataset snapshot capture
  - readiness checks
  - config apply
  - validation
  - before/after `lf.start_training()`
  - training callbacks
  - training polling
- Replay logic was moved away from `lf.load_config_file(...)` and into explicit optimization replay.
- Queue progression is now keyed to LFS trainer hooks/polling, not MCP runtime events.
- Latest local validation:
  - `python -m unittest discover -s tests -p "test_*.py"` passes, 14 tests
  - `python -m py_compile __init__.py queue_core.py queue_controller.py panels\main_panel.py tests\test_queue_controller_no_mcp.py tests\test_queue_core.py` passed in the implementation pass
  - `python .\scripts\queue_cli.py fixtures` discovers the two COLMAP-ready fixtures listed above
  - Nightly live verifier wrote `queue_live_verify_report.json` with `queue_completed=True`
  - app log confirms both completed output PLYs loaded successfully:
    - `model-1.ply`: 23477 Gaussians, SH degree 3
    - `model-2.ply`: 23477 Gaussians, SH degree 3
  - artifact cleanup verifier passed in `output\lfs_queue_artifact_verify`:
    - top-level `splat_*.ply` count: 0
    - top-level checkpoint file count: 0
    - `queue\model-1\model-1.ply` and `queue\model-2\model-2.ply` exist
    - `queue\model-1\checkpoints\checkpoint.resume` and `queue\model-2\checkpoints\checkpoint.resume` exist
    - trace contains `queue.live_training_model_removed`
- Git working tree still has unstaged/untracked project changes from this work and earlier docs/task edits; no commit has been made for the current implementation pass.
- `.gitignore` now excludes generated queue artifacts and media:
  - `queue/`
  - `*.ply`
  - image formats
  - logs / jsonl / report JSONs
- `tasks/todo.md` now holds the next requested feature backlog for UX and export improvements.
- `tasks/active/lfs-queue-bare-bones-product-build.md` is the canonical handoff file.
- `docs/00-product-requirements.md` defines the product direction and V1 acceptance criteria.

## Open questions / uncertainties

- The current code has prior queue/runtime work, but the latest accepted product objective is simpler: prove the bare real-panel queue flow first.
- It is still uncertain whether the current panel flow and runtime callbacks share one controller instance in live LFS.
- Exact LFS API path for checking native training readiness and preserving/reloading completed `.ply` outputs should be confirmed from the host repo and real GUI behavior.
- Exact safest "next tick" or deferred-start mechanism should be confirmed so job 2 starts only after LFS has finished finalizing job 1.

## Next recommended actions

1. Re-run Nightly live verifier and confirm no duplicate live `Trained Model` remains after queue output reload.
2. Confirm the base output has no top-level `splat_*.ply` after queue completion.
3. Confirm each completed job has `queue\<job>\checkpoints\checkpoint.resume`.
4. Keep strengthening the no-MCP verifier into a reusable CLI/scriptable regression command.
5. Test with one changed setting between queued jobs so output comparison reflects distinct captured settings.

## Verification and back pressure plan

- Unit-test queue logic with a fake LFS adapter:
  - add is blocked when `has_trainer=False`
  - add is blocked when trainer state is not `idle` or `ready`
  - add is allowed when native training would be available
  - captured jobs keep independent settings snapshots
  - generated names are `model-1`, `model-2`, `model-3`
  - training-end callback completes job 1 and schedules job 2
  - failed job is marked failed and the queue advances when auto-run is enabled
  - controller starts session-empty even if old settings contain jobs
  - active plugin path does not register or call MCP
- Real GUI verification should use only:
  - visible LFS panel behavior
  - local app logs
  - plugin trace files such as `live_queue_debug_trace.jsonl`
  - generated output files
  - visible scene/model state after the run
- Required trace events should include:
  - `queue.add_attempt`
  - `queue.add_blocked_not_ready`
  - `queue.job_added`
  - `queue.job_started`
  - `queue.training_started`
  - `queue.training_finished`
  - `queue.model_preserved` or `queue.output_loaded`
  - `queue.job_failed`
  - `queue.job_advance`
  - `queue.completed`
- Back pressure rules:
  - only one active job at a time
  - disable queue start/run controls while a job is active
  - do not start the next job directly inside a training-end callback
  - enter a `finalizing` phase after training ends
  - start the next job only after preservation/export cleanup is complete and LFS is back in a safe state
  - add timeouts for "training requested but never started" and "finalization never completed"

## Risks / blockers

- The replay map is now explicit for this LFS build's supported `OptimizationParams` API, but future host changes could require keeping that map in sync.
- Until the real panel flow passes, previous remote/debug verification should not be treated as acceptance.
- The project may need a small host-side UI hook if the plugin cannot cleanly add `Add to Queue` near the native training controls from plugin code alone.
- If trace evidence is too thin, agents will not be able to validate user-driven GUI runs after the fact.

## Important files / paths / commands / artifacts

- `C:\Dev\3DGS\LFS-plugins\lfs-queue\queue_controller.py`: queue runtime and replay logic
- `C:\Dev\3DGS\LFS-plugins\lfs-queue\queue_cli.py`: no-MCP command helpers for fixture discovery and LFS-script queue commands
- `C:\Dev\3DGS\LFS-plugins\lfs-queue\queue_live_verify.py`: no-MCP env-gated live verifier used by LFS plugin autoload
- `C:\Dev\3DGS\LFS-plugins\lfs-queue\scripts\queue_cli.py`: wrapper for normal Python/script execution
- `C:\Dev\3DGS\LFS-plugins\lfs-queue\queue_live_verify_report.json`: generated report from the latest Nightly run, ignored by git
- `C:\Dev\3DGS\LFS-plugins\lfs-queue\queue_live_verify_app.log`: generated app log from the latest Nightly run, ignored by git
- `C:\Dev\3DGS\LFS-plugins\lfs-queue\panels\main_panel.py`: panel path, `Add to Queue`, readiness-disabled UI, `Clear Queue`
- `C:\Dev\3DGS\LFS-plugins\lfs-queue\__init__.py`: active plugin registration; no MCP registration
- `C:\Dev\3DGS\LFS-plugins\lfs-queue\docs\00-product-requirements.md`: high-level product direction and V1 scope
- `C:\Dev\3DGS\LFS-plugins\lfs-queue\tasks\todo.md`: current prioritized backlog
- `C:\Dev\3DGS\LFS-plugins\lfs-queue\tasks\archive\panel-runtime-divergence-superseded-2026-05-10.md`: archived historical debug handoff; read only for background, not current direction
- `C:\Dev\3DGS\_example_datasets\COLMAP-ready-datasets`: local ready COLMAP fixture root; select a nested `colmap` folder
- `C:\Dev\3DGS\LFS-plugins\lfs-queue\live_queue_debug_trace.jsonl`: authoritative trace from the real panel run
- `C:\Dev\3DGS\LFS-plugins\lfs-queue\codex_fresh_verify_app.log`: host-side log for the same verification run
- `C:\Dev\3DGS\LFS-plugins\lfs-queue\.gitignore`: excludes generated queue outputs, media, logs, and report artifacts from git
- `C:\Users\Azad\Documents\_apps\LichtFeld_Studio\LFS_Stable\bin\lichtfeld\__init__.pyi`: exact `OptimizationParams` surface for this build
- `python -m unittest discover -s tests -p "test_*.py"`: currently passes; sanity only, not acceptance
- `python .\scripts\queue_cli.py fixtures`: lists local ready COLMAP fixtures without needing LFS or MCP

## Last updated

Queue artifact cleanup checkpoint: user verified the queue run and found expected queue outputs, plus a duplicate final live training model and ambiguous native top-level LFS artifacts. Patch now moves each job checkpoint into its job folder, removes ambiguous native top-level `splat_*.ply` files after saving named queue PLYs, and removes the final live training model before reloading completed queue outputs.
