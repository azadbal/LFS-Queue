"""No-MCP command helpers for driving LFS Queue from scripts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_FIXTURE_ROOT = Path(r"C:\Dev\3DGS\_example_datasets\COLMAP-ready-datasets")


def discover_colmap_fixtures(root: str | Path = DEFAULT_FIXTURE_ROOT) -> list[str]:
    root_path = Path(root)
    if not root_path.exists():
        return []
    return sorted(str(path) for path in root_path.glob("*/*") if path.is_dir() and path.name.lower() == "colmap")


def _controller():
    try:
        from .queue_controller import get_controller
    except ImportError:
        from queue_controller import get_controller
    return get_controller()


def _print_json(payload: dict[str, Any]) -> int:
    print(json.dumps(payload, indent=2, default=str))
    return 0


def _cmd_fixtures(args: argparse.Namespace) -> int:
    return _print_json({"fixtures": discover_colmap_fixtures(args.root)})


def _cmd_state(_args: argparse.Namespace) -> int:
    return _print_json(_controller().export_state())


def _cmd_add_current(_args: argparse.Namespace) -> int:
    controller = _controller()
    ok = controller.add_current_job()
    return _print_json({"ok": ok, "state": controller.export_state()})


def _cmd_run_all(_args: argparse.Namespace) -> int:
    controller = _controller()
    ok = controller.run_all_pending()
    return _print_json({"ok": ok, "state": controller.export_state()})


def _cmd_clear(_args: argparse.Namespace) -> int:
    controller = _controller()
    removed = controller.clear_queue()
    return _print_json({"removed": removed, "state": controller.export_state()})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="No-MCP helpers for LFS Queue.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fixtures = subparsers.add_parser("fixtures", help="List local ready COLMAP fixtures.")
    fixtures.add_argument("--root", default=str(DEFAULT_FIXTURE_ROOT))
    fixtures.set_defaults(func=_cmd_fixtures)

    state = subparsers.add_parser("state", help="Print current queue state. Requires LFS Python.")
    state.set_defaults(func=_cmd_state)

    add_current = subparsers.add_parser("add-current", help="Queue the current LFS training-ready state.")
    add_current.set_defaults(func=_cmd_add_current)

    run_all = subparsers.add_parser("run-all", help="Run all pending queue jobs.")
    run_all.set_defaults(func=_cmd_run_all)

    clear = subparsers.add_parser("clear", help="Clear the session queue.")
    clear.set_defaults(func=_cmd_clear)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
