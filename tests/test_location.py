"""Tests de type: Location (wireviz_skip, físico, anidación inline)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from housewire.project import abm
from housewire.project.io import create_empty_house_file


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
