from __future__ import annotations

import unittest

from queue_core import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_INTERRUPTED,
    STATUS_PENDING,
    build_runtime_state,
    QueueJob,
    classify_training_end,
    deserialize_queue_state,
    find_next_runnable_job_index,
    is_terminal_trainer_state,
    is_trainer_ready_state,
    make_job_output_dir,
    next_model_name,
    sanitize_label,
    serialize_queue_state,
    should_finalize_training_end,
)


class QueueCoreTests(unittest.TestCase):
    def test_sanitize_label_replaces_windows_unsafe_characters(self) -> None:
        self.assertEqual(sanitize_label("model: 1 / draft"), "model_1_draft")

    def test_next_model_name_uses_highest_existing_suffix(self) -> None:
        self.assertEqual(next_model_name(["model 1", "Model 3", "variant"]), "model 4")

    def test_make_job_output_dir_avoids_existing_queue_paths(self) -> None:
        output_dir = make_job_output_dir(
            "C:\\output",
            "model 1",
            existing_paths=[],
            path_exists=lambda path: str(path).endswith("model_1"),
        )

        self.assertTrue(output_dir.endswith("model_1_2"))

    def test_queue_state_round_trip_converts_transient_statuses(self) -> None:
        job = QueueJob.new(
            label="model 1",
            dataset_path="C:\\dataset",
            base_output_dir="C:\\output",
            job_output_dir="C:\\output\\queue\\model_1",
            created_at="2026-03-29T00:00:00+00:00",
            config_json={"optimization": {"iterations": 1000}},
            dataset_overrides={"resize_factor": 2},
        )
        job.status = "training"

        restored = deserialize_queue_state(serialize_queue_state([job]))

        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0].status, STATUS_INTERRUPTED)

    def test_find_next_runnable_job_index_skips_completed_jobs(self) -> None:
        jobs = [
            QueueJob.from_dict({"label": "model 1", "model_name": "model 1", "status": STATUS_COMPLETED}),
            QueueJob.from_dict({"label": "model 2", "model_name": "model 2", "status": STATUS_PENDING}),
        ]

        self.assertEqual(find_next_runnable_job_index(jobs), 1)

    def test_classify_training_end_handles_success_failure_and_interrupt(self) -> None:
        success = classify_training_end(None, None, stop_requested=False, auto_run=True)
        failure = classify_training_end("failed", "CUDA out of memory", stop_requested=False, auto_run=True)
        stopped = classify_training_end("stopped", None, stop_requested=False, auto_run=True)

        self.assertEqual(success.status, STATUS_COMPLETED)
        self.assertTrue(success.continue_queue)
        self.assertEqual(failure.status, STATUS_FAILED)
        self.assertTrue(failure.continue_queue)
        self.assertEqual(stopped.status, STATUS_INTERRUPTED)
        self.assertFalse(stopped.continue_queue)

    def test_is_trainer_ready_state_accepts_explicit_ready_state(self) -> None:
        self.assertTrue(is_trainer_ready_state(has_trainer=True, trainer_state="ready"))
        self.assertTrue(is_trainer_ready_state(has_trainer=True, trainer_state="IDLE"))
        self.assertTrue(is_trainer_ready_state(has_trainer=False, trainer_state="ready"))
        self.assertTrue(is_trainer_ready_state(has_trainer=False, trainer_state="idle"))
        self.assertFalse(is_trainer_ready_state(has_trainer=True, trainer_state="running"))
        self.assertFalse(is_trainer_ready_state(has_trainer=False, trainer_state=""))

    def test_is_terminal_trainer_state_matches_completed_stopped_and_error(self) -> None:
        self.assertTrue(is_terminal_trainer_state("completed"))
        self.assertTrue(is_terminal_trainer_state("STOPPED"))
        self.assertTrue(is_terminal_trainer_state("error"))
        self.assertFalse(is_terminal_trainer_state("ready"))

    def test_should_finalize_training_end_detects_terminal_completion_without_start_hook(self) -> None:
        self.assertTrue(
            should_finalize_training_end(
                trainer_state="completed",
                trainer_error=None,
                finish_reason="",
                finish_reason_baseline="",
            )
        )
        self.assertTrue(
            should_finalize_training_end(
                trainer_state="idle",
                trainer_error=None,
                finish_reason="completed",
                finish_reason_baseline="",
            )
        )
        self.assertFalse(
            should_finalize_training_end(
                trainer_state="idle",
                trainer_error=None,
                finish_reason="completed",
                finish_reason_baseline="completed",
            )
        )
        self.assertFalse(
            should_finalize_training_end(
                trainer_state="running",
                trainer_error=None,
                finish_reason="",
                finish_reason_baseline="",
            )
        )

    def test_build_runtime_state_includes_runtime_metadata(self) -> None:
        job = QueueJob.from_dict({"label": "model 1", "model_name": "model 1", "status": STATUS_PENDING})

        state = build_runtime_state(
            [job],
            status_message="Queue ready.",
            active_job_id=job.id,
            phase="loading",
            auto_run=True,
            is_running=True,
            debug_event_count=7,
        )

        self.assertEqual(state["version"], 1)
        self.assertEqual(state["status_message"], "Queue ready.")
        self.assertEqual(state["active_job_id"], job.id)
        self.assertEqual(state["phase"], "loading")
        self.assertTrue(state["auto_run"])
        self.assertTrue(state["is_running"])
        self.assertEqual(state["debug_event_count"], 7)
        self.assertEqual(len(state["jobs"]), 1)


if __name__ == "__main__":
    unittest.main()
