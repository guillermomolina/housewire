"""Tests del dispatcher del shell (run_shell_line)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from housewire.project import abm
from housewire.project.io import create_empty_house_file, create_location_index


# ---------------------------------------------------------------------------
# Shell dispatcher (run_shell_line)
# ---------------------------------------------------------------------------

class TestShellDispatcher(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "zona_a").mkdir()
        self.yaml = self.root / "zona_a" / "housewire.yaml"
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

    def test_version_prints_package_version(self) -> None:
        from io import StringIO
        import sys
        from housewire import __version__

        s = self._session()
        buf = StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            code = self._run(s, "version")
        finally:
            sys.stdout = old
        self.assertEqual(code, 0)
        self.assertIn(__version__, buf.getvalue())

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

    def test_ls_shows_locations_and_elements(self) -> None:
        from io import StringIO
        import sys

        s = self._session()
        self._run(s, "cd zona_a")
        self._run(s, "add element MT_A --type MCB --subtype C10")
        (self.root / "zona_a" / "subloc").mkdir()
        from housewire.project.io import create_location_index

        create_location_index(self.root / "caja", type_id="JunctionBox")
        s = self._session()
        buf = StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            code = self._run(s, "ls")
        finally:
            sys.stdout = old
        self.assertEqual(code, 0)
        out = buf.getvalue()
        self.assertIn("locations:", out)
        self.assertIn("zona_a/", out)
        self.assertIn("caja/", out)
        self.assertNotIn("[d]", out)
        self.assertNotIn("[f]", out)
        self.assertNotIn("housewire.yaml", out)

    def test_use_sets_active(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        self._run(s, "use housewire.yaml")
        self.assertIsNotNone(s.active_yaml)

    def test_add_element_via_shell(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        self._run(s, "use housewire.yaml")
        code = self._run(s, "add element MT_Nuevo --type MCB --subtype C10")
        self.assertEqual(code, 0)
        self.assertTrue(s.is_dirty())
        _path, doc = s.ensure_doc()
        self.assertIn("MT_Nuevo", doc["elements"])
        self._run(s, "save")
        disk = abm.load_editable(s.active_path(), self.root)
        self.assertIn("MT_Nuevo", disk["elements"])

    def test_rm_element_via_shell(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        self._run(s, "use housewire.yaml")
        self._run(s, "add element MT_Nuevo --type MCB --subtype C10")
        code = self._run(s, "rm element MT_Nuevo")
        self.assertEqual(code, 0)
        _path, doc = s.ensure_doc()
        self.assertNotIn("MT_Nuevo", doc["elements"])

    def test_add_cable_via_shell(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        self._run(s, "use housewire.yaml")
        code = self._run(s, "add cable Linea_X --section '1.5 mm2' --colors BN,BU")
        self.assertEqual(code, 0)
        _path, doc = s.ensure_doc()
        self.assertIn("Linea_X", doc["cables"])

    def test_add_conduit_via_shell(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        self._run(s, "add cable Linea_Z --section 1.5 --colors BN,BU")
        code = self._run(
            s,
            "add conduit Conducto_Z --from .N1 --to Caja_derivacion_2.S1 "
            "--contains Linea_Z --notes 'paso'",
        )
        self.assertEqual(code, 0)
        _path, doc = s.ensure_doc()
        cd = doc["conduits"]["Conducto_Z"]
        self.assertEqual(cd["from"], ".N1")
        self.assertEqual(cd["to"], "Caja_derivacion_2.S1")
        self.assertEqual(cd["contains"], ["Linea_Z"])
        self.assertEqual(cd["subtype"], "tube")
        self.assertEqual(cd["notes"], "paso")

    def test_pend_via_shell(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        code = self._run(s, "pend B1 B2")
        self.assertEqual(code, 0)
        _path, doc = s.ensure_doc()
        self.assertIn("PEND_Linea_01", doc["cables"])
        self.assertIn("Conducto_paso_01", doc["conduits"])

    def test_pend_with_section_via_shell(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        code = self._run(s, "pend B1 B2 2.5")
        self.assertEqual(code, 0)
        _path, doc = s.ensure_doc()
        self.assertEqual(doc["cables"]["PEND_Linea_01"]["section"], "2.5 mm2")

    def test_cd_auto_use_message_path(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        self.assertIsNotNone(s.active_yaml)
        self.assertEqual(s.active_yaml.name, "housewire.yaml")

    def test_pend_wizard_prompts(self) -> None:
        from unittest.mock import patch

        s = self._session()
        self._run(s, "cd zona_a")
        with patch("housewire.commands._prompt", side_effect=["B1", "B2"]):
            code = self._run(s, "pend")
        self.assertEqual(code, 0)
        _path, doc = s.ensure_doc()
        self.assertIn("PEND_Linea_01", doc["cables"])
        self.assertIn("B1", doc["cables"]["PEND_Linea_01"]["notes"])

    def test_add_dir_creates_directory(self) -> None:
        s = self._session()
        code = self._run(s, "add dir nueva_zona")
        self.assertEqual(code, 0)
        self.assertTrue((self.root / "nueva_zona").is_dir())

    def test_rm_file_removes_index(self) -> None:
        from housewire.project.io import create_empty_house_file

        s = self._session()
        create_empty_house_file(self.root / "solo" / "housewire.yaml") if False else None
        (self.root / "tmp_loc").mkdir()
        create_empty_house_file(self.root / "tmp_loc" / "housewire.yaml")
        self._run(s, "cd tmp_loc")
        code = self._run(s, "rm file housewire.yaml")
        self.assertEqual(code, 0)
        self.assertFalse((self.root / "tmp_loc" / "housewire.yaml").exists())

    def test_rm_file_clears_active_if_active(self) -> None:
        from housewire.project.io import create_empty_house_file

        (self.root / "tmp_loc2").mkdir()
        create_empty_house_file(self.root / "tmp_loc2" / "housewire.yaml")
        s = self._session()
        self._run(s, "cd tmp_loc2")
        self.assertIsNotNone(s.active_yaml)
        self._run(s, "rm file housewire.yaml")
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

        def mock_gen(scope, force=False):
            called.append((scope, force))
            return 0

        self._run(s, "generate -f", generate_fn=mock_gen)
        self.assertEqual(called, [(s.cwd_path(), True)])

    def test_generate_without_force(self) -> None:
        s = self._session()
        called = []

        def mock_gen(scope, force=False):
            called.append((scope, force))
            return 0

        self._run(s, "generate", generate_fn=mock_gen)
        self.assertEqual(called, [(s.cwd_path(), False)])

    def test_generate_uses_cwd_not_root(self) -> None:
        create_location_index(self.root / "Parking", type_id="Floor", label="Parking")
        s = self._session()
        self._run(s, "cd Parking")
        called = []

        def mock_gen(scope, force=False):
            called.append(scope)
            return 0

        self._run(s, "generate -f", generate_fn=mock_gen)
        self.assertEqual(called, [s.cwd_path()])
        self.assertEqual(called[0], (self.root / "Parking").resolve())
        self.assertNotEqual(called[0], s.root)
    def test_add_location_via_shell(self) -> None:
        s = self._session()
        code = self._run(
            s,
            'add location "Caja X" --type JunctionBox --subtype "100x100" --notes "mount: wall"',
        )
        self.assertEqual(code, 0)
        disk = self.root / "Caja_X" / "housewire.yaml"
        self.assertFalse(disk.is_file())
        self.assertTrue(s.is_dirty())
        self.assertEqual(s.active_yaml.name, "housewire.yaml")
        self._run(s, "save")
        self.assertTrue(disk.is_file())
        doc = abm.load_editable(s.active_path(), self.root)
        self.assertEqual(doc["type"], "JunctionBox")
        self.assertEqual(doc["subtype"], "100x100")
        self.assertEqual(doc["label"], "Caja X")

    def test_show_includes_location(self) -> None:
        from housewire.project.io import create_location_index
        from io import StringIO
        import sys

        create_location_index(
            self.root / "zona_b", type_id="Floor", subtype="zona", notes="meta"
        )
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
        self.assertIn("place (Floor)", out)
        self.assertIn("zona", out)


class TestShellLineContinuation(unittest.TestCase):
    def test_read_logical_line_joins_backslash(self) -> None:
        from housewire.shell import read_logical_line

        answers = [
            "add conduit X --from A.E1 --to B.N1 \\",
            "  --contains C1",
        ]

        def fake_input(prompt: str = "") -> str:
            return answers.pop(0)

        line = read_logical_line(prompt="$ ", input_fn=fake_input)
        self.assertEqual(
            line,
            "add conduit X --from A.E1 --to B.N1 --contains C1",
        )

    def test_read_logical_line_single(self) -> None:
        from housewire.shell import read_logical_line

        line = read_logical_line(prompt="$ ", input_fn=lambda p: "pwd")
        self.assertEqual(line, "pwd")
