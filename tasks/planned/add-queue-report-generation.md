# Add Queue Report Generation

- Status: planned
- Last updated: 2026-05-10 12:16 local time

## User Ask

- Add an optional `Create report` queue UI checkbox, enabled by default, that generates per-job render outputs, settings, metrics, timestamped queue-level JSON/HTML reports, and comparison animations after queued LFS training jobs finish.

## Current Objective

- Design and implement the first report-generation slice that reuses LFS rendering/evaluation APIs where possible and produces consistent comparison artifacts for completed queue jobs.

## Plan

1. Inspect the current queue controller/panel flow and host LFS rendering or evaluation APIs before choosing the render implementation path.
2. Add a default-enabled `Create report` checkbox to the queue UI and thread its value through queued job execution without changing queue behavior when disabled.
3. For each completed job, write `job_settings.json`, `job_metrics.json`, and three consistent reference renders under the job folder's `renders/` directory.
4. After the queue finishes, generate timestamped queue-level JSON and HTML reports containing queue metadata, job settings, metrics, render paths, splat paths, log links, and comparison media paths.
5. Generate one timestamped comparison animation per reference view, preferring MP4 and falling back to GIF only if MP4 generation is unavailable.
6. Validate with unit/script checks plus a real LFS GUI queue run that produces multiple completed jobs and report artifacts.

## Open Questions

- Does LFS already expose an evaluation render path for arbitrary COLMAP camera/image views that can be reused?
- Which LFS APIs expose PSNR, SSIM, final Gaussian count, final iteration count, runtime duration, and other metrics after training completes?
- Which queue UI feature flags should be treated as "major" settings for `job_settings.json` beyond the explicitly listed fields?
- Should comparison videos be generated with an existing local ffmpeg dependency, Python image tooling, or an LFS/host-provided media path?

## Next Actions

- Inspect `queue_controller.py`, `panels/main_panel.py`, and the host LFS docs/source for render/evaluation and metrics APIs.

## Blockers

- None yet; implementation depends on confirming available LFS render/evaluation and metrics APIs from the host repo.

## Key Files

- `C:\Dev\3DGS\LFS-plugins\lfs-queue\queue_controller.py`: queue execution, job finalization, per-job artifact generation, and queue completion flow.
- `C:\Dev\3DGS\LFS-plugins\lfs-queue\panels\main_panel.py`: queue UI location for the default-enabled `Create report` checkbox.
- `C:\Dev\3DGS\LFS-plugins\lfs-queue\queue_core.py`: possible queue/job data model changes for report settings and artifact paths.
- `C:\Dev\3DGS\LFS-plugins\lfs-queue\tests\`: focused tests for report gating, report metadata, and artifact path generation.
- `C:\Dev\3DGS\LichtFeld-Studio\docs`: host documentation to check first for render/evaluation features.
- `C:\Dev\3DGS\LichtFeld-Studio\src\python`: host Python APIs for training metrics, dataset cameras, rendering, and plugin integration.
- `C:\Dev\3DGS\LichtFeld-Studio\src\visualizer`: host visualizer/rendering behavior and UI extension context.
