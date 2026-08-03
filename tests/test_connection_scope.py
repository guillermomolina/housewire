"""Conductor terminal refs must stay within the declaring location tree."""
from __future__ import annotations

import unittest

import yaml as _yaml

from housewire.house import load_catalog, validate_house_tree


class TestConnectionScope(unittest.TestCase):
    def _validate(self, doc_yaml: str, parts: list[str]) -> None:
        doc = _yaml.safe_load(doc_yaml)
        validate_house_tree(
            doc, catalog=load_catalog(), file_location_parts=parts
        )

    def test_local_and_child_relative_ok(self) -> None:
        self._validate(
            """
schema: house/v2
elements:
  Enchufe:
    type: Socket
  Caja 1:
    type: JunctionBox
    elements:
      Regleta:
        type: TerminalStrip
cables:
  L1_1:
    type: Conductor
    section: 1.5 mm2
    color: BN
    from: Caja 1/Regleta.N1
    to: Enchufe.N1
""",
            ["Parking"],
        )

    def test_parent_relative_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            self._validate(
                """
schema: house/v2
elements:
  Regleta:
    type: TerminalStrip
cables:
  L1_1:
    type: Conductor
    section: 1.5 mm2
    color: BN
    from: ../Enchufe.N1
    to: Regleta.N1
""",
                ["Parking", "Caja 1"],
            )
        self.assertIn("../", str(ctx.exception))

    def test_sibling_absolute_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            self._validate(
                """
schema: house/v2
elements:
  Regleta:
    type: TerminalStrip
cables:
  L1_1:
    type: Conductor
    section: 1.5 mm2
    color: BN
    from: Regleta.N1
    to: /Parking/Caja 2/Regleta.N1
""",
                ["Parking", "Caja 1"],
            )
        msg = str(ctx.exception).lower()
        self.assertTrue(
            "outside" in msg or "tree" in msg or "ancestor" in msg,
            msg,
        )

    def test_absolute_into_child_ok(self) -> None:
        self._validate(
            """
schema: house/v2
elements:
  Enchufe:
    type: Socket
  Caja 1:
    type: JunctionBox
    elements:
      Regleta:
        type: TerminalStrip
cables:
  L1_1:
    type: Conductor
    section: 1.5 mm2
    color: BN
    from: /Parking/Caja 1/Regleta.N1
    to: Enchufe.N1
""",
            ["Parking"],
        )

    def test_cross_location_cable_on_ancestor_local_conduit_ok(self) -> None:
        """Cable at LCA; local hop conduit may list it in contains (no ../)."""
        self._validate(
            """
schema: house/v2
type: House
elements:
  Parking:
    type: Floor
    elements:
      Caja_A:
        type: JunctionBox
        openings: [E1]
      Caja_B:
        type: JunctionBox
        openings: [W1]
    cables:
      Conducto_local:
        type: Conduit
        subtype: tube
        from: Caja_A.E1
        to: Caja_B.W1
        contains: [Linea_cross]
  Escalera:
    type: Stair
    openings: [N1]
cables:
  Linea_cross_1:
    type: Conductor
    section: 1.5 mm2
    color: BN
    from: Parking/Caja_A.N1
    to: Escalera.N1
  Linea_cross:
    type: Cable
    contains: [Linea_cross_1]
    color: BK
    subtype: power
    section: 1.5 mm2
""",
            [],
        )

    def test_conduit_contains_sibling_cable_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            self._validate(
                """
schema: house/v2
type: House
elements:
  Floor_A:
    type: Floor
    cables:
      Linea_A_1:
        type: Conductor
        section: 1.5 mm2
        color: BN
        from: Box.N1
        to: Box.N2
      Linea_A:
        type: Cable
        contains: [Linea_A_1]
        color: BK
        subtype: power
        section: 1.5 mm2
    elements:
      Box:
        type: JunctionBox
  Floor_B:
    type: Floor
    elements:
      Box_B:
        type: JunctionBox
        openings: [N1, S1]
    cables:
      Conducto_B:
        type: Conduit
        subtype: tube
        from: Box_B.N1
        to: Box_B.S1
        contains: [Linea_A]
""",
                [],
            )
        self.assertIn("missing cables entry", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
