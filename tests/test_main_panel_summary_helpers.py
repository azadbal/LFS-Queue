from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path


class MainPanelSummaryHelperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self._saved_modules: dict[str, object | None] = {}
        self._install_stub(
            "lichtfeld",
            self._make_fake_lichtfeld(),
        )
        self._install_stub(
            "lfs_queue",
            self._make_package("lfs_queue", self.repo_root),
        )
        self._install_stub(
            "lfs_queue.panels",
            self._make_package("lfs_queue.panels", self.repo_root / "panels"),
        )
        queue_controller = types.ModuleType("lfs_queue.queue_controller")
        queue_controller.get_controller = lambda: None
        self._install_stub("lfs_queue.queue_controller", queue_controller)

        module_name = "lfs_queue.panels.main_panel"
        spec = importlib.util.spec_from_file_location(module_name, self.repo_root / "panels" / "main_panel.py")
        if spec is None or spec.loader is None:
            raise RuntimeError("Unable to load main_panel.py for testing.")
        module = importlib.util.module_from_spec(spec)
        self._install_stub(module_name, module)
        spec.loader.exec_module(module)
        self.main_panel = module

    def tearDown(self) -> None:
        for name, previous in reversed(list(self._saved_modules.items())):
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous

    def _install_stub(self, name: str, module: object) -> None:
        if name not in self._saved_modules:
            self._saved_modules[name] = sys.modules.get(name)
        sys.modules[name] = module

    def _make_package(self, name: str, path: Path) -> types.ModuleType:
        module = types.ModuleType(name)
        module.__path__ = [str(path)]
        return module

    def _make_fake_lichtfeld(self) -> types.ModuleType:
        module = types.ModuleType("lichtfeld")
        module.ui = types.SimpleNamespace(
            Panel=type("Panel", (), {}),
            PanelSpace=types.SimpleNamespace(MAIN_PANEL_TAB="main_panel_tab"),
        )
        return module

    def test_flags_render_double_dash_when_none_are_enabled(self) -> None:
        job = types.SimpleNamespace(
            config_json={"optimization": {"iterations": 300, "strategy": "mrnf", "max_cap": 1000000}}
        )

        self.assertEqual(self.main_panel._job_flags_text(job), "--")
        self.assertEqual(
            self.main_panel._job_compact_summary(job),
            "iters 300 | MRNF | max 1,000,000 | flags --",
        )

    def test_flags_include_enabled_labels_in_stable_order(self) -> None:
        job = types.SimpleNamespace(
            config_json={
                "optimization": {
                    "use_bilateral_grid": True,
                    "undistort": True,
                    "ppisp": True,
                    "ppisp_use_controller": True,
                    "ppisp_freeze_gaussians": True,
                    "revised_opacity": True,
                    "enable_sparsity": True,
                    "mip_filter": True,
                }
            }
        )

        self.assertEqual(
            self.main_panel._job_enabled_flags(job),
            [
                "Bilateral Grid",
                "Undistort",
                "PPISP",
                "PPISP Controller",
                "Freeze Gaussians",
                "Revised Opacity",
                "Sparsity",
                "MIP",
            ],
        )

    def test_missing_summary_values_fall_back_to_double_dash(self) -> None:
        job = types.SimpleNamespace(config_json={"optimization": {}})

        self.assertEqual(self.main_panel._job_iterations(job), "--")
        self.assertEqual(self.main_panel._job_strategy(job), "--")
        self.assertEqual(self.main_panel._job_max_gaussians(job), "--")

    def test_row_text_uses_single_summary_line(self) -> None:
        job = types.SimpleNamespace(
            label="model-2",
            status="pending",
            config_json={"optimization": {"iterations": 450, "strategy": "igs+", "max_cap": 250000, "undistort": True}},
        )

        self.assertEqual(
            self.main_panel._job_row_text(job, 2, is_selected=True, is_editing=False),
            "[selected] 2. model-2 | pending | iters 450 | IGS+ | max 250,000 | flags Undistort",
        )


if __name__ == "__main__":
    unittest.main()
