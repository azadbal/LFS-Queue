from __future__ import annotations

import importlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path


class _Settings:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    def get(self, key: str, default: object = None) -> object:
        return self.values.get(key, default)

    def set(self, key: str, value: object) -> None:
        self.values[key] = value


class _ScopedHandler:
    def __init__(self) -> None:
        self.training_start = None
        self.training_end = None

    def on_training_start(self, callback) -> None:
        self.training_start = callback

    def on_training_end(self, callback) -> None:
        self.training_end = callback

    def clear(self) -> None:
        pass


class _Dataset:
    def __init__(self, output_path: str) -> None:
        self.data_path = r"C:\dataset\colmap"
        self.output_path = output_path
        self.resize_factor = 1
        self.max_width = 0
        self.use_cpu_cache = False
        self.use_fs_cache = False


class _Optimization:
    iterations = 10

    def has_params(self) -> bool:
        return True

    def validate(self) -> str:
        return ""


class FakeLichtfeld(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("lichtfeld")
        self.output_root = tempfile.TemporaryDirectory()
        self.dataset = _Dataset(str(Path(self.output_root.name) / "output"))
        self.optimization = _Optimization()
        self.training_starts = 0
        self.load_file_calls = 0
        self.remove_node_calls = []
        self.mcp_reads = 0
        self.reset_training_calls = 0
        self.has_trainer_value = True
        self.trainer_state_value = "ready"
        self.finish_reason_value = ""
        self.trainer_error_value = ""
        self.plugins = types.SimpleNamespace(settings=lambda _plugin_id: _Settings())
        self.log = types.SimpleNamespace(info=lambda _msg: None, error=lambda _msg: None)
        self.ui = types.SimpleNamespace(request_redraw=lambda: None)
        self.scene = types.SimpleNamespace(NodeType=types.SimpleNamespace(SPLAT="splat"))
        self.io = types.SimpleNamespace(save_ply=lambda _data, path: Path(path).write_text("ply", encoding="utf-8"))
        self.BackgroundMode = types.SimpleNamespace()
        self.MaskMode = types.SimpleNamespace()
        self.mcp = types.SimpleNamespace(read_resource=self._read_resource)
        self._handler = _ScopedHandler()

    def _read_resource(self, _uri: str):
        self.mcp_reads += 1
        raise AssertionError("MCP must not be used by the active queue path")

    def ScopedHandler(self) -> _ScopedHandler:
        return self._handler

    def save_config_file(self, path: str) -> None:
        Path(path).write_text(json.dumps({"optimization": {"iterations": self.optimization.iterations}}), encoding="utf-8")

    def dataset_params(self) -> _Dataset:
        return self.dataset

    def optimization_params(self) -> _Optimization:
        return self.optimization

    def has_scene(self) -> bool:
        return True

    def has_trainer(self) -> bool:
        return self.has_trainer_value

    def trainer_state(self) -> str:
        return self.trainer_state_value

    def finish_reason(self) -> str:
        return self.finish_reason_value

    def trainer_error(self) -> str:
        return self.trainer_error_value

    def context(self):
        return types.SimpleNamespace(is_training=False)

    def start_training(self) -> None:
        self.training_starts += 1
        self.trainer_state_value = "running"

    def stop_training(self) -> None:
        pass

    def reset_training(self) -> None:
        self.reset_training_calls += 1
        self.trainer_state_value = "ready"

    def load_file(self, *_args, **_kwargs) -> None:
        self.load_file_calls += 1
        raise AssertionError("Queue jobs must use the active LFS dataset, not reload via load_file")

    def remove_node(self, name: str, keep_children: bool = False) -> None:
        self.remove_node_calls.append((name, keep_children))

    def get_scene(self):
        return types.SimpleNamespace(
            training_model_node_name="Model",
            get_node=lambda _name: types.SimpleNamespace(splat_data=lambda: object()),
            get_nodes=lambda: [],
        )


class QueueControllerNoMcpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fake_lf = FakeLichtfeld()
        sys.modules["lichtfeld"] = self.fake_lf
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        sys.modules.pop("queue_controller", None)
        self.queue_controller = importlib.import_module("queue_controller")

    def tearDown(self) -> None:
        self.fake_lf.output_root.cleanup()
        sys.modules.pop("queue_controller", None)
        try:
            sys.path.remove(str(Path(__file__).resolve().parents[1]))
        except ValueError:
            pass

    def test_add_current_job_is_blocked_when_native_start_is_not_ready(self) -> None:
        self.fake_lf.trainer_state_value = "running"
        controller = self.queue_controller.QueueController()

        self.assertFalse(controller.can_add_current_job())
        self.assertFalse(controller.add_current_job())
        self.assertEqual(controller.jobs, [])
        self.assertEqual(self.fake_lf.mcp_reads, 0)

    def test_run_selected_uses_active_dataset_without_mcp_or_load_file(self) -> None:
        controller = self.queue_controller.QueueController()

        self.assertTrue(controller.add_current_job())
        self.assertTrue(controller.run_selected(controller.jobs[0].id))

        self.assertEqual(controller.jobs[0].label, "model-1")
        self.assertTrue(controller.jobs[0].job_output_dir.replace("/", "\\").endswith(r"queue\model-1"))
        self.assertTrue(self.fake_lf.dataset.output_path.replace("/", "\\").endswith(r"output"))
        self.assertEqual(self.fake_lf.training_starts, 1)
        self.assertEqual(self.fake_lf.load_file_calls, 0)
        self.assertEqual(self.fake_lf.mcp_reads, 0)

    def test_auto_run_resets_before_advancing_after_finished_state(self) -> None:
        controller = self.queue_controller.QueueController()
        self.assertTrue(controller.add_current_job())
        self.fake_lf.trainer_state_value = "ready"
        self.assertTrue(controller.add_current_job())

        self.assertTrue(controller.run_all_pending())
        first_job = controller.jobs[0]
        self.fake_lf.trainer_state_value = "finished"
        self.fake_lf.finish_reason_value = "completed"
        controller._poll_training_state(first_job)

        self.assertEqual(self.fake_lf.reset_training_calls, 1)
        self.assertEqual(controller.jobs[0].status, "completed")
        self.assertEqual(controller.jobs[1].status, "pending")

    def test_completed_job_claims_checkpoint_and_removes_ambiguous_native_splat(self) -> None:
        controller = self.queue_controller.QueueController()
        self.assertTrue(controller.add_current_job())
        job = controller.jobs[0]
        self.assertTrue(controller.run_selected(job.id))

        base_output = Path(job.base_output_dir)
        checkpoints = base_output / "checkpoints"
        checkpoints.mkdir(parents=True, exist_ok=True)
        native_splat = base_output / "splat_300.ply"
        native_checkpoint = checkpoints / "checkpoint.resume"
        native_splat.write_text("native ply", encoding="utf-8")
        native_checkpoint.write_text("checkpoint", encoding="utf-8")

        self.fake_lf.trainer_state_value = "finished"
        self.fake_lf.finish_reason_value = "completed"
        controller._poll_training_state(job)

        self.assertEqual(job.status, "completed")
        self.assertFalse(native_splat.exists())
        self.assertFalse(native_checkpoint.exists())
        self.assertTrue((Path(job.job_output_dir) / "model-1.ply").exists())
        self.assertTrue((Path(job.job_output_dir) / "checkpoints" / "checkpoint.resume").exists())


if __name__ == "__main__":
    unittest.main()
