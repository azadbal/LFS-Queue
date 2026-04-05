# LFS Queue

`lfs_queue` is a Lift Studio plugin for queueing multiple training variants from the same dataset snapshot.

V1 is intentionally narrow:

- Capture the current dataset and optimization setup into queue jobs
- Keep the queue session-scoped within the current LFS run
- Reload the dataset fresh for each job
- Train jobs one-by-one from a main-tab panel
- Preserve each completed model in-scene as `model 1`, `model 2`, and so on
- Write each run into its own output subfolder under `<output>/queue/`

## Current Workflow

1. Load a dataset in Lift Studio.
2. Adjust training settings in the native UI.
3. Open the `LFS Queue` panel and click `Add Current`.
4. Change settings again and add more jobs.
5. Click `Run Selected` or `Run All Pending`.

Each job stores:

- Full config JSON captured via `lf.save_config_file(...)`
- Dataset path
- Base output directory
- Mutable dataset overrides that the public Python API can replay

## MCP Tools

When LFS is running with this plugin loaded, the plugin also registers these MCP tools:

- `queue.state`
- `queue.add_current`
- `queue.run_all`
- `queue.stop`
- `queue.debug_events`

In the live LFS MCP registry, Python tools are auto-namespaced, so these appear as `plugin.queue.state`, `plugin.queue.add_current`, `plugin.queue.run_all`, `plugin.queue.stop`, and `plugin.queue.debug_events`.

`queue.state` returns the current session job list plus runtime metadata such as `phase`, `active_job_id`, `auto_run`, `is_running`, and the latest `status_message`.

`queue.debug_events` returns a recent ring buffer of queue lifecycle events so you can see transitions like dataset reload, config apply, training start, training end, and model preservation without scraping the raw app log.

## Repo Layout

```text
__init__.py             Plugin entrypoint
queue_core.py           Pure queue models and helpers
queue_controller.py     LFS runtime integration and state machine
queue_mcp.py            MCP tool registration for remote control/debugging
panels/main_panel.py    Immediate-mode queue UI
tests/test_queue_core.py
docs/                   Template docs copied from the starter
```

## Local Validation

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

Manual validation still matters because the runtime behavior depends on the live Lift Studio plugin API.

## Known V1 Limits

- Jobs are same-dataset replays, not checkpoint resumes.
- Disk outputs are isolated with per-job subfolders because LFS does not currently expose dataset `output_name` in public Python.
- Preserved prior models are session-scoped queue results. They are meant to survive dataset reloads within the current live queue run, not to persist across app restarts.

## License

MIT
