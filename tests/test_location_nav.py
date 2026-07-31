"""Tests for logical location navigation (outline dirs + inline places)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml as _yaml

from housewire.project.io import (
    create_empty_house_file,
    create_inline_location,
    create_location_index,
    load_yaml,
)


class TestLocationNavigation(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        # Outline tree: Floor/Parking + JunctionBox outline

        create_location_index(self.root / "Parking", type_id="Floor", label="Parking")
        create_location_index(
            self.root / "Parking" / "Caja_outline",
            type_id="JunctionBox",
            label="Outline box",
        )
        # Inline place under Parking
        parking_yaml = self.root / "Parking" / "housewire.yaml"
        doc = load_yaml(parking_yaml)
        create_inline_location(
            doc, "Caja_inline", type_id="JunctionBox", label="Inline box"
        )
        doc.setdefault("elements", {})["Enchufe"] = {
            "type": "Socket",
            "subtype": "Schuko",
        }
        parking_yaml.write_text(
            _yaml.safe_dump(doc, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _session(self):
        from housewire.project.session import ProjectSession

        return ProjectSession(self.root)

    def test_list_locations_includes_outline_and_inline(self) -> None:
        s = self._session()
        s.cd("Parking")
        children = {c.name: c for c in s.list_location_children()}
        self.assertIn("Caja_outline", children)
        self.assertEqual(children["Caja_outline"].storage, "dir")
        self.assertIn("Caja_inline", children)
        self.assertEqual(children["Caja_inline"].storage, "inline")
        self.assertEqual(children["Caja_inline"].place_type, "JunctionBox")

    def test_list_elements_skips_place_types(self) -> None:
        s = self._session()
        s.cd("Parking")
        rows = dict(s.list_elements())
        self.assertIn("Enchufe", rows)
        self.assertNotIn("Caja_inline", rows)
        self.assertNotIn("Caja_outline", rows)

    def test_cd_into_inline_place(self) -> None:
        s = self._session()
        s.cd("Parking/Caja_inline")
        self.assertEqual(s.logical_parts, ["Parking", "Caja_inline"])
        self.assertTrue(s.cursor().is_inline)
        self.assertEqual(s.active_yaml, self.root / "Parking" / "housewire.yaml")

    def test_cd_into_outline_place(self) -> None:
        s = self._session()
        s.cd("Parking/Caja_outline")
        self.assertEqual(s.logical_parts, ["Parking", "Caja_outline"])
        self.assertFalse(s.cursor().is_inline)
        self.assertEqual(
            s.active_yaml, self.root / "Parking" / "Caja_outline" / "housewire.yaml"
        )

    def test_cd_dotdot_from_inline(self) -> None:
        s = self._session()
        s.cd("Parking/Caja_inline")
        s.cd("..")
        self.assertEqual(s.logical_parts, ["Parking"])

    def test_cd_plain_directory_without_housewire_fails(self) -> None:
        (self.root / "Parking" / "solo_carpeta").mkdir()
        s = self._session()
        s.cd("Parking")
        with self.assertRaises(FileNotFoundError):
            s.cd("solo_carpeta")

    def test_add_element_inside_inline_place(self) -> None:
        from housewire.project import abm

        s = self._session()
        s.cd("Parking/Caja_inline")
        path = s.ensure_active_yaml()
        doc = abm.load_editable(path, self.root)
        place = s.place_node(doc)
        abm.add_element(place, "Regleta", type_id="TerminalStrip")
        abm.persist(doc, path, self.root)
        reloaded = load_yaml(path)
        self.assertIn(
            "Regleta",
            reloaded["elements"]["Caja_inline"]["elements"],
        )
        # Sibling socket at Parking still there
        self.assertIn("Enchufe", reloaded["elements"])

    def test_name_collision_dir_and_inline_raises_on_ls(self) -> None:
        # Create colliding inline with same name as outline sibling
        parking_yaml = self.root / "Parking" / "housewire.yaml"
        doc = load_yaml(parking_yaml)
        create_inline_location(doc, "Caja_outline", type_id="JunctionBox")
        parking_yaml.write_text(
            _yaml.safe_dump(doc, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        s = self._session()
        s.cd("Parking")
        with self.assertRaises(ValueError) as ctx:
            s.list_location_children()
        self.assertIn("ambiguous", str(ctx.exception).lower())

    def test_monolith_single_file_navigation(self) -> None:
        mono = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(mono, ignore_errors=True))
        create_location_index(mono, type_id="House", label="Site")
        # overwrite: put zones inline in root yaml (housewire is inside mono/ if create_location_index used mono as dir)
        # create_location_index(mono) creates mono/housewire.yaml — but mono IS the project root.
        # Recreate properly:
        import shutil

        shutil.rmtree(mono)
        mono.mkdir()
        root_yaml = mono / "housewire.yaml"
        root_yaml.write_text(
            "schema: house/v1\n"
            "type: House\n"
            "elements:\n"
            "  Parking:\n"
            "    type: Floor\n"
            "    elements:\n"
            "      Caja_1:\n"
            "        type: JunctionBox\n"
            "        elements:\n"
            "          Regleta:\n"
            "            type: TerminalStrip\n",
            encoding="utf-8",
        )
        from housewire.project.session import ProjectSession

        s = ProjectSession(mono)
        names = [n for n, _ in s.list_locations()]
        self.assertEqual(names, ["Parking"])
        s.cd("Parking")
        self.assertTrue(s.cursor().is_inline)
        child_names = [c.name for c in s.list_location_children()]
        self.assertEqual(child_names, ["Caja_1"])
        s.cd("Caja_1")
        self.assertEqual(s.logical_parts, ["Parking", "Caja_1"])
        self.assertEqual(dict(s.list_elements()), {"Regleta": "TerminalStrip"})


class TestAddLocationMode(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        create_location_index(self.root / "Parking", type_id="Floor")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run(self, session, line: str) -> int:
        from housewire.commands import run_shell_line

        return run_shell_line(session, line, generate_fn=lambda root, force=False: 0)

    def _session(self):
        from housewire.project.session import ProjectSession

        return ProjectSession(self.root)

    def test_add_location_default_outline(self) -> None:
        s = self._session()
        s.cd("Parking")
        code = self._run(s, "add location Caja_nueva --type JunctionBox")
        self.assertEqual(code, 0)
        disk = self.root / "Parking" / "Caja_nueva" / "housewire.yaml"
        self.assertFalse(disk.is_file())
        self.assertTrue(s.is_dirty())
        self.assertEqual(s.logical_parts, ["Parking", "Caja_nueva"])
        self.assertFalse(s.cursor().is_inline)
        self._run(s, "save")
        self.assertTrue(disk.is_file())

    def test_add_location_inline_flag(self) -> None:
        s = self._session()
        s.cd("Parking")
        code = self._run(s, "add location Caja_in --type JunctionBox --inline")
        self.assertEqual(code, 0)
        self.assertEqual(s.logical_parts, ["Parking", "Caja_in"])
        self.assertTrue(s.cursor().is_inline)
        self.assertTrue(s.is_dirty())
        _path, doc = s.ensure_doc()
        self.assertEqual(doc["elements"]["Caja_in"]["type"], "JunctionBox")
        self._run(s, "save")
        disk = load_yaml(self.root / "Parking" / "housewire.yaml")
        self.assertEqual(disk["elements"]["Caja_in"]["type"], "JunctionBox")

    def test_add_location_under_inline_defaults_inline(self) -> None:
        s = self._session()
        s.cd("Parking")
        self._run(s, "add location Padre --type JunctionBox --inline")
        code = self._run(s, "add location Hija --type JunctionBox")
        self.assertEqual(code, 0)
        self.assertEqual(s.logical_parts, ["Parking", "Padre", "Hija"])
        self.assertTrue(s.cursor().is_inline)
        _path, doc = s.ensure_doc()
        self.assertIn("Hija", doc["elements"]["Padre"]["elements"])

    def test_add_location_dir_under_inline_fails(self) -> None:
        s = self._session()
        s.cd("Parking")
        self._run(s, "add location Padre --type JunctionBox --inline")
        code = self._run(s, "add location Hija --type JunctionBox --dir")
        self.assertEqual(code, 1)

    def test_add_location_collision_with_outline(self) -> None:
        create_location_index(
            self.root / "Parking" / "Caja_x", type_id="JunctionBox"
        )
        s = self._session()
        s.cd("Parking")
        code = self._run(s, "add location Caja_x --type JunctionBox --inline")
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
