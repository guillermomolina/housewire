"""Tests for logical location navigation (nested places in one YAML)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.unit.fixtures import add_place, init_site, save_site
from housewire.site.io import HOUSEWIRE_YAML, load_yaml


class TestLocationNavigation(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        doc = init_site(self.root, type_id="House", label="Site")
        add_place(doc, "Parking", type_id="Floor", label="Parking")
        add_place(
            doc,
            "Caja_outline",
            under=("Parking",),
            type_id="JunctionBox",
            label="Outline box",
        )
        add_place(
            doc,
            "Caja_inline",
            under=("Parking",),
            type_id="JunctionBox",
            label="Inline box",
        )
        parking = doc["elements"]["Parking"]
        parking.setdefault("elements", {})["Enchufe"] = {
            "type": "Socket",
            "subtype": "Schuko",
        }
        save_site(self.root, doc)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _session(self):
        from housewire.site.session import SiteSession

        return SiteSession(self.root)

    def test_list_locations_includes_nested_places(self) -> None:
        s = self._session()
        s.cd("Parking")
        children = {c.name: c for c in s.list_location_children()}
        self.assertIn("Caja_outline", children)
        self.assertIn("Caja_inline", children)
        self.assertEqual(children["Caja_outline"].place_type, "JunctionBox")
        self.assertEqual(children["Caja_inline"].place_type, "JunctionBox")

    def test_list_elements_skips_place_types(self) -> None:
        s = self._session()
        s.cd("Parking")
        rows = dict(s.list_elements())
        self.assertIn("Enchufe", rows)
        self.assertNotIn("Caja_inline", rows)
        self.assertNotIn("Caja_outline", rows)

    def test_cd_into_nested_place(self) -> None:
        s = self._session()
        s.cd("Parking/Caja_inline")
        self.assertEqual(s.logical_parts, ["Parking", "Caja_inline"])
        self.assertEqual(s.active_yaml, (self.root / HOUSEWIRE_YAML).resolve())

    def test_cd_dotdot_from_nested(self) -> None:
        s = self._session()
        s.cd("Parking/Caja_inline")
        s.cd("..")
        self.assertEqual(s.logical_parts, ["Parking"])

    def test_cd_nonexistent_child_raises(self) -> None:
        s = self._session()
        s.cd("Parking")
        with self.assertRaises(FileNotFoundError):
            s.cd("solo_carpeta")

    def test_add_element_inside_nested_place(self) -> None:
        from housewire.site import abm

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
            reloaded["elements"]["Parking"]["elements"]["Caja_inline"]["elements"],
        )
        self.assertIn("Enchufe", reloaded["elements"]["Parking"]["elements"])

    def test_monolith_single_file_navigation(self) -> None:
        mono = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(mono, ignore_errors=True))
        doc = init_site(mono, type_id="House", label="Site")
        add_place(doc, "Parking", type_id="Floor")
        add_place(doc, "Caja_1", under=("Parking",), type_id="JunctionBox")
        caja = doc["elements"]["Parking"]["elements"]["Caja_1"]
        caja.setdefault("elements", {})["Regleta"] = {"type": "TerminalStrip"}
        save_site(mono, doc)

        from housewire.site.session import SiteSession

        s = SiteSession(mono)
        names = [n for n, _ in s.list_locations()]
        self.assertEqual(names, ["Parking"])
        s.cd("Parking")
        child_names = [c.name for c in s.list_location_children()]
        self.assertEqual(child_names, ["Caja_1"])
        s.cd("Caja_1")
        self.assertEqual(s.logical_parts, ["Parking", "Caja_1"])
        self.assertEqual(dict(s.list_elements()), {"Regleta": "TerminalStrip"})


class TestAddLocationNested(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        doc = init_site(self.root, type_id="House")
        add_place(doc, "Parking", type_id="Floor")
        save_site(self.root, doc)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run(self, session, line: str) -> int:
        from housewire.commands import run_shell_line

        return run_shell_line(session, line)

    def _session(self):
        from housewire.site.session import SiteSession

        return SiteSession(self.root)

    def test_add_location_nests_in_site_yaml(self) -> None:
        s = self._session()
        s.cd("Parking")
        code = self._run(s, "add location Caja_nueva --type JunctionBox")
        self.assertEqual(code, 0)
        self.assertTrue(s.is_dirty())
        self.assertEqual(s.logical_parts, ["Parking", "Caja_nueva"])
        self._run(s, "save")
        doc = load_yaml(self.root / HOUSEWIRE_YAML)
        self.assertEqual(
            doc["elements"]["Parking"]["elements"]["Caja_nueva"]["type"],
            "JunctionBox",
        )

    def test_add_location_under_nested_parent(self) -> None:
        s = self._session()
        s.cd("Parking")
        self._run(s, "add location Padre --type JunctionBox")
        code = self._run(s, "add location Hija --type JunctionBox")
        self.assertEqual(code, 0)
        self.assertEqual(s.logical_parts, ["Parking", "Padre", "Hija"])
        _path, doc = s.ensure_doc()
        self.assertIn(
            "Hija",
            doc["elements"]["Parking"]["elements"]["Padre"]["elements"],
        )

    def test_add_location_duplicate_name_fails(self) -> None:
        s = self._session()
        s.cd("Parking")
        self._run(s, "add location Caja_x --type JunctionBox")
        self._run(s, "save")
        s.cd("/Parking")
        code = self._run(s, "add location Caja_x --type JunctionBox")
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
