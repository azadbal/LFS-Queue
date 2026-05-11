# LFS Queue Todo

## Priority 1: Bare-Bones Queue

- [ ] Refactor queue runtime behind a small LFS adapter/facade so core behavior can be tested with fakes.
- [ ] Remove MCP registration and MCP resource reads from the active plugin path.
- [ ] Put `Add to Queue` where the user normally starts training, or make it equally easy to reach.
- [ ] Enable `Add to Queue` only when the native LFS `Start Training` action would be available.
- [ ] Capture the current training-ready LFS state and settings when `Add to Queue` is clicked.
- [ ] Let the user add multiple jobs for the same dataset after changing settings between adds.
- [ ] Show queued jobs with simple generated names.
- [ ] Use simple incrementing names first: `model-1`, `model-2`, `model-3`.
- [ ] Run queued jobs sequentially.
- [ ] When a job finishes, stop/finalize that training run and start the next queued job.
- [ ] Keep each completed output loaded in the same LFS session so models can be compared visually.
- [ ] Keep queue state session-only; no persistence across app restarts.
- [ ] Verify using the real LFS GUI/panel flow, not MCP.
- [ ] Do not implement dataset import/loading as part of the queue workflow.

## Priority 1A: Verification and Back Pressure

- [ ] Add fake-adapter unit tests for training readiness gating.
- [ ] Add fake-adapter unit tests for independent job setting snapshots.
- [ ] Add fake-adapter unit tests for sequential job progression.
- [ ] Add fake-adapter unit tests for failed-job skip/advance behavior.
- [ ] Add a test or import guard proving the active plugin path does not register/call MCP.
- [ ] Write local trace events for add attempts, blocked adds, job start, training start, training finish, preservation/output load, failure, advance, and queue completion.
- [ ] Ensure traces are enough to validate a user-driven GUI run afterward without MCP.
- [ ] Add back pressure states so the queue cannot start two jobs at once.
- [ ] Use a finalizing phase after training ends before starting the next job.
- [ ] Start the next job only after preservation/export cleanup is complete and LFS is back in a safe state.
- [ ] Add timeout handling for "training requested but never started".
- [ ] Add timeout handling for "finalization never completed".
- [ ] Add a no-MCP CLI/scriptable queue runner for development and regression testing.
- [ ] CLI runner should use COLMAP fixtures under `C:\Dev\3DGS\LFS-plugins\lfs-queue\_testingSplatArea\*\colmap`.
- [ ] Keep `_testingSplatArea/` gitignored and out of commits.
- [ ] CLI runner should write a machine-readable report plus plugin trace/log evidence.

## Priority 2: Basic Output Handling

- [ ] Ensure each job writes a distinct `.ply` output.
- [ ] Use distinct output filenames such as `model-1.ply`, `model-2.ply`.
- [ ] Keep generated outputs in the dataset output area or another clearly derived output folder.

## Priority 3: Installable Plugin

- [ ] Document manual installation for local LFS plugin use.
- [ ] Clean up plugin metadata and folder structure for sharing.
- [ ] Add shipping notes only after the core queue flow works reliably.

## Later: Naming, Stats, Logs, and Comparison

- [ ] Generate descriptive names from selected settings.
- [ ] Record per-job logs.
- [ ] Capture useful stats after training, such as PSNR, SSIM, splat count, duration, and output path.
- [ ] Improve queue item display for fast comparison between training variants.
