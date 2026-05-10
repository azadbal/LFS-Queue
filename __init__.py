"""lfs_queue - queue multiple Lift Studio training variants from one dataset."""

from __future__ import annotations

import os

import lichtfeld as lf

from .panels.main_panel import QueuePanel
from .queue_controller import get_controller, shutdown_controller


_classes = [QueuePanel]


def on_load() -> None:
    get_controller()
    for cls in _classes:
        lf.register_class(cls)
    lf.log.info("lfs_queue loaded")
    if os.environ.get("LFS_QUEUE_AUTORUN_VERIFY"):
        from .queue_live_verify import start_autorun_verify

        start_autorun_verify()


def on_unload() -> None:
    shutdown_controller()
    for cls in reversed(_classes):
        lf.unregister_class(cls)
    lf.log.info("lfs_queue unloaded")
