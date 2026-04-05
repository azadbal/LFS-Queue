# Planned Work

## Current
- Dogfood the queue in a normal LFS GUI session with fresh jobs, not reused debug-state jobs.
- Start from a loaded dataset, clear or ignore old queue entries, add 2-3 fresh variants with visibly different iteration counts/settings, and run them from the `LFS Queue` panel.
- Acceptance for the dogfooding pass:
  - each new job loads without manual intervention
  - each job trains
  - each job finalizes
  - completed models stay visible in-scene during the same session
  - the next job starts automatically
  - queue status/debug events stay coherent without MCP-only inspection
- During the dogfooding pass, note any UX friction:
  - confusing button flow
  - unclear status text
  - queue state that is hard to recover after stop/restart
  - model naming/output-path behavior that feels wrong in normal use
- After the dogfooding pass, only then decide whether the next work is:
  - controller regression tests
  - queue UX cleanup
  - config replay narrowing
- Add controller-focused regression tests for synchronous load readiness wait.
- Add controller-focused regression tests for terminal training detection without hook delivery.
- Add controller-focused regression tests for preserved-model restore on second job start.
- Re-run the two-job GUI MCP acceptance flow after controller changes.
- Stress-test longer queues and larger datasets.
- If config replay causes future parameter mismatches, narrow `_apply_job_config(job)` separately.
- If viewport snapshots are needed later, prefer dataset-camera render paths over `render/current` until the upstream crash is resolved.
