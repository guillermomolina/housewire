"""Tests de convención de nombres WireViz (__ entre niveles)."""
from __future__ import annotations

import unittest


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
