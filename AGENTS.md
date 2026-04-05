# Repository Guidelines

## Project Structure & Module Organization
This repository is dataset-first rather than application-first. Keep files grouped by purpose:

- `docs/` for process notes, workflow documentation, and reproducibility details.
- `example dataset/resist house/colmap/` for raw COLMAP inputs such as drone images, `Cameras.txt`, `Images.txt`, `Points3D.txt`, and `reg.csv`.
- `example dataset/resist house/colmap/output/` for derived artifacts such as checkpoints and exported `.ply` files.

Follow the same pattern for new scenes: `<dataset>/<scene>/colmap/` for source material and `<dataset>/<scene>/colmap/output/` for generated results. Do not mix generated files into raw capture folders.

## Build, Test, and Development Commands
There is no build system or automated test runner checked in yet. Use lightweight inspection commands while working locally:

```powershell
rg --files
Get-ChildItem "example dataset\resist house\colmap"
Get-Content "example dataset\resist house\colmap\Cameras.txt" -TotalCount 20
```

Use `rg --files` to locate repository content, `Get-ChildItem` to verify dataset layout, and `Get-Content` to spot-check COLMAP text outputs before committing.

## External Tool Paths
LichtFeld Studio (LFS) installations used alongside this repository are stored outside the repo:

- Stable: `C:\Users\Azad\Documents\_apps\LichtFeld_Studio\LFS_Stable`
- Nightly: `C:\Users\Azad\Documents\_apps\LichtFeld_Studio\LFS_nightly`
- Repo docs: `C:\Dev\3DGS\LichtFeld-Studio\docs`
- General refs/docs: `C:\Dev\_docs`

Reference these exact paths in documentation or local workflow notes when a task depends on a specific build.

## Low-Touch Execution
Default expectation: the agent should handle build, test, live verification, evaluation, and iteration with minimal user involvement.

Preferred workflow for this repo:

- Run local unit tests and script-based checks without asking the user to verify intermediate results.
- When queue behavior depends on the live app, prefer the GUI MCP HTTP path over fragile in-process `--python-script` verification.
- Use the stable LFS build first unless there is a specific reason to target nightly:
  - `C:\Users\Azad\Documents\_apps\LichtFeld_Studio\LFS_Stable\bin\LichtFeld-Studio.exe`
- For queue debugging, the agent should capture evidence directly from:
  - `plugin.queue.state`
  - `plugin.queue.debug_events`
  - `lichtfeld://runtime/state`
  - `lichtfeld://runtime/events`
- The agent should not tell the user a fix is complete until it has personally run the relevant end-to-end flow and inspected the resulting evidence.
- The agent should only stop and ask the user when:
  - sandbox or permission escalation is required
  - the task depends on a GUI/session state the agent cannot access
  - there is a destructive or ambiguous action that should not be assumed
  - there is a genuine external blocker that cannot be resolved from the repo or local tools

Current queue-specific expectation:

- The agent should launch LFS itself when needed, run the queue verifier itself, inspect the stop point itself, patch only the observed failure, and rerun verification itself.
- User interaction should be treated as exception handling, not the normal validation loop.

## Coding Style & Naming Conventions
Keep your responses to the user short in codex/chats short. do not be verbose unless asked for. this is specifically about the chat experience. docs should be as verbose as need-be. 

Keep Markdown concise and task-focused. For new scripts, prefer Python with 4-space indentation, `snake_case` filenames, and small single-purpose modules. Preserve original camera image names from capture devices. Name generated outputs clearly, for example `output/splat_010000.ply`.

No formatter or linter is configured yet; match surrounding style and keep changes minimal.

## Testing Guidelines
There is no formal coverage target today. Validate contributions by checking that COLMAP text files remain readable and internally consistent, generated artifacts are written only under `output/` or another clearly derived directory, and documentation references real paths and commands.

If you add executable code, include a `tests/` directory and name files `test_<feature>.py`.

## Commit & Pull Request Guidelines
Git history is not available in this checkout, so use short imperative commit messages such as `Add second sample dataset` or `Document COLMAP output layout`. Keep each commit scoped to one logical change.

Pull requests should include a brief summary, affected dataset paths, validation steps performed, and screenshots only when a visual result changed.

## Data Hygiene
Large binary outputs grow quickly. Avoid duplicating raw imagery, keep regenerated artifacts in derived directories, and document external tools or parameter changes in `docs/` when they affect reproducibility.
