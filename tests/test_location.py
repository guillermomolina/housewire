"""Tests for place metadata at YAML root, wireviz_skip, physical, inline."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml as _yaml

from housewire.house import house_document_to_wireviz, load_catalog, _walk_locations
from housewire.project import abm
from housewire.project.io import create_empty_house_file, create_location_index


class TestDirectoryLocation(unittest.TestCase):
    """Root place fields in housewire.yaml supply metadata for the directory."""

    def test_location_not_in_wireviz_connectors(self) -> None:
        doc = _yaml.safe_load(
            "schema: house/v1\n"
            "type: JunctionBox\n"
            "subtype: '100x100 IP40'\n"
            "notes: 'mount: ceiling'\n"
            "elements:\n"
            "  Regleta:\n"
            "    type: TerminalStrip\n"
        )
        wv = house_document_to_wireviz(
            doc, catalog=load_catalog(), file_location_parts=["Parking", "Caja 1"]
        )
        names = list(wv["connectors"])
        self.assertTrue(
            any(n.endswith("__Regleta") or n == "Parking__Caja_1__Regleta" for n in names),
            names,
        )
        self.assertEqual(len(names), 1, names)

    def test_physical_subtitle_from_location(self) -> None:
        from housewire.house.physical import build_physical_model

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            caja = root / "Parking" / "Caja_derivacion_1"
            caja.mkdir(parents=True)
            (caja / "housewire.yaml").write_text(
                "schema: house/v1\n"
                "type: JunctionBox\n"
                "label: 'Caja derivacion 1'\n"
                "subtype: '100x100 IP40'\n"
                "notes: 'mount: ceiling'\n"
                "elements:\n"
                "  Regleta:\n"
                "    type: TerminalStrip\n",
                encoding="utf-8",
            )
            model = build_physical_model(root, [caja / "housewire.yaml"])
            subtitles = {n.cluster_subtitle for n in model.nodes.values()}
            labels = {n.cluster_label for n in model.nodes.values()}
            self.assertTrue(any("JunctionBox" in s for s in subtitles), subtitles)
            self.assertTrue(any("100x100" in s for s in subtitles), subtitles)
            self.assertTrue(any("ceiling" in s for s in subtitles), subtitles)
            self.assertTrue(
                any("Caja derivacion 1" in lab for lab in labels),
                labels,
            )

    def test_create_location_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "Cuadro_General"
            index = create_location_index(
                target,
                type_id="Panel",
                subtype="Cuadro",
                notes="IGA",
                label="Cuadro General",
            )
            self.assertTrue(index.is_file())
            doc = _yaml.safe_load(index.read_text(encoding="utf-8"))
            self.assertEqual(doc["type"], "Panel")
            self.assertEqual(doc["subtype"], "Cuadro")
            self.assertEqual(doc["label"], "Cuadro General")

    def test_create_location_normalizes_spaced_name(self) -> None:
        from housewire.house import location_id_from_name

        loc_id, label = location_id_from_name("Caja derivacion 6")
        self.assertEqual(loc_id, "Caja_derivacion_6")
        self.assertEqual(label, "Caja derivacion 6")
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / loc_id
            index = create_location_index(
                target, type_id="JunctionBox", label=label
            )
            doc = _yaml.safe_load(index.read_text(encoding="utf-8"))
            self.assertEqual(doc["label"], "Caja derivacion 6")
            self.assertEqual(target.name, "Caja_derivacion_6")

    def test_self_block_rejected(self) -> None:
        doc = _yaml.safe_load(
            "schema: house/v1\n"
            "self:\n"
            "  type: Location\n"
            "elements:\n"
            "  Regleta:\n"
            "    type: TerminalStrip\n"
        )
        with self.assertRaises(ValueError) as ctx:
            house_document_to_wireviz(
                doc, catalog=load_catalog(), file_location_parts=["Parking"]
            )
        self.assertTrue("self" in str(ctx.exception).lower() or "raiz" in str(ctx.exception).lower())

    def test_place_types_in_catalog(self) -> None:
        catalog = load_catalog()
        for type_id in (
            "Room",
            "JunctionBox",
            "DeviceBox",
            "Panel",
            "Floor",
            "House",
            "Location",
        ):
            self.assertIn(type_id, catalog)
            self.assertTrue(catalog[type_id].get("wireviz_skip"))


class TestLocationElementLegacyInline(unittest.TestCase):
    """Inline place types with nested content still work (escape hatch)."""

    def _wv(self, doc_yaml: str, file_parts: list[str]) -> dict:
        doc = _yaml.safe_load(doc_yaml)
        return house_document_to_wireviz(
            doc, catalog=load_catalog(), file_location_parts=file_parts
        )

    def test_nested_element_gets_sublocation_prefix(self) -> None:
        wv = self._wv(
            """
schema: house/v1
elements:
  Caja_1:
    type: JunctionBox
    elements:
      Regleta:
        type: TerminalStrip
""",
            ["Parking"],
        )
        self.assertIn("Parking__Caja_1__Regleta", wv["connectors"])

    def test_location_metadata_preserved_in_sublevel(self) -> None:
        doc = _yaml.safe_load(
            """
schema: house/v1
elements:
  Caja_1:
    type: JunctionBox
    subtype: "100x100 IP40"
    notes: "mount: ceiling"
    elements:
      Regleta:
        type: TerminalStrip
"""
        )
        fragments = _walk_locations(doc, ["Parking"])
        sublevel = [f for loc, f in fragments if loc == ["Parking", "Caja_1"]]
        self.assertTrue(sublevel)
        self.assertIn("Caja_1", sublevel[0].get("elements") or {})

    def test_abm_add_place_element(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        yaml_path = root / "test.yaml"
        create_empty_house_file(yaml_path)
        doc = abm.load_editable(yaml_path, root)
        abm.add_element(
            doc,
            "MiCaja",
            type_id="JunctionBox",
            subtype="100x100 IP40",
            notes="mount: ceiling",
        )
        self.assertEqual(doc["elements"]["MiCaja"]["type"], "JunctionBox")
        tmp.cleanup()
