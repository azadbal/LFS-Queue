# LFS Queue

`lfs_queue` is a LichtFeld Studio plugin for running multiple training variants from the current training-ready LFS scene. It snapshots the active dataset and optimization settings, queues those snapshots as jobs, runs them one at a time through native LFS training, and writes each finished model to its own queue output folder for comparison.

The plugin is intentionally session-focused: prepare a scene in LFS, add variants, run the queue, compare the outputs, then start a new queue when needed.

## What It Does

- Adds an `LFS Queue` panel in the main LFS panel tab.
- Enables `Add to Queue` only when native LFS training is ready.
- Captures the current config via `lf.save_config_file(...)`.
- Replays supported optimization settings and mutable dataset options for each job.
- Runs jobs sequentially with native `lf.start_training()`.
- Resets LFS training state between jobs when the runtime needs it.
- Saves completed models as `model-1.ply`, `model-2.ply`, etc.
- Moves native `checkpoints/checkpoint.resume` into the matching queue job folder.
- Reloads completed queue outputs into the current LFS session after the queue finishes.
- Writes runtime trace evidence to `live_queue_debug_trace.jsonl`.

The queue does not use MCP for implementation or verification.

## Typical Workflow

1. Load or prepare a COLMAP dataset in LichtFeld Studio.
2. Wait until the native `Start Training` action is available.
3. Adjust the normal LFS training settings.
4. Open the `LFS Queue` panel.
5. Click `Add to Queue`.
6. Change settings and click `Add to Queue` again for more variants.
7. Click `Run Queue`.
8. Inspect the completed `.ply` outputs loaded back into the scene.

Jobs are held only for the current LFS run. Any persisted queue state from older versions is discarded when the controller starts.

## Output Layout

For a dataset whose native output path is:

```text
<dataset>/colmap/output
```

queue jobs write under:

```text
<dataset>/colmap/output/queue/model-1/
<dataset>/colmap/output/queue/model-2/
```

Each completed job folder may contain:

```text
model-1.ply
config.json
checkpoints/checkpoint.resume
```

LFS may briefly create native top-level artifacts such as `splat_<iter>.ply` or `checkpoints/checkpoint.resume`. After a job completes, the plugin claims those artifacts for the active queue job and removes ambiguous top-level native splats after the named queue `.ply` has been saved.

## Install From GitHub

This repository is already laid out as a LichtFeld plugin root. LFS can install it directly from the repository URL:

```python
import lichtfeld as lf

lf.plugins.install("https://github.com/azadbal/LFS-Queue")
```

Using a release tag is recommended for repeatable installs:

```python
lf.plugins.install("https://github.com/azadbal/LFS-Queue@v0.1.0")
```

For local development on Windows, junction the repo into the LFS user plugin folder:

```powershell
cmd /c mklink /J "%USERPROFILE%\.lichtfeld\plugins\lfs_queue" "C:\Dev\3DGS\LFS-plugins\lfs-queue"
```

Then load it in LFS:

```python
import lichtfeld as lf

lf.plugins.discover()
lf.plugins.load("lfs_queue")
```

The included `settings.json` enables startup loading with:

```json
{
  "load_on_startup": true
}
```

## Local Validation

Run unit tests from the repo root:

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

List local ready COLMAP fixtures:

```powershell
python .\scripts\queue_cli.py fixtures
```

The `fixtures` command can run in normal Python. The other CLI commands need an LFS Python context because they use the live `lichtfeld` module:

```powershell
python .\scripts\queue_cli.py state
python .\scripts\queue_cli.py add-current
python .\scripts\queue_cli.py run-all
python .\scripts\queue_cli.py clear
```

For live end-to-end verification, launch LFS with `LFS_QUEUE_AUTORUN_VERIFY=1`. The verifier loads a COLMAP fixture, queues two jobs, runs them, writes `queue_live_verify_report.json`, and exits LFS unless `LFS_QUEUE_VERIFY_EXIT=0` is set.

Useful verifier environment variables:

- `LFS_QUEUE_VERIFY_DATASET`
- `LFS_QUEUE_VERIFY_OUTPUT`
- `LFS_QUEUE_VERIFY_REPORT`
- `LFS_QUEUE_VERIFY_ITERATIONS`
- `LFS_QUEUE_VERIFY_TIMEOUT_SECONDS`
- `LFS_QUEUE_VERIFY_EXIT`

Local fixture datasets belong under `_testingSplatArea/`, which is intentionally gitignored.

## Repo Layout

```text
__init__.py                  Plugin load/unload entrypoint
panels/main_panel.py         LFS Queue panel UI
queue_core.py                Pure queue models and helpers
queue_controller.py          LFS runtime integration and state machine
queue_cli.py                 No-MCP command helpers
queue_live_verify.py         LFS autorun verification helper
scripts/                    Script wrappers and verification helpers
tests/                      Unit tests with fake LFS adapters
docs/                       Development, product, and shipping notes
```

## Current Limits

- Jobs replay the current dataset and settings; they are not checkpoint-resume experiments.
- Queue state is session-only and is not restored across LFS restarts.
- The panel assumes the user has already prepared LFS until native training is possible.
- Only supported public LFS optimization/dataset fields are replayed.
- Detailed experiment metrics such as PSNR, SSIM, splat count, and duration are not part of V1.

## Requirements

- Python `>=3.12`
- LichtFeld Studio `>=0.4.2`
- LichtFeld plugin API `>=1,<2`

## License

MIT
