"""Generate scopes to the given directory tree (single site YAML)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fixtures import add_place, init_site, save_site
from housewire.cli import resolve_inputs, run_generate_project
from housewire.project.io import HOUSEWIRE_YAML


class TestGenerateScope(unittest.TestCase):
    def test_site_root_collects_single_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "MyHouse"
            root.mkdir()
            doc = init_site(root, type_id="House", label="House")
            add_place(doc, "Parking", type_id="Floor", label="Parking")
            add_place(
                doc, "Box_1", under=("Parking",), type_id="JunctionBox", label="Box 1"
            )
            add_place(doc, "Planta_baja", type_id="Floor", label="Planta baja")
            save_site(root, doc)

            root_out = (root / "out").resolve()
            all_files = resolve_inputs(root, None, root_out)
            self.assertEqual(len(all_files), 1)
            self.assertEqual(all_files[0], (root / HOUSEWIRE_YAML).resolve())

            empty_sub = root / "Parking"
            empty_sub.mkdir()
            parking_out = (empty_sub / "out").resolve()
            parking_files = resolve_inputs(empty_sub, None, parking_out)
            self.assertEqual(parking_files, [])

    def test_run_generate_writes_out_under_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "MyHouse"
            root.mkdir()
            doc = init_site(root, type_id="House", label="House")
            add_place(doc, "Parking", type_id="Floor", label="Parking")
            save_site(root, doc)

            with (
                mock.patch("housewire.cli.run_wireviz"),
                mock.patch("housewire.cli.export_physical_zone"),
                mock.patch("housewire.cli.write_and_render_wireviz") as write_wv,
            ):
                code = run_generate_project(root, force=True)

            self.assertEqual(code, 0)
            write_wv.assert_called_once()
            args = write_wv.call_args
            self.assertEqual(args.args[0], root)
            self.assertEqual(args.args[2], (root / "out").resolve())
            self.assertTrue(args.kwargs.get("with_stubs"))
