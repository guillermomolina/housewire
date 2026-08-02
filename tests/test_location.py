"""Tests for place metadata at YAML root, physical, inline."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml as _yaml

from fixtures import add_place, init_site, save_site
from housewire.house import is_place_type, load_catalog, validate_house_tree, _walk_locations
from housewire.project import abm
from housewire.project.io import HOUSEWIRE_YAML, create_empty_house_file
from housewire.project.tree import get_place_node


class TestDirectoryLocation(unittest.TestCase):
    """Root place fields in housewire.yaml supply metadata for nested places."""

    def test_location_place_validates_with_element(self) -> None:
        doc = _yaml.safe_load(
            "schema: house/v1\n"
            "type: JunctionBox\n"
            "subtype: '100x100 IP40'\n"
            "notes: 'mount: ceiling'\n"
            "elements:\n"
            "  Regleta:\n"
            "    type: TerminalStrip\n"
        )
        validate_house_tree(
            doc, catalog=load_catalog(), file_location_parts=["Parking", "Caja 1"]
        )

    def test_physical_subtitle_from_location(self) -> None:
        from housewire.house.physical import build_physical_model

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = init_site(root, type_id="House")
            add_place(doc, "Parking", type_id="Floor")
            add_place(
                doc,
                "Caja_derivacion_1",
                under=("Parking",),
                type_id="JunctionBox",
                label="Caja derivacion 1",
                subtype="100x100 IP40",
                notes="mount: ceiling",
            )
            caja = get_place_node(doc, ("Parking", "Caja_derivacion_1"))
            caja.setdefault("elements", {})["Regleta"] = {"type": "TerminalStrip"}
            save_site(root, doc)

            site_yaml = root / HOUSEWIRE_YAML
            model = build_physical_model(root, [site_yaml])
            subtitles = {n.subtitle for n in model.nodes.values()}
            labels = {n.display_label for n in model.nodes.values()}
            self.assertTrue(any("JunctionBox" in s for s in subtitles), subtitles)
            self.assertTrue(any("100x100" in s for s in subtitles), subtitles)
            self.assertTrue(any("ceiling" in s for s in subtitles), subtitles)
            self.assertIn("Caja_derivacion_1", labels)
            self.assertTrue(
                any("Caja derivacion 1" in s for s in subtitles),
                subtitles,
            )

    def test_create_inline_location_via_fixtures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = init_site(root, type_id="House")
            add_place(
                doc,
                "Cuadro_General",
                type_id="Panel",
                subtype="Cuadro",
                notes="IGA",
                label="Cuadro General",
            )
            save_site(root, doc)
            index = root / HOUSEWIRE_YAML
            self.assertTrue(index.is_file())
            loaded = _yaml.safe_load(index.read_text(encoding="utf-8"))
            panel = loaded["elements"]["Cuadro_General"]
            self.assertEqual(panel["type"], "Panel")
            self.assertEqual(panel["subtype"], "Cuadro")
            self.assertEqual(panel["label"], "Cuadro General")

    def test_create_location_normalizes_spaced_name(self) -> None:
        from housewire.house import location_id_from_name

        loc_id, label = location_id_from_name("Caja derivacion 6")
        self.assertEqual(loc_id, "Caja_derivacion_6")
        self.assertEqual(label, "Caja derivacion 6")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = init_site(root, type_id="House")
            add_place(doc, loc_id, type_id="JunctionBox", label=label)
            save_site(root, doc)
            loaded = _yaml.safe_load((root / HOUSEWIRE_YAML).read_text(encoding="utf-8"))
            self.assertEqual(loaded["elements"][loc_id]["label"], "Caja derivacion 6")

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
            validate_house_tree(
                doc, catalog=load_catalog(), file_location_parts=["Parking"]
            )
        self.assertTrue("self" in str(ctx.exception).lower() or "raiz" in str(ctx.exception).lower())

    def test_place_types_in_catalog(self) -> None:
        catalog = load_catalog()
        for type_id in (
            "Room",
            "JunctionBox",
            "DeviceBox",
            "LightPoint",
            "Panel",
            "Floor",
            "House",
            "Location",
        ):
            self.assertIn(type_id, catalog)
            self.assertTrue(is_place_type(type_id))
            self.assertNotIn("wireviz_skip", catalog[type_id])
            self.assertTrue(str(catalog[type_id].get("icon") or "").startswith("fa-"))

    def test_site_catalog_icon_overlay(self) -> None:
        from housewire.house import catalog_icon

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cat = root / "catalog"
            cat.mkdir()
            (cat / "Socket.yaml").write_text(
                "id: Socket\nicon: fa-outlet\n", encoding="utf-8"
            )
            merged = load_catalog(root)
            self.assertEqual(merged["Socket"]["icon"], "fa-outlet")
            self.assertEqual(merged["Socket"]["kind"], "element_type")
            self.assertEqual(
                catalog_icon("Socket", catalog=merged), "fa-outlet"
            )
            self.assertEqual(
                catalog_icon(
                    "Socket",
                    catalog=merged,
                    instance={"type": "Socket", "icon": "fa-star"},
                ),
                "fa-star",
            )


class TestLocationElementLegacyInline(unittest.TestCase):
    """Inline place types with nested content still work (escape hatch)."""

    def test_nested_element_validates(self) -> None:
        doc = _yaml.safe_load(
            """
schema: house/v1
elements:
  Caja_1:
    type: JunctionBox
    elements:
      Regleta:
        type: TerminalStrip
"""
        )
        validate_house_tree(
            doc, catalog=load_catalog(), file_location_parts=["Parking"]
        )

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
