"""Connection refs must stay within the declaring location and its sublocations."""
from __future__ import annotations

import unittest

import yaml as _yaml

from housewire.house import house_document_to_wireviz, load_catalog


class TestConnectionScope(unittest.TestCase):
    def _wv(self, doc_yaml: str, parts: list[str]) -> dict:
        doc = _yaml.safe_load(doc_yaml)
        return house_document_to_wireviz(
            doc, catalog=load_catalog(), file_location_parts=parts
        )

    def test_local_and_child_relative_ok(self) -> None:
        wv = self._wv(
            """
schema: house/v1
elements:
  Enchufe:
    type: Socket
  Caja 1:
    type: JunctionBox
    elements:
      Regleta:
        type: TerminalStrip
cables:
  L1:
    kind: power
    section: 1.5 mm2
    colors: [BN, BU]
connections:
  - from: Caja 1/Regleta.1
    via: L1.1
    to: Enchufe.L
""",
            ["Parking"],
        )
        flat = str(wv["connections"])
        self.assertIn("Parking__Caja_1__Regleta", flat)
        self.assertIn("Parking__Enchufe", flat)

    def test_parent_relative_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            self._wv(
                """
schema: house/v1
elements:
  Regleta:
    type: TerminalStrip
cables:
  L1:
    kind: power
    section: 1.5 mm2
    colors: [BN]
connections:
  - from: ../Enchufe.L
    via: L1.1
    to: Regleta.1
""",
                ["Parking", "Caja 1"],
            )
        self.assertIn("../", str(ctx.exception))

    def test_sibling_absolute_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            self._wv(
                """
schema: house/v1
elements:
  Regleta:
    type: TerminalStrip
cables:
  L1:
    kind: power
    section: 1.5 mm2
    colors: [BN]
connections:
  - from: Regleta.1
    via: L1.1
    to: /Parking/Caja 2/Regleta.1
""",
                ["Parking", "Caja 1"],
            )
        msg = str(ctx.exception).lower()
        self.assertTrue("fuera" in msg or "arbol" in msg or "ancestro" in msg)

    def test_absolute_into_child_ok(self) -> None:
        wv = self._wv(
            """
schema: house/v1
elements:
  Enchufe:
    type: Socket
  Caja 1:
    type: JunctionBox
    elements:
      Regleta:
        type: TerminalStrip
cables:
  L1:
    kind: power
    section: 1.5 mm2
    colors: [BN, BU]
connections:
  - from: /Parking/Caja 1/Regleta.1
    via: L1.1
    to: Enchufe.L
""",
            ["Parking"],
        )
        self.assertTrue(wv["connections"])
