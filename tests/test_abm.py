"""Tests de project.abm (elements, cables, conduits, connections, show)."""
from __future__ import annotations

import unittest

from housewire.project import abm
from tests.helpers import make_project


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

    def test_add_cable_defaults(self) -> None:
        doc = abm.load_editable(self.yaml, self.root)
        abm.add_cable(doc, "L_def")
        self.assertEqual(doc["cables"]["L_def"]["type"], "Cable")
        self.assertEqual(doc["cables"]["L_def"]["subtype"], "power")
        self.assertEqual(doc["cables"]["L_def"]["section"], "1.5 mm2")
        self.assertEqual(doc["cables"]["L_def"]["colors"], ["BN", "BU"])

    def test_normalize_section_bare_number(self) -> None:
        self.assertEqual(abm.normalize_section("2.5"), "2.5 mm2")
        self.assertEqual(abm.normalize_section("1.5 mm2"), "1.5 mm2")

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
# abm – pending cables / conduits
# ---------------------------------------------------------------------------

class TestABMPendingAndConduits(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp, self.root, self.yaml = make_project()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_add_pending_cable_creates_cable_and_conduit(self) -> None:
        doc = abm.load_editable(self.yaml, self.root)
        cable, conduit = abm.add_pending_cable(doc, enter="B1", exit="B2")
        self.assertEqual(cable, "PEND_Linea_01")
        self.assertEqual(conduit, "Conducto_paso_01")
        self.assertIn(cable, doc["cables"])
        self.assertIn(conduit, doc["conduits"])
        self.assertIn("estado: pendiente", doc["cables"][cable]["notes"])
        self.assertIn("B1", doc["cables"][cable]["notes"])
        self.assertEqual(doc["cables"][cable]["type"], "Cable")
        self.assertEqual(doc["conduits"][conduit]["type"], "Conduit")
        self.assertEqual(doc["conduits"][conduit]["contains"], [cable])
        self.assertEqual(doc["conduits"][conduit]["from"], ".B1")
        self.assertEqual(doc["conduits"][conduit]["to"], ".B2")
        self.assertNotIn("route", doc["conduits"][conduit])
        self.assertEqual(doc.get("connections") or [], [])

    def test_pending_cable_numbering_increments(self) -> None:
        doc = abm.load_editable(self.yaml, self.root)
        c1, _ = abm.add_pending_cable(doc, enter="B1", exit="B2")
        c2, d2 = abm.add_pending_cable(doc, enter="B1", exit="B2", section="2.5")
        self.assertEqual(c1, "PEND_Linea_01")
        self.assertEqual(c2, "PEND_Linea_02")
        self.assertEqual(d2, "Conducto_paso_02")
        self.assertEqual(doc["cables"][c2]["section"], "2.5 mm2")

    def test_add_conduit_unknown_cable_raises(self) -> None:
        doc = abm.load_editable(self.yaml, self.root)
        with self.assertRaises(ValueError):
            abm.add_conduit(doc, "C1", contains=["NO_EXISTE"])

    def test_rm_cable_referenced_in_conduit_raises(self) -> None:
        doc = abm.load_editable(self.yaml, self.root)
        cable, _ = abm.add_pending_cable(doc, enter="B1", exit="B2")
        with self.assertRaises(ValueError):
            abm.rm_cable(doc, cable)

    def test_pending_rejects_undeclared_opening(self) -> None:
        doc = abm.load_editable(self.yaml, self.root)
        doc.update({
            "type": "JunctionBox",
            "openings": ["N1", "S1"],
        })
        with self.assertRaises(ValueError) as ctx:
            abm.add_pending_cable(doc, enter="N1", exit="N9")
        self.assertIn("N9", str(ctx.exception))

    def test_pending_ok_with_declared_openings(self) -> None:
        doc = abm.load_editable(self.yaml, self.root)
        doc.update({
            "type": "JunctionBox",
            "openings": ["N1", "S1"],
        })
        cable, _ = abm.add_pending_cable(doc, enter="N1", exit="S1")
        self.assertEqual(cable, "PEND_Linea_01")

    def test_pending_ok_with_panel_openings(self) -> None:
        doc = abm.load_editable(self.yaml, self.root)
        doc.update({
            "type": "Panel",
            "openings": ["B1-1", "N1"],
        })
        cable, _ = abm.add_pending_cable(doc, enter="B1-1", exit="N1")
        self.assertEqual(cable, "PEND_Linea_01")

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

    def test_show_lists_openings(self) -> None:
        doc = abm.load_editable(self.yaml, self.root)
        doc.update({
            "type": "JunctionBox",
            "mount": "ceiling",
            "opening_grid": {"NS": 2, "B": 1},
            "openings": ["B1-1", "W1"],
        })
        text = abm.format_show(doc)
        self.assertIn("openings (2):", text)
        self.assertIn("B1-1", text)
        self.assertIn("W1", text)
        self.assertIn("opening_grid:", text)
        self.assertIn("place (JunctionBox):", text)
        # openings not dumped twice inside location yaml
        self.assertNotIn("openings:", text.split("openings (2):")[0])
