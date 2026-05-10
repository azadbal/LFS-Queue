# LFS Queue Product Requirements

## Purpose

Build a LichtFeld Studio plugin that lets a user queue multiple training runs for the already-ready training state in LFS, run them sequentially, and compare the resulting splats in the same LFS session.

The first priority is a working bare-bones queue. Packaging the plugin so others can install it is a second priority. Metrics, logs, and analysis features are later work.

## Target User Flow

1. User gets LFS into a state where the native `Start Training` button would be available.
2. User adjusts the normal LFS training settings.
3. Instead of starting training immediately, user clicks `Add to Queue`.
4. User changes settings again and clicks `Add to Queue` again.
5. User starts the queue.
6. Job 1 performs the same kind of training run that `Start Training` would have performed for that captured state.
7. When job 1 finishes, the plugin keeps its output loaded in the scene.
8. The plugin starts job 2 automatically.
9. When job 2 finishes, both completed splats are loaded in the same LFS session for visual comparison.

## V1 Scope

- Queue jobs only when LFS is already ready to train.
- Treat the native `Start Training` button as the source of truth for readiness: if LFS cannot start training, the plugin should not allow adding a queue job.
- Capture the current training-ready state and settings when `Add to Queue` is clicked.
- Keep queue state session-only. Jobs do not need to persist across LFS restarts.
- Run queued jobs one at a time.
- After each job completes, preserve or reload its resulting `.ply` in the LFS scene.
- Name outputs with a simple incrementing scheme such as `model-1.ply`, `model-2.ply`.
- Provide enough UI to add jobs, view queued jobs, start the queue, and clear/reset the queue.

## V1 Non-Goals

- No MCP dependency for implementation or verification.
- No dataset import/loading workflow. The plugin assumes the user has already prepared LFS until training is possible.
- No cross-session queue persistence.
- No advanced failure recovery beyond moving on when practical.
- No full experiment analytics dashboard.
- No PSNR, SSIM, splat count, or detailed stats in V1.
- No plugin marketplace/shipping polish until the core queue works.

## Later Goals

- Package the plugin so other LFS users can install it.
- Add a no-MCP CLI/scriptable queue path for development and regression testing.
- Generate more descriptive names from selected settings.
- Add per-job stats such as PSNR, SSIM, splat count, duration, output path, and final file size.
- Write useful logs for completed jobs.
- Improve comparison workflows around loaded models.

## Acceptance Criteria

- In a real LFS GUI session where native `Start Training` is available, the user can add two queue jobs with different settings, run the queue, and see both completed outputs loaded in the scene.
- When native `Start Training` is unavailable, `Add to Queue` is unavailable or disabled too.
- The second job starts after the first job finishes without manual intervention.
- Outputs are named distinctly with an incrementing scheme.
- The queue does not rely on MCP tools or MCP-based verification.
- The plugin writes local trace/log evidence that lets an agent validate what happened after a manual GUI run.

## Verification Strategy

- Core queue behavior should be unit-tested with a fake LFS adapter.
- Real acceptance should be validated in LFS through visible UI behavior, app logs, plugin trace files, generated outputs, and loaded scene models.
- For local dogfood testing, use ready COLMAP datasets under:
  - `C:\Dev\3DGS\_example_datasets\COLMAP-ready-datasets`
- Choose a scene subfolder, then use its nested `colmap` folder. Known fixtures include:
  - `C:\Dev\3DGS\_example_datasets\COLMAP-ready-datasets\ferry building drone\colmap`
  - `C:\Dev\3DGS\_example_datasets\COLMAP-ready-datasets\360-hobart-short\colmap`
- The original single-fixture path was:
  - `C:\Dev\3DGS\_example_datasets\COLMAP-ready-datasets\ferry building drone\colmap`
- These datasets are only validation fixtures. The plugin itself should still assume LFS is already ready to train for the panel workflow.
- The CLI/scriptable test path may load a fixture dataset as test setup, then exercise the same queue controller logic without MCP.
- The queue should use explicit phases so it can handle runtime back pressure:
  - `idle`
  - `starting`
  - `training`
  - `finalizing`
  - `stopping`
- The queue must not start the next job from inside the training-end callback. It should finalize the completed job first, then start the next job once LFS is safe to train again.

## CLI / Scriptable Queue Requirement

- Provide a supported no-MCP way to run queue workflows from a command/script context.
- The CLI path should be able to:
  - load or assume a ready COLMAP fixture for test setup
  - add two or more jobs from supplied setting presets or config files
  - run the queue to completion
  - write plugin-owned trace/report files
  - return a machine-readable success/failure result
- This path is for development, regression testing, and automation. It should share the same queue core/controller behavior as the GUI path rather than becoming a separate implementation.
