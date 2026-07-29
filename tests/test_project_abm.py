"""Tests unitarios de la capa ABM (elements, cables, connections, validate, io)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from housewire.project import abm
from housewire.project.io import (
    create_empty_house_file,
    load_yaml,
    require_house_document,
    save_yaml,
)
from housewire.project.validate import validate_house_document


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_project() -> tuple[tempfile.TemporaryDirectory, Path, Path]:
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    yaml_path = root / "test.yaml"
    create_empty_house_file(yaml_path)
    return tmp, root, yaml_path


# ---------------------------------------------------------------------------
# io.py
# ---------------------------------------------------------------------------

class TestIO(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp, self.root, self.yaml = make_project()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_create_empty_file_has_schema(self) -> None:
        doc = load_yaml(self.yaml)
        self.assertEqual(doc.get("schema"), "house/v1")
        self.assertIsInstance(doc.get("elements"), dict)
        self.assertIsInstance(doc.get("cables"), dict)
        self.assertIsInstance(doc.get("connections"), list)

    def test_create_empty_file_already_exists_raises(self) -> None:
        with self.assertRaises(FileExistsError):
            create_empty_house_file(self.yaml)

    def test_save_yaml_creates_backup(self) -> None:
        doc = load_yaml(self.yaml)
        save_yaml(self.yaml, doc, backup=True)
        backup = self.yaml.with_suffix(self.yaml.suffix + ".bak")
        self.assertTrue(backup.exists())

    def test_save_yaml_no_backup(self) -> None:
        doc = load_yaml(self.yaml)
        save_yaml(self.yaml, doc, backup=False)
        backup = self.yaml.with_suffix(self.yaml.suffix + ".bak")
        self.assertFalse(backup.exists())

    def test_require_house_document_passes(self) -> None:
        doc = load_yaml(self.yaml)
        require_house_document(doc)

    def test_require_house_document_fails_on_legacy(self) -> None:
        with self.assertRaises(ValueError):
            require_house_document({"connectors": {}, "cables": {}})


# ---------------------------------------------------------------------------
# abm – elements
# ---------------------------------------------------------------------------

class TestABMElements(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp, self.root, self.yaml = make_project()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_add_element_minimal(self) -> None:
        doc = abm.load_editable(self.yaml, self.root)
        abm.add_element(doc, "MT_A", type_id="MCB")
        self.assertIn("MT_A", doc["elements"])
        self.assertEqual(doc["elements"]["MT_A"]["type"], "MCB")

    def test_add_element_full_fields(self) -> None:
        doc = abm.load_editable(self.yaml, self.root)
        abm.add_element(
            doc, "MT_B",
            type_id="MCB", subtype="C10",
            manufacturer="Merlin Gerin", model="multi9",
            label="LUZ", notes="Prueba",
        )
        entry = doc["elements"]["MT_B"]
        self.assertEqual(entry["subtype"], "C10")
        self.assertEqual(entry["manufacturer"], "Merlin Gerin")
        self.assertEqual(entry["label"], "LUZ")

    def test_add_element_unknown_type_raises(self) -> None:
        doc = abm.load_editable(self.yaml, self.root)
        with self.assertRaises(ValueError):
            abm.add_element(doc, "X", type_id="INEXISTENTE")

    def test_add_element_duplicate_raises(self) -> None:
        doc = abm.load_editable(self.yaml, self.root)
        abm.add_element(doc, "MT_A", type_id="MCB")
        with self.assertRaises(ValueError):
            abm.add_element(doc, "MT_A", type_id="MCB")

    def test_rm_element_ok(self) -> None:
        doc = abm.load_editable(self.yaml, self.root)
        abm.add_element(doc, "MT_A", type_id="MCB")
        abm.rm_element(doc, "MT_A")
        self.assertNotIn("MT_A", doc["elements"])

    def test_rm_element_not_found_raises(self) -> None:
        doc = abm.load_editable(self.yaml, self.root)
        with self.assertRaises(ValueError):
            abm.rm_element(doc, "NO_EXISTE")

    def test_rm_element_with_connection_raises(self) -> None:
        doc = abm.load_editable(self.yaml, self.root)
        abm.add_element(doc, "A", type_id="MCB", subtype="C10")
        abm.add_element(doc, "B", type_id="MCB", subtype="C10")
        abm.add_cable(doc, "L", section="1.5 mm2", colors=["BN"])
        abm.add_connection(doc, from_ref="A.1", via_ref="L.1", to_ref="B.1")
        with self.assertRaises(ValueError):
            abm.rm_element(doc, "A")

    def test_persist_writes_to_disk(self) -> None:
        doc = abm.load_editable(self.yaml, self.root)
        abm.add_element(doc, "MT_A", type_id="MCB")
        abm.persist(doc, self.yaml, self.root)
        doc2 = abm.load_editable(self.yaml, self.root)
        self.assertIn("MT_A", doc2["elements"])


# ---------------------------------------------------------------------------
# abm – cables
# ---------------------------------------------------------------------------

class TestABMCables(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp, self.root, self.yaml = make_project()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_add_cable_minimal(self) -> None:
        doc = abm.load_editable(self.yaml, self.root)
        abm.add_cable(doc, "L1", section="1.5 mm2", colors=["BN", "BU"])
        self.assertIn("L1", doc["cables"])
        self.assertEqual(doc["cables"]["L1"]["colors"], ["BN", "BU"])

    def test_add_cable_with_notes(self) -> None:
        doc = abm.load_editable(self.yaml, self.root)
        abm.add_cable(doc, "L2", section="2.5 mm2", colors=["BN"], notes="hilos sueltos")
        self.assertEqual(doc["cables"]["L2"]["notes"], "hilos sueltos")

    def test_add_cable_empty_colors_raises(self) -> None:
        doc = abm.load_editable(self.yaml, self.root)
        with self.assertRaises(ValueError):
            abm.add_cable(doc, "L3", section="1.5 mm2", colors=[])

    def test_add_cable_duplicate_raises(self) -> None:
        doc = abm.load_editable(self.yaml, self.root)
        abm.add_cable(doc, "L1", section="1.5 mm2", colors=["BN"])
        with self.assertRaises(ValueError):
            abm.add_cable(doc, "L1", section="1.5 mm2", colors=["BN"])

    def test_rm_cable_ok(self) -> None:
        doc = abm.load_editable(self.yaml, self.root)
        abm.add_cable(doc, "L1", section="1.5 mm2", colors=["BN"])
        abm.rm_cable(doc, "L1")
        self.assertNotIn("L1", doc["cables"])

    def test_rm_cable_not_found_raises(self) -> None:
        doc = abm.load_editable(self.yaml, self.root)
        with self.assertRaises(ValueError):
            abm.rm_cable(doc, "NO_EXISTE")

    def test_rm_cable_referenced_in_connection_raises(self) -> None:
        doc = abm.load_editable(self.yaml, self.root)
        abm.add_element(doc, "A", type_id="MCB", subtype="C10")
        abm.add_element(doc, "B", type_id="MCB", subtype="C10")
        abm.add_cable(doc, "L1", section="1.5 mm2", colors=["BN"])
        abm.add_connection(doc, from_ref="A.1", via_ref="L1.1", to_ref="B.1")
        with self.assertRaises(ValueError):
            abm.rm_cable(doc, "L1")


# ---------------------------------------------------------------------------
# abm – connections
# ---------------------------------------------------------------------------

class TestABMConnections(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp, self.root, self.yaml = make_project()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_add_and_rm_connection(self) -> None:
        doc = abm.load_editable(self.yaml, self.root)
        abm.add_connection(doc, from_ref="A.1", via_ref="L.1", to_ref="B.1")
        self.assertEqual(len(doc["connections"]), 1)
        abm.rm_connection(doc, 0)
        self.assertEqual(len(doc["connections"]), 0)

    def test_rm_connection_invalid_index_raises(self) -> None:
        doc = abm.load_editable(self.yaml, self.root)
        with self.assertRaises(ValueError):
            abm.rm_connection(doc, 0)

    def test_rm_connection_negative_index_raises(self) -> None:
        doc = abm.load_editable(self.yaml, self.root)
        abm.add_connection(doc, from_ref="A.1", via_ref="L.1", to_ref="B.1")
        with self.assertRaises(ValueError):
            abm.rm_connection(doc, -1)

    def test_connections_referencing_element(self) -> None:
        doc = abm.load_editable(self.yaml, self.root)
        abm.add_connection(doc, from_ref="MT_A.1", via_ref="L.1", to_ref="MT_B.1")
        abm.add_connection(doc, from_ref="MT_C.1", via_ref="L.1", to_ref="MT_D.1")
        hits = abm.connections_referencing_element(doc, "MT_A")
        self.assertEqual(hits, [0])
        hits_b = abm.connections_referencing_element(doc, "MT_D")
        self.assertEqual(hits_b, [1])


# ---------------------------------------------------------------------------
# abm – format_show
# ---------------------------------------------------------------------------

class TestFormatShow(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp, self.root, self.yaml = make_project()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_show_summary(self) -> None:
        doc = abm.load_editable(self.yaml, self.root)
        abm.add_element(doc, "MT_A", type_id="MCB")
        abm.add_cable(doc, "L1", section="1.5 mm2", colors=["BN"])
        text = abm.format_show(doc)
        self.assertIn("MT_A", text)
        self.assertIn("L1", text)
        self.assertIn("elements (1)", text)
        self.assertIn("cables (1)", text)

    def test_show_specific_element(self) -> None:
        doc = abm.load_editable(self.yaml, self.root)
        abm.add_element(doc, "MT_A", type_id="MCB", subtype="C10")
        text = abm.format_show(doc, element="MT_A")
        self.assertIn("element MT_A", text)
        self.assertIn("MCB", text)

    def test_show_missing_element_raises(self) -> None:
        doc = abm.load_editable(self.yaml, self.root)
        with self.assertRaises(ValueError):
            abm.format_show(doc, element="INEXISTENTE")

    def test_show_specific_cable(self) -> None:
        doc = abm.load_editable(self.yaml, self.root)
        abm.add_cable(doc, "L1", section="1.5 mm2", colors=["BN", "BU"])
        text = abm.format_show(doc, cable="L1")
        self.assertIn("cable L1", text)

    def test_show_missing_cable_raises(self) -> None:
        doc = abm.load_editable(self.yaml, self.root)
        with self.assertRaises(ValueError):
            abm.format_show(doc, cable="NO_EXISTE")


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


# ---------------------------------------------------------------------------
# Shell dispatcher (run_shell_line)
# ---------------------------------------------------------------------------

class TestShellDispatcher(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "zona_a").mkdir()
        self.yaml = self.root / "zona_a" / "doc.yaml"
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
        self._run(s, "use doc.yaml")
        self.assertIsNotNone(s.active_yaml)

    def test_add_element_via_shell(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        self._run(s, "use doc.yaml")
        code = self._run(s, "add element MT_Nuevo --type MCB --subtype C10")
        self.assertEqual(code, 0)
        doc = abm.load_editable(s.active_path(), self.root)
        self.assertIn("MT_Nuevo", doc["elements"])

    def test_rm_element_via_shell(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        self._run(s, "use doc.yaml")
        self._run(s, "add element MT_Nuevo --type MCB --subtype C10")
        code = self._run(s, "rm element MT_Nuevo")
        self.assertEqual(code, 0)
        doc = abm.load_editable(s.active_path(), self.root)
        self.assertNotIn("MT_Nuevo", doc["elements"])

    def test_add_cable_via_shell(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        self._run(s, "use doc.yaml")
        code = self._run(s, "add cable Linea_X --section '1.5 mm2' --colors BN,BU")
        self.assertEqual(code, 0)
        doc = abm.load_editable(s.active_path(), self.root)
        self.assertIn("Linea_X", doc["cables"])

    def test_add_dir_creates_directory(self) -> None:
        s = self._session()
        code = self._run(s, "add dir nueva_zona")
        self.assertEqual(code, 0)
        self.assertTrue((self.root / "nueva_zona").is_dir())

    def test_add_file_creates_yaml_and_activates(self) -> None:
        s = self._session()
        code = self._run(s, "add file nueva.yaml")
        self.assertEqual(code, 0)
        self.assertTrue((self.root / "nueva.yaml").exists())
        self.assertIsNotNone(s.active_yaml)

    def test_rm_file_removes_yaml(self) -> None:
        s = self._session()
        self._run(s, "add file temporal.yaml")
        code = self._run(s, "rm file temporal.yaml")
        self.assertEqual(code, 0)
        self.assertFalse((self.root / "temporal.yaml").exists())

    def test_rm_file_clears_active_if_active(self) -> None:
        s = self._session()
        self._run(s, "add file temporal.yaml")
        self.assertIsNotNone(s.active_yaml)
        self._run(s, "rm file temporal.yaml")
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


if __name__ == "__main__":
    unittest.main()
