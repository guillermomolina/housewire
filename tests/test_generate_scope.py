"""Generate scopes to the given directory tree (no multi-zone discovery)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from housewire.cli import resolve_inputs, run_generate_project
from housewire.project.io import create_location_index


class TestGenerateScope(unittest.TestCase):
    def test_subtree_only_collects_descendant_yamls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "MyHouse"
            root.mkdir()
            create_location_index(root, type_id="House", label="House")
            parking = root / "Parking"
            create_location_index(parking, type_id="Floor", label="Parking")
            create_location_index(
                parking / "Box_1", type_id="JunctionBox", label="Box 1"
            )
            create_location_index(
                root / "Planta_baja", type_id="Floor", label="Planta baja"
            )

            parking_out = (parking / "out").resolve()
            parking_files = resolve_inputs(parking, None, parking_out)
            self.assertEqual(len(parking_files), 2)
            self.assertTrue(all(str(p).startswith(str(parking)) for p in parking_files))

            root_out = (root / "out").resolve()
            all_files = resolve_inputs(root, None, root_out)
            self.assertGreater(len(all_files), len(parking_files))

    def test_run_generate_writes_out_under_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "MyHouse"
            root.mkdir()
            create_location_index(root, type_id="House", label="House")
            parking = root / "Parking"
            create_location_index(parking, type_id="Floor", label="Parking")

            with (
                mock.patch("housewire.cli.run_wireviz"),
                mock.patch("housewire.cli.export_physical_zone"),
                mock.patch("housewire.cli.write_and_render_wireviz") as write_wv,
            ):
                code = run_generate_project(parking, force=True)

            self.assertEqual(code, 0)
            write_wv.assert_called_once()
            args = write_wv.call_args
            self.assertEqual(args.args[0], parking)
            self.assertEqual(args.args[2], (parking / "out").resolve())
            self.assertTrue(args.kwargs.get("with_stubs"))
