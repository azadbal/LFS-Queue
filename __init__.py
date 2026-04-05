"""lfs_queue - queue multiple Lift Studio training variants from one dataset."""

from __future__ import annotations

import lichtfeld as lf

from .panels.main_panel import QueuePanel
from .queue_mcp import register_tools, unregister_tools
from .queue_controller import get_controller, shutdown_controller


_classes = [QueuePanel]


def on_load() -> None:
    get_controller()
    register_tools()
    for cls in _classes:
        lf.register_class(cls)
    lf.log.info("lfs_queue loaded")


def on_unload() -> None:
    shutdown_controller()
    unregister_tools()
    for cls in reversed(_classes):
        lf.unregister_class(cls)
    lf.log.info("lfs_queue unloaded")
