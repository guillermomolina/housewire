"""Tests de convención de nombres WireViz (__ entre niveles)."""
from __future__ import annotations

import unittest

import yaml as _yaml

from housewire.house import house_document_to_wireviz, load_catalog


class TestNamingConvention(unittest.TestCase):
    """Verifica que __ separa uniformemente niveles de location y nombre."""

    def _wv_names(self, location_parts: list[str]) -> tuple[list[str], list[str]]:
        doc = _yaml.safe_load(
            "schema: house/v1\n"
            "elements:\n"
            "  Regleta:\n"
            "    type: TerminalStrip\n"
            "cables:\n"
            "  Linea_test:\n"
            "    kind: power\n"
            "    section: '1.5 mm2'\n"
            "    colors: [BN, BU]\n"
        )
        catalog = load_catalog()
        wv = house_document_to_wireviz(doc, catalog=catalog, file_location_parts=location_parts)
        return list(wv["connectors"]), list(wv["cables"])

    def test_single_location_level(self) -> None:
        connectors, cables = self._wv_names(["Parking"])
        self.assertIn("Parking__Regleta", connectors)
        self.assertIn("Parking__Linea_test", cables)

    def test_two_location_levels(self) -> None:
        connectors, cables = self._wv_names(["Parking", "Caja derivacion 1"])
        self.assertIn("Parking__Caja_derivacion_1__Regleta", connectors)
        self.assertIn("Parking__Caja_derivacion_1__Linea_test", cables)

    def test_three_location_levels(self) -> None:
        connectors, cables = self._wv_names(
            ["Planta baja", "Recibidor", "Cuadro general"]
        )
        self.assertIn("Planta_baja__Recibidor__Cuadro_general__Regleta", connectors)

    def test_no_single_underscore_between_location_and_name(self) -> None:
        connectors, cables = self._wv_names(["Parking", "Caja derivacion 1"])
        for name in connectors + cables:
            self.assertNotIn("_1_Regleta", name, f"Separador _ simple encontrado en: {name}")
            self.assertNotIn("_1_Linea", name, f"Separador _ simple encontrado en: {name}")

    def test_location_path_list_rejected(self) -> None:
        doc = _yaml.safe_load(
            "schema: house/v1\n"
            "location: [Caja derivacion 1]\n"
            "elements:\n"
            "  Regleta:\n"
            "    type: TerminalStrip\n"
        )
        with self.assertRaises(ValueError) as ctx:
            house_document_to_wireviz(
                doc, catalog=load_catalog(), file_location_parts=["Parking"]
            )
        self.assertIn("location:", str(ctx.exception))
        self.assertIn("lista", str(ctx.exception).lower())

    def test_path_only_determines_prefix(self) -> None:
        """El path del fichero manda; location: es metadatos, no jerarquia."""
        connectors, _ = self._wv_names(["Parking", "Caja derivacion 1"])
        self.assertIn("Parking__Caja_derivacion_1__Regleta", connectors)
