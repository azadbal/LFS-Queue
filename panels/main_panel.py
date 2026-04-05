"""Immediate-mode queue management panel for LFS Queue."""

from __future__ import annotations

import lichtfeld as lf

from ..queue_controller import get_controller
from ..queue_core import STATUS_COMPLETED


class QueuePanel(lf.ui.Panel):
    """Main queue panel for snapshotting and replaying training configs."""

    id = "lfs_queue.main_panel"
    label = "LFS Queue"
    space = lf.ui.PanelSpace.MAIN_PANEL_TAB
    order = 100
    debug_marker = "HI - LFS QUEUE LIVE CODE"

    def __init__(self) -> None:
        self._controller = get_controller()
        self._selected_job_id: str | None = None
        self._label_input = ""

    def draw(self, ui) -> None:
        controller = self._controller
        jobs = controller.jobs
        selected_job = controller.get_job_by_id(self._selected_job_id)
        if selected_job is None and jobs:
            self._selected_job_id = jobs[0].id
            selected_job = jobs[0]
            self._label_input = selected_job.label

        self._draw_debug_marker(ui)
        ui.heading("LFS Queue")
        ui.text_disabled("Snapshot the current dataset and current training settings into queue jobs.")
        ui.text_wrapped(controller.status_message)
        ui.separator()

        self._draw_actions(ui, controller, selected_job)
        ui.separator()
        self._draw_selected_job_editor(ui, controller, selected_job)
        ui.separator()
        self._draw_queue_table(ui, controller)

    def _draw_debug_marker(self, ui) -> None:
        ui.text_colored(self.debug_marker, (1.0, 1.0, 0.0, 1.0))
        ui.push_style_var_vec2("FramePadding", (24.0, 24.0))
        ui.push_style_color("Button", (1.0, 1.0, 0.0, 1.0))
        ui.push_style_color("ButtonHovered", (1.0, 0.95, 0.2, 1.0))
        ui.push_style_color("ButtonActive", (0.95, 0.85, 0.0, 1.0))
        ui.push_style_color("Text", (0.05, 0.05, 0.05, 1.0))
        ui.button("HI", (-1, 72))
        ui.pop_style_color(4)
        ui.pop_style_var()
        ui.separator()

    def _draw_actions(self, ui, controller, selected_job) -> None:
        if ui.button("Add Current", (-1, 0)):
            if controller.add_current_job():
                last_job = controller.jobs[-1]
                self._selected_job_id = last_job.id
                self._label_input = last_job.label

        ui.begin_disabled(selected_job is None or controller.is_running)
        if ui.button("Run Selected", (-1, 0)) and selected_job is not None:
            controller.run_selected(selected_job.id)
        ui.end_disabled()

        ui.begin_disabled(controller.is_running)
        if ui.button("Run All Pending", (-1, 0)):
            controller.run_all_pending()
        ui.end_disabled()

        ui.begin_disabled(not controller.is_running)
        if ui.button("Stop Queue", (-1, 0)):
            controller.stop_queue()
        ui.end_disabled()

        ui.begin_disabled(selected_job is None or controller.is_running)
        if ui.button("Move Up", (-1, 0)) and selected_job is not None:
            controller.move_job(selected_job.id, -1)
        if ui.button("Move Down", (-1, 0)) and selected_job is not None:
            controller.move_job(selected_job.id, 1)
        if ui.button("Delete", (-1, 0)) and selected_job is not None:
            deleted_id = selected_job.id
            controller.delete_job(deleted_id)
            if self._selected_job_id == deleted_id:
                self._selected_job_id = None
                self._label_input = ""
        ui.end_disabled()

        if ui.button("Clear Finished/Failed", (-1, 0)):
            controller.clear_finished_and_failed()
            if controller.get_job_by_id(self._selected_job_id) is None:
                self._selected_job_id = None
                self._label_input = ""

        ui.begin_disabled(controller.is_running)
        if ui.button("Clear Queue", (-1, 0)):
            controller.clear_queue()
            self._selected_job_id = None
            self._label_input = ""
        ui.end_disabled()

    def _draw_selected_job_editor(self, ui, controller, selected_job) -> None:
        ui.heading("Selected Job")
        if selected_job is None:
            ui.text_disabled("No queue jobs yet. Queue entries are session-only.")
            return

        if self._label_input != selected_job.label:
            self._label_input = selected_job.label

        changed, new_label = ui.input_text_with_hint("Model Name", "model 1", self._label_input)
        if changed:
            self._label_input = new_label
            controller.update_job_label(selected_job.id, new_label)

        ui.text_disabled(f"Status: {selected_job.status}")
        ui.text_disabled(f"Dataset: {selected_job.dataset_path}")
        ui.text_disabled(f"Output: {selected_job.job_output_dir}")
        if selected_job.error:
            ui.text_wrapped(f"Last error: {selected_job.error}")
        elif selected_job.status == STATUS_COMPLETED:
            ui.text_disabled("Completed models stay in-scene under the configured model name.")

    def _draw_queue_table(self, ui, controller) -> None:
        jobs = controller.jobs
        ui.heading(f"Queue ({len(jobs)})")
        if not jobs:
            ui.text_disabled("Add the current settings to start building the queue.")
            return

        if ui.begin_table("lfs_queue.jobs", 4):
            ui.table_setup_column("Model")
            ui.table_setup_column("Status", 90.0)
            ui.table_setup_column("Output", 220.0)
            ui.table_setup_column("Notes")
            ui.table_headers_row()

            for index, job in enumerate(jobs, start=1):
                ui.table_next_row()

                ui.table_set_column_index(0)
                selected = job.id == self._selected_job_id
                if ui.selectable(f"{index}. {job.label}", selected):
                    self._selected_job_id = job.id
                    self._label_input = job.label

                ui.table_set_column_index(1)
                ui.text_disabled(job.status)

                ui.table_set_column_index(2)
                ui.text_wrapped(job.job_output_dir)

                ui.table_set_column_index(3)
                ui.text_wrapped(job.error or job.dataset_path)

            ui.end_table()
