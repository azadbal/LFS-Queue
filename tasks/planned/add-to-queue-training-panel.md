# Add To Queue Training Panel

- Status: planned
- Last updated: 2026-05-10 11:28 local time

## User Ask

- Add an `Add to Queue` control into the native LFS Training UI panel, under the existing `Start Training` button, instead of relying on a separate plugin panel for that action.

## Current Objective

- Determine the clean plugin-friendly integration path and implement the smallest maintainable slice that places `Add to Queue` in the Training panel controls area.

## Plan

1. Inspect the host Training panel implementation and confirm whether an existing UI hook point can place plugin controls under `Start Training`.
2. If no hook exists, add a generic host-side Training panel extension point that is not specific to `lfs_queue`.
3. Register the queue plugin's `Add to Queue` action into that extension point, using the same native readiness gating as the current queue panel.
4. Decide whether the separate `LFS Queue` panel should remain for `Run Queue`, `Clear Queue`, and queue status only.
5. Validate in LFS Nightly with a loaded training-ready COLMAP dataset.

## Open Questions

- Should `Run Queue` and `Clear Queue` also move into the Training panel, or should only `Add to Queue` live under `Start Training` for now?
- Should this require a host LFS repo change, or can a suitable hook be used from the plugin repo alone?

## Next Actions

- Inspect `training_panel.py`, `training.rml`, and the UI hook system, then choose the least invasive implementation path.

## Blockers

- May require a small host repo change if the Training panel does not currently expose a hook point below the native controls.

## Key Files

- `C:\Dev\3DGS\LFS-plugins\lfs-queue\panels\main_panel.py`: current plugin panel controls.
- `C:\Dev\3DGS\LFS-plugins\lfs-queue\queue_controller.py`: `add_current_job()` and readiness logic.
- `C:\Dev\3DGS\Lichtfeld-Studio-GH-REPO\LichtFeld-Studio\src\python\lfs_plugins\training_panel.py`: native Training panel logic.
- `C:\Dev\3DGS\Lichtfeld-Studio-GH-REPO\LichtFeld-Studio\src\visualizer\gui\rmlui\resources\training.rml`: native Training panel controls markup.
- `C:\Dev\3DGS\Lichtfeld-Studio-GH-REPO\LichtFeld-Studio\src\python\lfs\py_ui_hooks.cpp`: Python UI hook registration/invocation.
