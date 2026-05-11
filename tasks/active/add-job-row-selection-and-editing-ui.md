# Add Job Row Selection And Editing UI

- Status: active
- Last updated: 2026-05-10 20:37 local time

## User Ask

- For the queue UI, make a row for each job.
- Treat each thing added to the queue as a `job`.
- Make job rows selectable.
- When a job is selected, enable action buttons above the list, including `Remove`.
- Add an `Edit` button that loads the selected job's settings into the LFS settings UI so the job can be changed.
- Add a `Save` button that overwrites the selected job instead of creating a new one with `Add to Queue`.
- Record the shared `job` terminology in `AGENTS.md` under a terms section.
- Remove the currently shown directory/path fields from the per-job row display.
- Tighten the row layout so the columns are not spaced far apart.
- Show useful per-job settings/stats in each row instead, including iteration count, densification strategy/model, max Gaussian cap, and enabled-only flags such as bilateral grid, undistort, PPISP, and similar toggles.

## Current Objective

- Confirm the new selectable summary-row list behaves correctly in a normal interactive LFS session and keep the repaired panel stable.

## Scope Status

- Scope expanded from implementing row selection and editing to also harden narrow-panel rendering and capture the live-panel verification lesson after a panel draw regression.
- Scope also includes replacing the current directory-heavy row content with a denser job-summary layout that surfaces the agreed queued settings and flags instead of output or dataset paths.

## Dev Plan

1. Add controller-owned selection and editing state so the panel can safely target one selected job, load that job back into the active LFS settings, and save edits back onto the same job record.
2. Update the queue panel to render selectable job rows plus selected-job actions above the list, with `Remove`, `Edit`, and `Save` states driven by controller selection and edit mode.
3. Extend fake-LFS controller tests to cover selecting, editing, saving, and deleting jobs without introducing MCP or dataset reload behavior.
4. Run repo unit tests, then verify the edit flow against the stable LFS build and inspect runtime evidence such as `live_queue_debug_trace.jsonl`.

## Validation

- `python -m unittest discover -s tests -p "test_*.py"`: confirms queue controller and core behavior still pass after the editing flow changes.
- Stable LFS autorun verify: confirms plugin load plus add, edit, save, remove, and queue execution still work in the real app runtime.

## Known State

- [C:\Dev\3DGS\LFS-plugins\lfs-queue\queue_controller.py](C:\Dev\3DGS\LFS-plugins\lfs-queue\queue_controller.py) now owns selected-job and editing state plus edit-load, save-overwrite, and delete-selected behavior.
- [C:\Dev\3DGS\LFS-plugins\lfs-queue\panels\main_panel.py](C:\Dev\3DGS\LFS-plugins\lfs-queue\panels\main_panel.py) now uses selectable single-line summary rows instead of the earlier table interaction; a bad `ui.text(...)` call caused a panel draw regression earlier and was repaired by switching back to supported text rendering.
- The compact row fields are now decided: `Job`, `Status`, `Iterations`, `Strategy`, `Max Gaussians`, and enabled-only `Flags`.
- `Max Gaussians` should come from the queued `optimization.max_cap` setting, not from a completed model's real splat or PLY Gaussian count.
- The flags cell should render only enabled toggles among `Bilateral Grid`, `Undistort`, `PPISP`, `PPISP Controller`, `Freeze Gaussians`, `Revised Opacity`, `Sparsity`, and `MIP`; when none are enabled it should show `--`.
- On narrow panels, the flags string should stay single-line, truncate if needed, and expose the full value through the existing tooltip pattern.
- [C:\Dev\3DGS\LFS-plugins\lfs-queue\tests\test_main_panel_summary_helpers.py](C:\Dev\3DGS\LFS-plugins\lfs-queue\tests\test_main_panel_summary_helpers.py) now covers the pure helper logic for summary values, enabled-only flags, and `--` fallbacks without needing a live LFS UI session.
- Stable LFS autorun verification still passes after the repair, but autorun does not prove that a human-opened `LFS Queue` tab is visually healthy in the current desktop session.
- The host LFS repo exposes `lf.load_config_file(path)` and immediate-mode UI APIs through the stubs under `C:\Dev\3DGS\Lichtfeld-Studio-GH-REPO\LichtFeld-Studio\src\python`; UI methods must be checked there before use.
- [C:\Dev\3DGS\LFS-plugins\lfs-queue\AGENTS.md](C:\Dev\3DGS\LFS-plugins\lfs-queue\AGENTS.md) already includes the repo terms section that defines each queue entry as a `job`.

## Open Questions

- None.

## Blockers

- Final visual confirmation of the repaired panel still depends on a live human-opened `LFS Queue` tab after reload.

## Key Files

- `C:\Dev\3DGS\LFS-plugins\lfs-queue\panels\main_panel.py`: queue panel layout, button states, and row-selection UI.
- `C:\Dev\3DGS\LFS-plugins\lfs-queue\queue_controller.py`: queue add, remove, update, and edit-back-into-settings behavior.
- `C:\Dev\3DGS\LFS-plugins\lfs-queue\queue_core.py`: queue/job data model and state handling.
- `C:\Dev\3DGS\Lichtfeld-Studio-GH-REPO\LichtFeld-Studio\src\python`: host-side settings APIs and training UI integration points used as ground truth for `lf.load_config_file(...)` and selectable UI support.
- `C:\Dev\3DGS\LFS-plugins\lfs-queue\queue_live_verify.py`: stable-build autorun verification path that now covers select, edit, save, remove, re-add, and rerun.

## Done

- Promoted the task from `tasks/planned/` to `tasks/active/`.
- Inspected the queue panel, controller, queue core, tests, and host LFS API surface for config loading and selectable UI support.
- Confirmed the repo already uses the shared `job` terminology in `AGENTS.md`.
- Added controller-owned job selection and edit mode, including load-into-settings, save-overwrite, and selected-job remove behavior.
- Updated the panel to render selectable job rows plus `Save`, `Remove`, and `Edit` or `Cancel Edit` actions above the queue list.
- Reworked the panel row interaction to use explicit row buttons and replaced wrapped path rendering with compact, truncated path text plus clearer path labels for narrow panels.
- Fixed the panel draw regression by replacing the unsupported `ui.text(...)` call with supported text rendering.
- Captured the regression learning in `AGENTS.md`: panel UI changes now require explicit live tab-render verification, and immediate-mode UI methods must be checked against host stubs or source before use.
- Confirmed the compact row summary should use max Gaussian cap rather than actual completed-model Gaussian count.
- Confirmed the row flags should be enabled-only, render `--` when empty, and keep truncation plus tooltip behavior on narrow panels.
- Replaced the row path columns with queued-setting summaries.
- Replaced the table-based row UI with one selectable single-line summary row per job so wide and narrow layouts use the same text-first presentation.
- Switched truncated UI text rendering to `ui.label(...)` so row text stays single-line instead of wrapped.
- Added helper-level tests for row summary formatting and flag extraction.
- Extended fake-LFS tests for begin-edit, save-overwrite, and delete-selected behavior.
- Extended the live autorun verifier to exercise the select, edit, save, remove, re-add, and run flow inside the stable LFS build.
- Validation completed:
  - `python -m py_compile panels\main_panel.py tests\test_main_panel_summary_helpers.py` passed.
  - `python -m unittest discover -s tests -p "test_*.py"` passed with 22 tests.
  - Stable LFS autorun verify completed again after the selectable summary-row change and the latest report still shows `queue_completed: true`.

## Next Actions

1. Reload LFS or reopen the plugin tab in a normal interactive session and confirm the selectable summary rows visibly render.
2. Recheck that clicking a job row visibly marks it selected and enables `Edit` and `Remove`.
3. If selection is still unreliable in the live panel even after moving off the table, replace the list with per-job cards plus direct per-row action buttons as the next fallback.
4. Keep an eye on any future need to replay more optimization keys if editing should cover advanced settings that are currently intentionally skipped during job run replay.
