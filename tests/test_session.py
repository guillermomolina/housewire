"""Tests de ProjectSession."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from housewire.project.io import create_empty_house_file


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
        self.yaml = self.root / "zona_a" / "doc.yaml"
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
        s = self._session()
        s.cd("zona_a/sub")
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
        s.use_yaml("doc.yaml")
        self.assertIsNotNone(s.active_yaml)
        s.cd("..")
        self.assertIsNone(s.active_yaml)

    def test_cd_auto_uses_index_yaml_over_siblings(self) -> None:
        create_empty_house_file(self.root / "zona_a" / "otro.yaml")
        (self.root / "zona_a" / "index.yaml").write_text(
            "schema: house/v1\nself:\n  type: Location\nelements: {}\n",
            encoding="utf-8",
        )
        s = self._session()
        auto = s.cd("zona_a")
        self.assertIsNotNone(auto)
        self.assertEqual(s.active_yaml.name, "index.yaml")

    def test_cd_auto_uses_single_yaml(self) -> None:
        s = self._session()
        auto = s.cd("zona_a")
        self.assertIsNotNone(auto)
        self.assertEqual(s.active_yaml.name, "doc.yaml")

    def test_cd_no_auto_use_when_multiple_yaml(self) -> None:
        create_empty_house_file(self.root / "zona_a" / "otro.yaml")
        s = self._session()
        auto = s.cd("zona_a")
        self.assertIsNone(auto)
        self.assertIsNone(s.active_yaml)

    def test_ensure_active_yaml_auto(self) -> None:
        s = self._session()
        s.cd("zona_a")
        # clear after auto from cd to test ensure
        s.active_yaml = None
        path = s.ensure_active_yaml()
        self.assertEqual(path.name, "doc.yaml")

    def test_cd_outside_root_raises(self) -> None:
        s = self._session()
        with self.assertRaises(ValueError):
            s.cd("../../etc")

    def test_cd_excluded_dir_raises(self) -> None:
        s = self._session()
        with self.assertRaises(ValueError):
            s.cd("out")

    def test_cd_nonexistent_raises(self) -> None:
        s = self._session()
        with self.assertRaises(NotADirectoryError):
            s.cd("no_existe")

    def test_use_yaml_sets_active(self) -> None:
        s = self._session()
        s.cd("zona_a")
        s.use_yaml("doc.yaml")
        self.assertIsNotNone(s.active_yaml)
        self.assertEqual(s.active_yaml.name, "doc.yaml")

    def test_use_yaml_nonexistent_raises(self) -> None:
        s = self._session()
        with self.assertRaises(FileNotFoundError):
            s.use_yaml("noexiste.yaml")

    def test_active_path_without_use_raises(self) -> None:
        s = self._session()
        with self.assertRaises(ValueError):
            s.active_path()

    def test_list_dir_contains_subdir(self) -> None:
        s = self._session()
        names = [n for n, _ in s.list_dir()]
        self.assertIn("zona_a/", names)

    def test_list_dir_excludes_out(self) -> None:
        s = self._session()
        names = [n for n, _ in s.list_dir()]
        self.assertNotIn("out/", names)

    def test_list_dir_marks_active_yaml(self) -> None:
        s = self._session()
        s.cd("zona_a")
        s.use_yaml("doc.yaml")
        names = [n for n, _ in s.list_dir()]
        self.assertTrue(any("doc.yaml" in n and "*" in n for n in names))

    def test_prompt_label_shows_active(self) -> None:
        s = self._session()
        s.cd("zona_a")
        s.use_yaml("doc.yaml")
        label = s.prompt_label()
        self.assertIn("doc.yaml", label)
