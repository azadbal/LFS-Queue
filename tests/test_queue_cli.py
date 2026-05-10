from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from queue_cli import discover_colmap_fixtures


class QueueCliTests(unittest.TestCase):
    def test_discover_colmap_fixtures_finds_one_level_nested_colmap_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scene-a" / "colmap").mkdir(parents=True)
            (root / "scene-b" / "not-colmap").mkdir(parents=True)
            (root / "scene-c" / "COLMAP").mkdir(parents=True)

            fixtures = discover_colmap_fixtures(root)

        normalized = [Path(path).name.lower() for path in fixtures]
        self.assertEqual(normalized, ["colmap", "colmap"])
        self.assertEqual(len(fixtures), 2)


if __name__ == "__main__":
    unittest.main()
