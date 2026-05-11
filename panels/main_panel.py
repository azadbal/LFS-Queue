"""Immediate-mode queue management panel for LFS Queue."""

from __future__ import annotations

import lichtfeld as lf

from ..queue_controller import get_controller


COMPACT_PANEL_WIDTH = 1120.0
FLAG_SPECS = (
    ("Bilateral Grid", ("use_bilateral_grid",)),
    ("Undistort", ("undistort",)),
    ("PPISP", ("use_ppisp", "ppisp")),
    ("PPISP Controller", ("ppisp_use_controller",)),
    ("Freeze Gaussians", ("ppisp_freeze_gaussians_on_distill", "ppisp_freeze_gaussians")),
    ("Revised Opacity", ("revised_opacity",)),
    ("Sparsity", ("enable_sparsity",)),
    ("MIP", ("mip_filter",)),
)


def _truncate_middle(text: str, max_chars: int) -> str:
    value = str(text or "")
    if max_chars <= 0:
        return ""
    if len(value) <= max_chars:
        return value
    if max_chars <= 3:
        return value[:max_chars]

    keep = max_chars - 3
    left = max(1, keep // 2)
    right = max(1, keep - left)
    return f"{value[:left]}...{value[-right:]}"


def _job_optimization(job) -> dict:
    config_json = getattr(job, "config_json", {}) or {}
    optimization = config_json.get("optimization") or {}
    return optimization if isinstance(optimization, dict) else {}


def _job_setting(optimization: dict, *keys: str):
    for key in keys:
        if key in optimization:
            return optimization.get(key)
    return None


def _format_int(value) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "--"


def _format_strategy(value) -> str:
    strategy = str(value or "").strip()
    return strategy.upper() if strategy else "--"


def _job_iterations(job) -> str:
    return _format_int(_job_setting(_job_optimization(job), "iterations"))


def _job_strategy(job) -> str:
    return _format_strategy(_job_setting(_job_optimization(job), "strategy"))


def _job_max_gaussians(job) -> str:
    return _format_int(_job_setting(_job_optimization(job), "max_cap"))


def _job_enabled_flags(job) -> list[str]:
    optimization = _job_optimization(job)
    enabled: list[str] = []
    for label, keys in FLAG_SPECS:
        value = _job_setting(optimization, *keys)
        if bool(value):
            enabled.append(label)
    return enabled


def _job_flags_text(job) -> str:
    flags = _job_enabled_flags(job)
    return " | ".join(flags) if flags else "--"


def _job_compact_summary(job) -> str:
    flags_text = _job_flags_text(job)
    return (
        f"iters {_job_iterations(job)} | "
        f"{_job_strategy(job)} | "
        f"max {_job_max_gaussians(job)} | "
        f"flags {flags_text}"
    )


def _job_row_text(job, index: int, *, is_selected: bool, is_editing: bool) -> str:
    prefix = f"{index}. {job.label}"
    if is_selected:
        prefix = f"[selected] {prefix}"
    if is_editing:
        prefix += " [editing]"
    return f"{prefix} | {job.status} | {_job_compact_summary(job)}"


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

        ui.heading("LFS Queue")
        ui.text_disabled("Queue the current training-ready LFS state as separate model outputs.")
        self._draw_truncated_text(ui, controller.status_message, max_chars=90, tooltip=controller.status_message)
        ui.separator()

        self._draw_actions(ui, controller)
        ui.separator()
        self._draw_queue_rows(ui, controller)

    def _draw_actions(self, ui, controller) -> None:
        selected_job = controller.selected_job
        is_editing_selected = bool(selected_job is not None and controller.editing_job is not None and controller.editing_job.id == selected_job.id)

        add_disabled = controller.is_running or controller.is_editing or not controller.can_add_current_job()
        ui.begin_disabled(add_disabled)
        if ui.button("Add to Queue", (-1, 0)):
            controller.add_current_job()
        ui.end_disabled()
        if controller.is_editing:
            ui.text_disabled("Editing a selected job. Click Save to overwrite it.")
        elif add_disabled and not controller.is_running:
            ui.text_disabled("Available when LFS Start Training is available.")

        ui.begin_disabled(controller.is_running)
        if ui.button("Run Queue", (-1, 0)):
            controller.run_all_pending()
        ui.end_disabled()

        ui.begin_disabled(controller.is_running)
        if ui.button("Clear Queue", (-1, 0)):
            controller.clear_queue()
        ui.end_disabled()

        if selected_job is not None:
            detail = f"Selected job: {selected_job.label}"
            if is_editing_selected:
                detail += " (editing)"
            ui.text_disabled(detail)
            self._draw_selected_job_details(ui, selected_job)
            self._draw_selected_job_actions(ui, controller, is_editing_selected=is_editing_selected)

    def _draw_queue_rows(self, ui, controller) -> None:
        jobs = controller.jobs
        ui.heading(f"Queue ({len(jobs)})")
        if not jobs:
            ui.text_disabled("Add the current settings to start building the queue.")
            return

        panel_width, _ = ui.get_content_region_avail()
        max_chars = max(40, int(panel_width / 6.5))
        if panel_width >= COMPACT_PANEL_WIDTH:
            ui.text_disabled("Job | Status | Iterations | Strategy | Max Gaussians | Flags")
        else:
            ui.text_disabled("Job | Status | Summary")

        for index, job in enumerate(jobs, start=1):
            is_selected = controller.selected_job is not None and controller.selected_job.id == job.id
            is_editing = controller.editing_job is not None and controller.editing_job.id == job.id
            row_text = _job_row_text(job, index, is_selected=is_selected, is_editing=is_editing)
            display_text = _truncate_middle(row_text, max_chars)
            if ui.selectable(display_text, is_selected):
                controller.select_job(None if is_selected else job.id)
            if row_text != display_text and ui.is_item_hovered():
                ui.set_tooltip(row_text)

    def _draw_selected_job_details(self, ui, job) -> None:
        flags_text = _job_flags_text(job)
        ui.text_disabled("Iterations")
        ui.label(_job_iterations(job))
        ui.text_disabled("Strategy")
        ui.label(_job_strategy(job))
        ui.text_disabled("Max Gaussians")
        ui.label(_job_max_gaussians(job))
        ui.text_disabled("Flags")
        self._draw_truncated_text(ui, flags_text, max_chars=120, tooltip=flags_text)
        ui.text_disabled("Queue output")
        self._draw_truncated_text(ui, job.job_output_dir, max_chars=120, tooltip=job.job_output_dir)
        ui.text_disabled("Dataset")
        self._draw_truncated_text(ui, job.dataset_path, max_chars=120, tooltip=job.dataset_path)
        if job.error:
            ui.text_disabled("Error")
            self._draw_truncated_text(ui, job.error, max_chars=120, tooltip=job.error)

    def _draw_selected_job_actions(self, ui, controller, *, is_editing_selected: bool) -> None:
        selected_job = controller.selected_job
        if selected_job is None:
            return

        ui.separator()

        ui.begin_disabled(not controller.can_save_selected_job())
        if ui.button("Save Selected Job", (-1, 0)):
            controller.save_selected_job()
        ui.end_disabled()

        ui.begin_disabled(controller.is_running)
        if ui.button("Cancel Edit" if is_editing_selected else "Edit Selected Job", (-1, 0)):
            if is_editing_selected:
                controller.cancel_edit()
            else:
                controller.begin_edit_selected_job()
        ui.end_disabled()

        ui.begin_disabled(not controller.can_remove_selected_job())
        if ui.button("Remove Selected Job", (-1, 0)):
            controller.delete_selected_job()
        ui.end_disabled()

    def _draw_truncated_cell(self, ui, text: str, *, tooltip: str) -> None:
        width, _ = ui.get_content_region_avail()
        max_chars = max(18, int(width / 7.0))
        self._draw_truncated_text(ui, text, max_chars=max_chars, tooltip=tooltip)

    def _draw_truncated_text(self, ui, text: str, *, max_chars: int, tooltip: str) -> None:
        display = _truncate_middle(text, max_chars)
        ui.label(display)
        if tooltip and display != tooltip and ui.is_item_hovered():
            ui.set_tooltip(tooltip)
