"""Tests de ProjectSession."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from housewire.project.io import create_empty_house_file, create_location_index


# ---------------------------------------------------------------------------
# ProjectSession
# ---------------------------------------------------------------------------

class TestProjectSession(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "zona_a").mkdir()
        (self.root / "zona_a" / "sub").mkdir()
        (self.root / "out").mkdir()
        self.yaml = self.root / "zona_a" / "housewire.yaml"
        create_empty_house_file(self.yaml)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _session(self):
        from housewire.project.session import ProjectSession
        return ProjectSession(self.root)

    def test_initial_cwd_is_root(self) -> None:
        s = self._session()
        self.assertEqual(s.cwd_path(), self.root)

    def test_cd_into_subdir(self) -> None:
        s = self._session()
        s.cd("zona_a")
        self.assertEqual(s.cwd, Path("zona_a"))

    def test_cd_dotdot(self) -> None:
        create_location_index(self.root / "zona_a" / "caja", type_id="JunctionBox")
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
        # Root has no housewire.yaml in this fixture
        self.assertIsNone(s.active_yaml)

    def test_cd_auto_uses_index_yaml(self) -> None:
        s = self._session()
        auto = s.cd("zona_a")
        self.assertIsNotNone(auto)
        self.assertEqual(s.active_yaml.name, "housewire.yaml")

    def test_cd_ignores_non_index_siblings(self) -> None:
        create_empty_house_file(self.root / "zona_a" / "otro.yaml")
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

    def test_use_non_index_raises(self) -> None:
        create_empty_house_file(self.root / "zona_a" / "otro.yaml")
        s = self._session()
        s.cd("zona_a")
        with self.assertRaises(ValueError):
            s.use_yaml("otro.yaml")

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

    def test_active_path_without_use_raises(self) -> None:
        s = self._session()
        with self.assertRaises(ValueError):
            s.active_path()

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
        from housewire.project import abm

        s = self._session()
        s.cd("zona_a")
        doc = abm.load_editable(s.active_path(), self.root)
        abm.add_element(doc, "MT_A", type_id="MCB", subtype="C10")
        abm.persist(doc, s.active_path(), self.root)
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
