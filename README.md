# LFS Queue

`lfs_queue` is a LichtFeld Studio plugin for queueing multiple training variants from the current LFS state when training is already available.

V1 is intentionally narrow:

- Capture the current training-ready LFS state and optimization setup into queue jobs
- Enable queueing only when native LFS training is available
- Keep the queue session-scoped within the current LFS run
- Reset the active LFS training state between jobs when needed
- Let the user add jobs instead of immediately starting training
- Train jobs one-by-one
- Save each completed model as a distinct queue output
- Move each job checkpoint into that job's queue folder
- Reload completed outputs for comparison after the queue finishes
- Write distinct outputs such as `model-1.ply`, `model-2.ply`

## Current Workflow

1. Prepare LFS until the native `Start Training` action is available.
2. Adjust training settings in the native UI.
3. Click `Add to Queue`.
4. Change settings again and add more jobs.
5. Click `Run Selected` or `Run All Pending`.

Each job stores:

- Full config JSON captured via `lf.save_config_file(...)`
- Dataset path
- Base output directory
- Mutable dataset overrides that the public Python API can replay

## Repo Layout

```text
__init__.py             Plugin entrypoint
queue_core.py           Pure queue models and helpers
queue_controller.py     LFS runtime integration and state machine
panels/main_panel.py    Immediate-mode queue UI
queue_cli.py            No-MCP command helpers for scripts/LFS Python
tests/test_queue_core.py
docs/                   Template docs copied from the starter
```

## Local Validation

```powershell
python -m unittest discover -s tests -p "test_*.py"
python .\scripts\queue_cli.py fixtures
```

Manual validation still matters because the runtime behavior depends on the live Lift Studio plugin API.
Acceptance should be based on the real LFS GUI/panel flow, local logs, and trace artifacts, not MCP tooling.

Queue CLI commands that touch LFS state, such as `state`, `add-current`, `run-all`, and `clear`, must run inside an LFS Python/script context because they require the live `lichtfeld` module. The `fixtures` command can run from normal Python and discovers ready COLMAP test fixtures under `C:\Dev\3DGS\_example_datasets\COLMAP-ready-datasets`.

## Known V1 Limits

- Jobs are same-dataset replays, not checkpoint resumes.
- Disk outputs are saved by exporting the trained scene model after each job because LFS dataset `output_path` is read-only through the current public Python API.
- Native LFS may briefly write top-level `splat_<iter>.ply` and `checkpoints/checkpoint.resume` files to the base output path. The queue claims those after each job: checkpoints move under `queue/<job>/checkpoints/`, and ambiguous top-level native splats are removed after the named queue PLY is saved.
- Completed queue outputs are session-scoped comparison results. They are reloaded after the queue run, not persisted as queue state across app restarts.

## License

MIT
