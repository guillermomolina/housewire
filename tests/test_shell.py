"""Tests del dispatcher del shell (run_shell_line)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fixtures import add_place, init_site, save_site
from housewire.site import abm
from housewire.site.io import HOUSEWIRE_YAML, create_empty_house_file
from housewire.site.tree import get_place_node


class TestShellDispatcher(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        doc = init_site(self.root, type_id="House")
        add_place(doc, "zona_a", type_id="Floor")
        save_site(self.root, doc)
        self.site_yaml = self.root / HOUSEWIRE_YAML

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _session(self):
        from housewire.site.session import SiteSession

        return SiteSession(self.root)

    def _run(self, session, line):
        from housewire.commands import run_shell_line

        return run_shell_line(session, line)

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

        doc = abm.load_editable(self.site_yaml, self.root)
        add_place(doc, "caja", type_id="JunctionBox")
        save_site(self.root, doc)

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
        self.assertNotIn("housewire.yaml", out)

        self._run(s, "cd zona_a")
        self._run(s, "add element MT_A --type MCB ")

    def test_use_sets_active(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        self._run(s, "use housewire.yaml")
        self.assertIsNotNone(s.active_yaml)

    def test_add_element_via_shell(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        self._run(s, "use housewire.yaml")
        code = self._run(s, "add element MT_Nuevo --type MCB ")
        self.assertEqual(code, 0)
        self.assertTrue(s.is_dirty())
        _path, doc = s.ensure_doc()
        place = get_place_node(doc, ("zona_a",))
        self.assertIn("MT_Nuevo", place["elements"])
        self._run(s, "save")
        disk = abm.load_editable(s.active_path(), self.root)
        self.assertIn("MT_Nuevo", get_place_node(disk, ("zona_a",))["elements"])

    def test_rm_element_via_shell(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        self._run(s, "use housewire.yaml")
        self._run(s, "add element MT_Nuevo --type MCB ")
        code = self._run(s, "rm element MT_Nuevo")
        self.assertEqual(code, 0)
        _path, doc = s.ensure_doc()
        place = get_place_node(doc, ("zona_a",))
        self.assertNotIn("MT_Nuevo", place["elements"])

    def test_add_cable_via_shell(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        self._run(s, "use housewire.yaml")
        code = self._run(s, "add cable Linea_X --section '1.5 mm2' --colors BN,BU")
        self.assertEqual(code, 0)
        _path, doc = s.ensure_doc()
        place = get_place_node(doc, ("zona_a",))
        self.assertIn("Linea_X", place["cables"])

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
        place = get_place_node(doc, ("zona_a",))
        cd = place["cables"]["Conducto_Z"]
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
        place = get_place_node(doc, ("zona_a",))
        self.assertIn("PEND_Linea_01", place["cables"])
        self.assertIn("Conducto_paso_01", place["cables"])

    def test_pend_with_section_via_shell(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        code = self._run(s, "pend B1 B2 2.5")
        self.assertEqual(code, 0)
        _path, doc = s.ensure_doc()
        place = get_place_node(doc, ("zona_a",))
        self.assertEqual(place["cables"]["PEND_Linea_01"]["section"], "2.5 mm2")

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
        place = get_place_node(doc, ("zona_a",))
        self.assertIn("PEND_Linea_01", place["cables"])
        self.assertIn("B1", place["cables"]["PEND_Linea_01"]["notes"])

    def test_add_dir_creates_directory(self) -> None:
        s = self._session()
        code = self._run(s, "add dir nueva_zona")
        self.assertEqual(code, 0)
        self.assertTrue((self.root / "nueva_zona").is_dir())

    def test_rm_file_removes_index(self) -> None:
        s = self._session()
        code = self._run(s, "rm file housewire.yaml")
        self.assertEqual(code, 0)
        self.assertFalse(self.site_yaml.exists())

    def test_rm_file_clears_active_if_active(self) -> None:
        s = self._session()
        self.assertIsNotNone(s.active_yaml)
        self._run(s, "rm file housewire.yaml")
        self.assertIsNone(s.active_yaml)

    def test_add_element_without_active_yaml_returns_error(self) -> None:
        s = self._session()
        s.active_yaml = None
        s._buffers.clear()
        (self.root / HOUSEWIRE_YAML).unlink(missing_ok=True)
        code = self._run(s, "add element MT_X --type MCB")
        self.assertEqual(code, 1)

    def test_rm_dir_empty_ok(self) -> None:
        s = self._session()
        self._run(s, "add dir vacia")
        code = self._run(s, "rm dir vacia")
        self.assertEqual(code, 0)

    def test_rm_dir_nonempty_returns_error(self) -> None:
        s = self._session()
        (self.root / "full_dir").mkdir()
        (self.root / "full_dir" / "file.txt").write_text("x", encoding="utf-8")
        code = self._run(s, "rm dir full_dir")
        self.assertEqual(code, 1)

    def test_add_location_via_shell(self) -> None:
        s = self._session()
        code = self._run(
            s,
            'add location "Caja X" --type JunctionBox --subtype ip40 --notes "mount: wall"',
        )
        self.assertEqual(code, 0)
        self.assertTrue(s.is_dirty())
        self.assertEqual(s.active_yaml.name, "housewire.yaml")
        self.assertEqual(s.logical_parts, ["Caja_X"])
        self._run(s, "save")
        disk = abm.load_editable(s.active_path(), self.root)
        caja = get_place_node(disk, ("Caja_X",))
        self.assertEqual(caja["type"], "JunctionBox")
        self.assertEqual(caja["subtype"], "ip40")
        self.assertEqual(caja["label"], "Caja X")

    def test_show_includes_location(self) -> None:
        from io import StringIO
        import sys

        doc = abm.load_editable(self.site_yaml, self.root)
        add_place(doc, "zona_b", type_id="Floor", notes="meta")
        save_site(self.root, doc)
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
        self.assertIn("meta", out)


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
