"""Immediate-mode queue management panel for LFS Queue."""

from __future__ import annotations

import lichtfeld as lf

from ..queue_controller import get_controller


class QueuePanel(lf.ui.Panel):
    """Main queue panel for snapshotting and replaying training configs."""

    id = "lfs_queue.main_panel"
    label = "LFS Queue"
    space = lf.ui.PanelSpace.MAIN_PANEL_TAB
    order = 100

    def __init__(self) -> None:
        self._controller = get_controller()

    def draw(self, ui) -> None:
        controller = self._controller
        jobs = controller.jobs

        ui.heading("LFS Queue")
        ui.text_disabled("Queue the current training-ready LFS state as separate model outputs.")
        ui.text_wrapped(controller.status_message)
        ui.separator()

        self._draw_actions(ui, controller)
        ui.separator()
        self._draw_queue_table(ui, controller)

    def _draw_actions(self, ui, controller) -> None:
        add_disabled = controller.is_running or not controller.can_add_current_job()
        ui.begin_disabled(add_disabled)
        if ui.button("Add to Queue", (-1, 0)):
            controller.add_current_job()
        ui.end_disabled()
        if add_disabled and not controller.is_running:
            ui.text_disabled("Available when LFS Start Training is available.")

        ui.begin_disabled(controller.is_running)
        if ui.button("Run Queue", (-1, 0)):
            controller.run_all_pending()
        ui.end_disabled()

        ui.begin_disabled(controller.is_running)
        if ui.button("Clear Queue", (-1, 0)):
            controller.clear_queue()
        ui.end_disabled()

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
                ui.text(f"{index}. {job.label}")

                ui.table_set_column_index(1)
                ui.text_disabled(job.status)

                ui.table_set_column_index(2)
                ui.text_wrapped(job.job_output_dir)

                ui.table_set_column_index(3)
                ui.text_wrapped(job.error or job.dataset_path)

            ui.end_table()
