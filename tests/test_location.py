"""Tests de Location: self: en index.yaml, wireviz_skip, físico, anidación inline."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml as _yaml

from housewire.house import house_document_to_wireviz, load_catalog, _walk_locations
from housewire.project import abm
from housewire.project.io import create_empty_house_file, create_location_index


class TestSelfLocation(unittest.TestCase):
    """self: en index.yaml aporta metadatos Location del directorio."""

    def test_self_not_in_wireviz_connectors(self) -> None:
        doc = _yaml.safe_load(
            "schema: house/v1\n"
            "self:\n"
            "  type: Location\n"
            "  subtype: '100x100 IP40'\n"
            "  notes: 'mount: ceiling'\n"
            "elements:\n"
            "  Regleta:\n"
            "    type: TerminalStrip\n"
        )
        wv = house_document_to_wireviz(
            doc, catalog=load_catalog(), file_location_parts=["Parking", "Caja 1"]
        )
        names = list(wv["connectors"])
        self.assertTrue(any(n.endswith("__Regleta") or n == "Parking__Caja_1__Regleta" for n in names), names)
        self.assertEqual(len(names), 1, names)

    def test_physical_subtitle_from_self(self) -> None:
        from housewire.house.physical import build_physical_model

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            caja = root / "Parking" / "Caja derivacion 1"
            caja.mkdir(parents=True)
            (caja / "index.yaml").write_text(
                "schema: house/v1\n"
                "self:\n"
                "  type: Location\n"
                "  subtype: '100x100 IP40'\n"
                "  notes: 'mount: ceiling'\n"
                "elements:\n"
                "  Regleta:\n"
                "    type: TerminalStrip\n",
                encoding="utf-8",
            )
            model = build_physical_model(root, [caja / "index.yaml"])
            subtitles = {n.cluster_subtitle for n in model.nodes.values()}
            self.assertTrue(any("100x100" in s for s in subtitles), subtitles)
            self.assertTrue(any("ceiling" in s for s in subtitles), subtitles)

    def test_create_location_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "Cuadro General"
            index = create_location_index(target, subtype="Cuadro", notes="IGA")
            self.assertTrue(index.is_file())
            doc = _yaml.safe_load(index.read_text(encoding="utf-8"))
            self.assertEqual(doc["self"]["type"], "Location")
            self.assertEqual(doc["self"]["subtype"], "Cuadro")


class TestLocationElementLegacyInline(unittest.TestCase):
    """type: Location anidado inline sigue funcionando (escape hatch)."""

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
    type: Location
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
    type: Location
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

    def test_abm_add_location_element(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        yaml_path = root / "test.yaml"
        create_empty_house_file(yaml_path)
        doc = abm.load_editable(yaml_path, root)
        abm.add_element(
            doc,
            "MiCaja",
            type_id="Location",
            subtype="100x100 IP40",
            notes="mount: ceiling",
        )
        self.assertEqual(doc["elements"]["MiCaja"]["type"], "Location")
        tmp.cleanup()

    def test_location_in_catalog(self) -> None:
        catalog = load_catalog()
        self.assertIn("Location", catalog)
        self.assertTrue(catalog["Location"].get("wireviz_skip"))
