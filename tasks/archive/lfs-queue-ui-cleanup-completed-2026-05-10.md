# LFS Queue UI Cleanup

- Status: completed
- Last updated: 2026-05-10 11:20 local time

## User Ask

- Make the queue UI very bare bones.
- Keep only:
  - `Add to Queue`
  - `Run Queue`
  - `Clear Queue`

## Result

- `panels/main_panel.py` was simplified to the three requested controls.
- The read-only queue table remains so queued jobs and statuses are visible.

## Verification

- `python -m py_compile panels\main_panel.py`
- `python -m unittest discover -s tests -p "test_*.py"`: 15 passed.

## Note

- This was incorrectly created under `tasks/active/` even though the `new-task` skill says new task records should go under `tasks/planned/`.
- Because the implementation was already completed, this record was moved to archive instead of leaving a stale planned task.
