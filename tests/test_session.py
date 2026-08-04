"""Tests for SiteSession."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fixtures import add_place, init_site, save_site
from housewire.site.io import HOUSEWIRE_YAML, create_empty_house_file


class TestSiteSession(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "out").mkdir()
        doc = init_site(self.root, type_id="House")
        add_place(doc, "zona_a", type_id="Floor")
        add_place(doc, "caja", under=("zona_a",), type_id="JunctionBox")
        save_site(self.root, doc)
        self.site_yaml = self.root / HOUSEWIRE_YAML

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _session(self):
        from housewire.site.session import SiteSession

        return SiteSession(self.root)

    def test_open_from_yaml_file(self) -> None:
        from housewire.site.session import SiteSession

        s = SiteSession.open(self.site_yaml)
        self.assertEqual(s.root, self.root.resolve())
        self.assertEqual(s.site_yaml(), self.site_yaml.resolve())

    def test_initial_cwd_is_root(self) -> None:
        s = self._session()
        self.assertEqual(s.cwd_path(), self.root)

    def test_cd_into_subdir(self) -> None:
        s = self._session()
        s.cd("zona_a")
        self.assertEqual(s.cwd, Path("zona_a"))

    def test_cd_dotdot(self) -> None:
        s = self._session()
        s.cd("zona_a/caja")
        s.cd("..")
        self.assertEqual(s.cwd, Path("zona_a"))

    def test_cd_no_args_returns_to_root(self) -> None:
        s = self._session()
        s.cd("zona_a")
        s.cd(None)
        self.assertEqual(s.cwd, Path("."))

    def test_cd_resets_active_yaml(self) -> None:
        s = self._session()
        s.cd("zona_a")
        s.use_yaml("housewire.yaml")
        self.assertIsNotNone(s.active_yaml)
        s.cd("..")
        self.assertEqual(s.active_yaml, self.site_yaml.resolve())

    def test_cd_auto_uses_index_yaml(self) -> None:
        s = self._session()
        auto = s.cd("zona_a")
        self.assertIsNotNone(auto)
        self.assertEqual(s.active_yaml.name, "housewire.yaml")

    def test_cd_ignores_non_index_siblings(self) -> None:
        create_empty_house_file(self.root / "otro.yaml")
        s = self._session()
        auto = s.cd("zona_a")
        self.assertIsNotNone(auto)
        self.assertEqual(s.active_yaml.name, "housewire.yaml")

    def test_ensure_active_yaml_auto(self) -> None:
        s = self._session()
        s.cd("zona_a")
        s.active_yaml = None
        path = s.ensure_active_yaml()
        self.assertEqual(path.name, "housewire.yaml")

    def test_use_other_root_yaml(self) -> None:
        create_empty_house_file(self.root / "otro.yaml")
        s = self._session()
        s.cd("zona_a")
        path = s.use_yaml("otro.yaml")
        self.assertEqual(path.name, "otro.yaml")
        self.assertEqual(s.site_yaml().name, "otro.yaml")

    def test_cd_outside_root_raises(self) -> None:
        s = self._session()
        with self.assertRaises(ValueError):
            s.cd("..")

    def test_cd_excluded_dir_raises(self) -> None:
        s = self._session()
        with self.assertRaises(FileNotFoundError):
            s.cd("out")

    def test_cd_nonexistent_raises(self) -> None:
        s = self._session()
        with self.assertRaises(FileNotFoundError):
            s.cd("no_existe")

    def test_use_yaml_sets_active(self) -> None:
        s = self._session()
        s.cd("zona_a")
        s.use_yaml("housewire.yaml")
        self.assertIsNotNone(s.active_yaml)
        self.assertEqual(s.active_yaml.name, "housewire.yaml")

    def test_use_yaml_nonexistent_raises(self) -> None:
        s = self._session()
        with self.assertRaises(FileNotFoundError):
            s.use_yaml("noexiste.yaml")

    def test_active_path_uses_site_yaml(self) -> None:
        s = self._session()
        self.assertEqual(s.active_path(), self.site_yaml.resolve())

    def test_list_locations_contains_subdir(self) -> None:
        s = self._session()
        names = [n for n, _ in s.list_locations()]
        self.assertIn("zona_a", names)

    def test_list_locations_skips_dirs_without_housewire(self) -> None:
        s = self._session()
        (self.root / "solo_carpeta").mkdir()
        names = [n for n, _ in s.list_locations()]
        self.assertNotIn("solo_carpeta", names)
        self.assertIn("zona_a", names)

    def test_list_elements_from_housewire(self) -> None:
        from housewire.site import abm

        s = self._session()
        s.cd("zona_a")
        path = s.ensure_active_yaml()
        doc = abm.load_editable(path, self.root)
        place = s.place_node(doc)
        abm.add_element(place, "MT_A", type_id="MCB")
        abm.persist(doc, path, self.root)
        rows = s.list_elements()
        self.assertEqual(rows, [("MT_A", "MCB")])

    def test_prompt_label_is_path_only(self) -> None:
        s = self._session()
        s.cd("zona_a")
        s.use_yaml("housewire.yaml")
        label = s.prompt_label()
        self.assertIn("zona_a", label)
        self.assertNotIn("housewire.yaml", label)
        self.assertNotIn("[", label)
