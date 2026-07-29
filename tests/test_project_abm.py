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


# ---------------------------------------------------------------------------
# Naming convention: __ separator between all levels
# ---------------------------------------------------------------------------

class TestNamingConvention(unittest.TestCase):
    """Verifica que __ separa uniformemente niveles de location y nombre."""

    def _wv_names(self, yaml_rel: str, location_parts: list[str]) -> tuple[list[str], list[str]]:
        """Devuelve (connector_names, cable_names) generados para un YAML temporal."""
        import yaml as _yaml
        from housewire.house import house_document_to_wireviz, load_catalog

        doc = _yaml.safe_load(
            f"schema: house/v1\n"
            f"elements:\n"
            f"  Regleta:\n"
            f"    type: TerminalStrip\n"
            f"cables:\n"
            f"  Linea_test:\n"
            f"    kind: power\n"
            f"    section: '1.5 mm2'\n"
            f"    colors: [BN, BU]\n"
        )
        catalog = load_catalog()
        wv = house_document_to_wireviz(doc, catalog=catalog, file_location_parts=location_parts)
        return list(wv["connectors"]), list(wv["cables"])

    def test_single_location_level(self) -> None:
        connectors, cables = self._wv_names("test.yaml", ["Parking"])
        self.assertIn("Parking__Regleta", connectors)
        self.assertIn("Parking__Linea_test", cables)

    def test_two_location_levels(self) -> None:
        connectors, cables = self._wv_names("test.yaml", ["Parking", "Caja derivacion 1"])
        self.assertIn("Parking__Caja_derivacion_1__Regleta", connectors)
        self.assertIn("Parking__Caja_derivacion_1__Linea_test", cables)

    def test_three_location_levels(self) -> None:
        connectors, cables = self._wv_names(
            "test.yaml", ["Planta baja", "Recibidor", "Cuadro general"]
        )
        self.assertIn("Planta_baja__Recibidor__Cuadro_general__Regleta", connectors)

    def test_no_single_underscore_between_location_and_name(self) -> None:
        """Nunca debe aparecer un _ simple entre el prefijo de location y el nombre."""
        connectors, cables = self._wv_names("test.yaml", ["Parking", "Caja derivacion 1"])
        for name in connectors + cables:
            # el prefijo termina en 1; si hay _Regleta (guion simple) es un bug
            self.assertNotIn("_1_Regleta", name, f"Separador _ simple encontrado en: {name}")
            self.assertNotIn("_1_Linea", name, f"Separador _ simple encontrado en: {name}")

    def test_location_relative_to_file_path(self) -> None:
        """location explícito se concatena con file_location_parts, no los sustituye."""
        import yaml as _yaml
        from housewire.house import house_document_to_wireviz, load_catalog

        doc = _yaml.safe_load(
            "schema: house/v1\n"
            "location: [Caja derivacion 1]\n"
            "elements:\n"
            "  Regleta:\n"
            "    type: TerminalStrip\n"
        )
        catalog = load_catalog()
        wv = house_document_to_wireviz(
            doc, catalog=catalog, file_location_parts=["Parking"]
        )
        connectors = list(wv["connectors"])
        self.assertIn("Parking__Caja_derivacion_1__Regleta", connectors,
                      f"Esperado Parking__Caja_derivacion_1__Regleta, obtenido: {connectors}")

    def test_location_absolute_not_duplicated(self) -> None:
        """Si location ya empieza con file_location_parts, no se duplican."""
        import yaml as _yaml
        from housewire.house import house_document_to_wireviz, load_catalog

        doc = _yaml.safe_load(
            "schema: house/v1\n"
            "location: [Parking, Caja derivacion 1]\n"
            "elements:\n"
            "  Regleta:\n"
            "    type: TerminalStrip\n"
        )
        catalog = load_catalog()
        wv = house_document_to_wireviz(
            doc, catalog=catalog, file_location_parts=["Parking"]
        )
        connectors = list(wv["connectors"])
        # No debe aparecer Parking__Parking__... ni Parking__Parking__Caja...
        for name in connectors:
            self.assertNotIn("Parking__Parking", name,
                             f"Location duplicado encontrado: {name}")
        self.assertIn("Parking__Caja_derivacion_1__Regleta", connectors)




# ---------------------------------------------------------------------------
# type: Location — wireviz_skip, physical subtitle
# ---------------------------------------------------------------------------

class TestLocationElement(unittest.TestCase):
    """type: Location no genera conector WireViz pero sí etiqueta en físico."""

    def _doc_with_location_element(self, extra_notes: str = "") -> dict:
        import yaml as _yaml
        notes_line = f'    notes: "{extra_notes}"' if extra_notes else ""
        return _yaml.safe_load(
            "schema: house/v1\n"
            "elements:\n"
            "  MiCaja:\n"
            "    type: Location\n"
            "    subtype: '100x100 IP40'\n"
            + (f"    notes: '{extra_notes}'\n" if extra_notes else "") +
            "  Regleta:\n"
            "    type: TerminalStrip\n"
        )

    def test_location_not_in_wireviz_connectors(self) -> None:
        from housewire.house import house_document_to_wireviz, load_catalog
        doc = self._doc_with_location_element()
        catalog = load_catalog()
        wv = house_document_to_wireviz(doc, catalog=catalog, file_location_parts=["Parking"])
        connector_names = list(wv["connectors"])
        # Location no debe generar conector
        self.assertFalse(
            any("MiCaja" in n for n in connector_names),
            f"Location generó conector inesperado: {connector_names}",
        )

    def test_regular_element_still_generated(self) -> None:
        from housewire.house import house_document_to_wireviz, load_catalog
        doc = self._doc_with_location_element()
        catalog = load_catalog()
        wv = house_document_to_wireviz(doc, catalog=catalog, file_location_parts=["Parking"])
        connector_names = list(wv["connectors"])
        self.assertTrue(
            any("Regleta" in n for n in connector_names),
            f"Regleta no encontrada en: {connector_names}",
        )

    def test_location_in_catalog(self) -> None:
        from housewire.house import load_catalog
        catalog = load_catalog()
        self.assertIn("Location", catalog)
        self.assertTrue(catalog["Location"].get("wireviz_skip"))

    def test_location_wireviz_skip_flag(self) -> None:
        from housewire.house import load_catalog
        catalog = load_catalog()
        loc = catalog["Location"]
        self.assertTrue(loc.get("wireviz_skip"), "wireviz_skip debe ser true en Location")

    def test_physical_cluster_subtitle_from_location(self) -> None:
        """El subtítulo del cluster físico incluye subtype y notes del elemento Location."""
        import tempfile
        from housewire.house.physical import build_physical_model
        import yaml as _yaml

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Parking").mkdir()
            f = root / "Parking" / "caja.yaml"
            f.write_text(
                "schema: house/v1\n"
                "location: [Caja derivacion 1]\n"
                "elements:\n"
                "  MiCaja:\n"
                "    type: Location\n"
                "    subtype: '100x100 IP40'\n"
                "    notes: 'mount: ceiling'\n"
                "  Regleta:\n"
                "    type: TerminalStrip\n"
            )
            model = build_physical_model(root, [f])
            # Al menos un nodo debe estar en el cluster de Caja derivacion 1
            subtitles = {n.cluster_subtitle for n in model.nodes.values()}
            self.assertTrue(
                any("100x100" in s for s in subtitles),
                f"Subtítulo con subtype no encontrado: {subtitles}",
            )
            self.assertTrue(
                any("ceiling" in s for s in subtitles),
                f"Subtítulo con notes no encontrado: {subtitles}",
            )

    def test_physical_location_element_not_a_node(self) -> None:
        """El elemento Location no aparece como nodo en el diagrama físico."""
        import tempfile
        from housewire.house.physical import build_physical_model

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Parking").mkdir()
            f = root / "Parking" / "caja.yaml"
            f.write_text(
                "schema: house/v1\n"
                "elements:\n"
                "  MiCaja:\n"
                "    type: Location\n"
                "  Regleta:\n"
                "    type: TerminalStrip\n"
            )
            model = build_physical_model(root, [f])
            node_ids = list(model.nodes)
            self.assertFalse(
                any("MiCaja" in n for n in node_ids),
                f"Location apareció como nodo físico: {node_ids}",
            )
            self.assertTrue(
                any("Regleta" in n for n in node_ids),
                f"Regleta no encontrada: {node_ids}",
            )

    def test_abm_add_location_element(self) -> None:
        """Se puede añadir un elemento type Location desde el ABM."""
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        yaml_path = root / "test.yaml"
        create_empty_house_file(yaml_path)
        doc = abm.load_editable(yaml_path, root)
        abm.add_element(
            doc, "MiCaja",
            type_id="Location",
            subtype="100x100 IP40",
            notes="mount: ceiling",
        )
        self.assertIn("MiCaja", doc["elements"])
        self.assertEqual(doc["elements"]["MiCaja"]["type"], "Location")
        tmp.cleanup()

    def test_dot_output_contains_subtitle(self) -> None:
        """El .dot generado contiene el subtítulo del Location en la etiqueta del cluster."""
        import tempfile
        from housewire.house.physical import build_physical_model, model_to_dot

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Zona").mkdir()
            f = root / "Zona" / "test.yaml"
            f.write_text(
                "schema: house/v1\n"
                "elements:\n"
                "  Contenedor:\n"
                "    type: Location\n"
                "    subtype: '200x300'\n"
                "  Regleta:\n"
                "    type: TerminalStrip\n"
            )
            model = build_physical_model(root, [f])
            dot = model_to_dot(model)
            self.assertIn("200x300", dot, f"subtype no encontrado en dot:\n{dot}")


# ---------------------------------------------------------------------------
# Location element with nested content (inline sublocation)
# ---------------------------------------------------------------------------

class TestLocationInlineNested(unittest.TestCase):
    """type: Location con elements/cables/connections anidados = sublocation inline."""

    def _wv(self, doc_yaml: str, file_parts: list[str]) -> dict:
        import yaml as _yaml
        from housewire.house import house_document_to_wireviz, load_catalog
        doc = _yaml.safe_load(doc_yaml)
        return house_document_to_wireviz(doc, catalog=load_catalog(), file_location_parts=file_parts)

    def test_nested_element_gets_sublocation_prefix(self) -> None:
        wv = self._wv("""
schema: house/v1
elements:
  Caja_1:
    type: Location
    elements:
      Regleta:
        type: TerminalStrip
""", ["Parking"])
        self.assertIn("Parking__Caja_1__Regleta", wv["connectors"],
                      f"Got: {list(wv['connectors'])}")

    def test_nested_cable_gets_sublocation_prefix(self) -> None:
        wv = self._wv("""
schema: house/v1
elements:
  Caja_1:
    type: Location
    elements:
      Regleta:
        type: TerminalStrip
    cables:
      Linea_X:
        kind: power
        section: "1.5 mm2"
        colors: [BN, BU]
""", ["Parking"])
        self.assertIn("Parking__Caja_1__Linea_X", wv["cables"],
                      f"Got: {list(wv['cables'])}")

    def test_location_metadata_preserved_in_sublevel(self) -> None:
        """El elemento Location aparece en el subnivel para que physical lo use."""
        import yaml as _yaml
        from housewire.house import house_document_to_wireviz, load_catalog, _walk_locations, _as_location_list, path_location_parts
        doc = _yaml.safe_load("""
schema: house/v1
elements:
  Caja_1:
    type: Location
    subtype: "100x100 IP40"
    notes: "mount: ceiling"
    elements:
      Regleta:
        type: TerminalStrip
""")
        from housewire.house import _walk_locations
        fragments = _walk_locations(doc, ["Parking"])
        # debe haber un fragmento en [Parking, Caja_1] con Caja_1 como Location metadata
        sublevel = [f for loc, f in fragments if loc == ["Parking", "Caja_1"]]
        self.assertTrue(sublevel, f"No fragment found for Parking/Caja_1. Fragments: {[(l,list(f.get('elements',{}).keys())) for l,f in fragments]}")
        sub_elements = sublevel[0].get("elements") or {}
        # Caja_1 debe estar en el subnivel como metadato (sin nested content)
        self.assertIn("Caja_1", sub_elements)
        self.assertEqual(sub_elements["Caja_1"].get("type"), "Location")
        self.assertEqual(sub_elements["Caja_1"].get("subtype"), "100x100 IP40")

    def test_top_level_and_nested_coexist(self) -> None:
        """Elementos en el nivel raíz y en Location anidado coexisten sin colisión."""
        wv = self._wv("""
schema: house/v1
elements:
  Caja_1:
    type: Location
    elements:
      Regleta:
        type: TerminalStrip
  Enchufe_1:
    type: Socket
""", ["Parking"])
        self.assertIn("Parking__Caja_1__Regleta", wv["connectors"])
        self.assertIn("Parking__Enchufe_1", wv["connectors"])

    def test_deeply_nested_location(self) -> None:
        """Location dentro de Location genera prefijo de tres niveles."""
        wv = self._wv("""
schema: house/v1
elements:
  Zona_A:
    type: Location
    elements:
      Caja_1:
        type: Location
        elements:
          Regleta:
            type: TerminalStrip
""", ["Parking"])
        self.assertIn("Parking__Zona_A__Caja_1__Regleta", wv["connectors"],
                      f"Got: {list(wv['connectors'])}")

    def test_location_without_nested_content_is_metadata_only(self) -> None:
        """Location sin nested content no genera subnivel, solo aparece como metadata."""
        wv = self._wv("""
schema: house/v1
elements:
  Caja_1:
    type: Location
    subtype: "100x100"
  Regleta:
    type: TerminalStrip
""", ["Parking"])
        # Regleta en el nivel Parking (no en Parking__Caja_1)
        self.assertIn("Parking__Regleta", wv["connectors"],
                      f"Got: {list(wv['connectors'])}")
        # No hay sublevel
        self.assertNotIn("Parking__Caja_1__Regleta", wv["connectors"])

    def test_physical_subtitle_from_nested_location(self) -> None:
        """El diagrama físico muestra el subtítulo del Location anidado."""
        import tempfile
        from housewire.house.physical import build_physical_model
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Parking").mkdir()
            f = root / "Parking" / "parking.yaml"
            f.write_text(
                "schema: house/v1\n"
                "elements:\n"
                "  Caja_1:\n"
                "    type: Location\n"
                "    subtype: '100x100 IP40'\n"
                "    notes: 'mount: ceiling'\n"
                "    elements:\n"
                "      Regleta:\n"
                "        type: TerminalStrip\n"
            )
            model = build_physical_model(root, [f])
            subtitles = {n.cluster_subtitle for n in model.nodes.values()}
            self.assertTrue(any("100x100" in s for s in subtitles),
                            f"subtype no en subtítulo: {subtitles}")
