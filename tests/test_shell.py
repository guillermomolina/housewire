"""Tests del dispatcher del shell (run_shell_line)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from housewire.project import abm
from housewire.project.io import create_empty_house_file


# ---------------------------------------------------------------------------
# Shell dispatcher (run_shell_line)
# ---------------------------------------------------------------------------

class TestShellDispatcher(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "zona_a").mkdir()
        self.yaml = self.root / "zona_a" / "index.yaml"
        create_empty_house_file(self.yaml)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _session(self):
        from housewire.project.session import ProjectSession
        return ProjectSession(self.root)

    def _run(self, session, line, generate_fn=None):
        from housewire.commands import run_shell_line
        if generate_fn is None:
            generate_fn = lambda root, force=False: 0
        return run_shell_line(session, line, generate_fn=generate_fn)

    def test_empty_line_returns_none(self) -> None:
        s = self._session()
        self.assertIsNone(self._run(s, ""))

    def test_exit_returns_minus_one(self) -> None:
        s = self._session()
        self.assertEqual(self._run(s, "exit"), -1)

    def test_quit_returns_minus_one(self) -> None:
        s = self._session()
        self.assertEqual(self._run(s, "quit"), -1)

    def test_unknown_command_returns_one(self) -> None:
        s = self._session()
        code = self._run(s, "foobar")
        self.assertEqual(code, 1)

    def test_cd_changes_cwd(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        self.assertEqual(s.cwd, Path("zona_a"))

    def test_cd_no_args_resets_to_root(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        self._run(s, "cd")
        self.assertEqual(s.cwd, Path("."))

    def test_ls_returns_zero(self) -> None:
        s = self._session()
        self.assertEqual(self._run(s, "ls"), 0)

    def test_use_sets_active(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        self._run(s, "use index.yaml")
        self.assertIsNotNone(s.active_yaml)

    def test_add_element_via_shell(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        self._run(s, "use index.yaml")
        code = self._run(s, "add element MT_Nuevo --type MCB --subtype C10")
        self.assertEqual(code, 0)
        doc = abm.load_editable(s.active_path(), self.root)
        self.assertIn("MT_Nuevo", doc["elements"])

    def test_rm_element_via_shell(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        self._run(s, "use index.yaml")
        self._run(s, "add element MT_Nuevo --type MCB --subtype C10")
        code = self._run(s, "rm element MT_Nuevo")
        self.assertEqual(code, 0)
        doc = abm.load_editable(s.active_path(), self.root)
        self.assertNotIn("MT_Nuevo", doc["elements"])

    def test_add_cable_via_shell(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        self._run(s, "use index.yaml")
        code = self._run(s, "add cable Linea_X --section '1.5 mm2' --colors BN,BU")
        self.assertEqual(code, 0)
        doc = abm.load_editable(s.active_path(), self.root)
        self.assertIn("Linea_X", doc["cables"])

    def test_add_cable_defaults_via_shell(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        code = self._run(s, "add cable Linea_Y")
        self.assertEqual(code, 0)
        doc = abm.load_editable(s.active_path(), self.root)
        self.assertEqual(doc["cables"]["Linea_Y"]["section"], "1.5 mm2")
        self.assertEqual(doc["cables"]["Linea_Y"]["colors"], ["BN", "BU"])

    def test_pend_via_shell(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        code = self._run(s, "pend W.N E.S")
        self.assertEqual(code, 0)
        doc = abm.load_editable(s.active_path(), self.root)
        self.assertIn("PEND_Linea_01", doc["cables"])
        self.assertIn("Conducto_paso_01", doc["conduits"])

    def test_pend_with_section_via_shell(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        code = self._run(s, "pend N.E S.W 2.5")
        self.assertEqual(code, 0)
        doc = abm.load_editable(s.active_path(), self.root)
        self.assertEqual(doc["cables"]["PEND_Linea_01"]["section"], "2.5 mm2")

    def test_cd_auto_use_message_path(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        self.assertIsNotNone(s.active_yaml)
        self.assertEqual(s.active_yaml.name, "index.yaml")

    def test_pend_wizard_prompts(self) -> None:
        from unittest.mock import patch

        s = self._session()
        self._run(s, "cd zona_a")
        with patch("housewire.commands._prompt", side_effect=["W.N", "E.S"]):
            code = self._run(s, "pend")
        self.assertEqual(code, 0)
        doc = abm.load_editable(s.active_path(), self.root)
        self.assertIn("PEND_Linea_01", doc["cables"])
        self.assertIn("W.N", doc["cables"]["PEND_Linea_01"]["notes"])

    def test_add_dir_creates_directory(self) -> None:
        s = self._session()
        code = self._run(s, "add dir nueva_zona")
        self.assertEqual(code, 0)
        self.assertTrue((self.root / "nueva_zona").is_dir())

    def test_rm_file_removes_index(self) -> None:
        from housewire.project.io import create_empty_house_file

        s = self._session()
        create_empty_house_file(self.root / "solo" / "index.yaml") if False else None
        (self.root / "tmp_loc").mkdir()
        create_empty_house_file(self.root / "tmp_loc" / "index.yaml")
        self._run(s, "cd tmp_loc")
        code = self._run(s, "rm file index.yaml")
        self.assertEqual(code, 0)
        self.assertFalse((self.root / "tmp_loc" / "index.yaml").exists())

    def test_rm_file_clears_active_if_active(self) -> None:
        from housewire.project.io import create_empty_house_file

        (self.root / "tmp_loc2").mkdir()
        create_empty_house_file(self.root / "tmp_loc2" / "index.yaml")
        s = self._session()
        self._run(s, "cd tmp_loc2")
        self.assertIsNotNone(s.active_yaml)
        self._run(s, "rm file index.yaml")
        self.assertIsNone(s.active_yaml)

    def test_add_element_without_active_yaml_returns_error(self) -> None:
        s = self._session()
        code = self._run(s, "add element MT_X --type MCB")
        self.assertEqual(code, 1)

    def test_rm_dir_empty_ok(self) -> None:
        s = self._session()
        self._run(s, "add dir vacia")
        code = self._run(s, "rm dir vacia")
        self.assertEqual(code, 0)

    def test_rm_dir_nonempty_returns_error(self) -> None:
        s = self._session()
        code = self._run(s, "rm dir zona_a")
        self.assertEqual(code, 1)

    def test_generate_calls_fn(self) -> None:
        s = self._session()
        called = []
        def mock_gen(root, force=False):
            called.append(force)
            return 0
        self._run(s, "generate -f", generate_fn=mock_gen)
        self.assertEqual(called, [True])

    def test_generate_without_force(self) -> None:
        s = self._session()
        called = []
        def mock_gen(root, force=False):
            called.append(force)
            return 0
        self._run(s, "generate", generate_fn=mock_gen)
        self.assertEqual(called, [False])

    def test_add_location_via_shell(self) -> None:
        s = self._session()
        code = self._run(s, 'add location "Caja X" --subtype "100x100" --notes "mount: wall"')
        self.assertEqual(code, 0)
        self.assertTrue((self.root / "Caja X" / "index.yaml").is_file())
        self.assertEqual(s.active_yaml.name, "index.yaml")
        doc = abm.load_editable(s.active_path(), self.root)
        self.assertEqual(doc["self"]["type"], "Location")
        self.assertEqual(doc["self"]["subtype"], "100x100")

    def test_show_includes_self(self) -> None:
        from housewire.project.io import create_location_index
        from io import StringIO
        import sys

        create_location_index(self.root / "zona_b", subtype="zona", notes="meta")
        s = self._session()
        self._run(s, "cd zona_b")
        buf = StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            code = self._run(s, "show")
        finally:
            sys.stdout = old
        self.assertEqual(code, 0)
        out = buf.getvalue()
        self.assertIn("self (Location)", out)
        self.assertIn("zona", out)
