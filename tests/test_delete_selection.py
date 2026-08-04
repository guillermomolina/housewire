"""Tests for cascade delete_selection."""
from __future__ import annotations

import unittest

from housewire.site import abm
from housewire.site.delete_selection import (
    delete_selection,
    suggest_location_after_delete,
)
from housewire.site.tree import get_place_node
from tests.helpers import make_site


class TestDeleteSelection(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp, self.root, self.yaml = make_site()
        self.doc = abm.load_editable(self.yaml, self.root)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _add_room_box(self) -> None:
        from housewire.site.tree import add_place  # type: ignore

        # Prefer session helpers used elsewhere
        from tests.fixtures import add_place as fix_add

        fix_add(self.doc, "Room", type_id="Room", label="Room")
        fix_add(self.doc, "Box_A", under=("Room",), type_id="JunctionBox")
        fix_add(self.doc, "Box_B", under=("Room",), type_id="JunctionBox")
        box_a = get_place_node(self.doc, ("Room", "Box_A"))
        box_b = get_place_node(self.doc, ("Room", "Box_B"))
        box_a["openings"] = ["E1"]
        box_b["openings"] = ["W1"]
        abm.add_element(box_a, "Strip", type_id="TerminalStrip")
        abm.add_element(box_b, "Strip", type_id="TerminalStrip")

    def test_delete_isolated_element(self) -> None:
        abm.add_element(self.doc, "MT", type_id="MCB")
        result = delete_selection(self.doc, ["MT"])
        self.assertNotIn("MT", self.doc.get("elements") or {})
        self.assertIn("MT", result.deleted)

    def test_delete_internal_cable_with_place(self) -> None:
        from tests.fixtures import add_place

        add_place(self.doc, "Room", type_id="Room")
        add_place(self.doc, "Box", under=("Room",), type_id="JunctionBox")
        box = get_place_node(self.doc, ("Room", "Box"))
        abm.add_element(box, "A", type_id="MCB")
        abm.add_element(box, "B", type_id="MCB")
        abm.add_conductor(
            box, "L1", section="1.5", color="BN", from_ref="A.N1", to_ref="B.N1"
        )
        result = delete_selection(self.doc, ["Room/Box"])
        room = get_place_node(self.doc, ("Room",))
        self.assertNotIn("Box", room.get("elements") or {})
        self.assertIn("Room/Box", result.deleted)

    def test_sever_cross_cable_and_delete_conduit(self) -> None:
        from tests.fixtures import add_place

        add_place(self.doc, "Room", type_id="Room")
        add_place(self.doc, "Box_A", under=("Room",), type_id="JunctionBox")
        add_place(self.doc, "Box_B", under=("Room",), type_id="JunctionBox")
        box_a = get_place_node(self.doc, ("Room", "Box_A"))
        box_b = get_place_node(self.doc, ("Room", "Box_B"))
        box_a["openings"] = ["E1"]
        box_b["openings"] = ["W1"]
        abm.add_element(box_a, "Strip", type_id="TerminalStrip")
        abm.add_element(box_b, "Strip", type_id="TerminalStrip")
        room = get_place_node(self.doc, ("Room",))
        abm.add_conductor(
            room,
            "L1_1",
            section="1.5",
            color="BN",
            from_ref="Box_A/Strip.N1",
            to_ref="Box_B/Strip.N1",
        )
        abm.add_sheath(room, "L1", contains=["L1_1"], section="1.5")
        abm.add_conduit(
            room,
            "C1",
            contains=["L1"],
            from_ref="Box_A.E1",
            to_ref="Box_B.W1",
        )
        result = delete_selection(self.doc, ["Room/Box_A"])
        room = get_place_node(self.doc, ("Room",))
        self.assertNotIn("Box_A", room.get("elements") or {})
        # Conduit must be gone (lost an endpoint).
        cables = room.get("cables") or {}
        self.assertNotIn("C1", cables)
        # Cable relocated to Box_B as open run.
        box_b = get_place_node(self.doc, ("Room", "Box_B"))
        b_cables = box_b.get("cables") or {}
        # Sheath + conductor should live on Box_B now.
        found = False
        for name, entry in b_cables.items():
            if not isinstance(entry, dict):
                continue
            if entry.get("type") == "Conductor" or str(
                entry.get("type") or ""
            ).endswith("Conductor"):
                self.assertTrue(
                    "from" not in entry or "to" not in entry,
                    msg=f"{name} should be severed: {entry}",
                )
                notes = str(entry.get("notes") or "")
                self.assertIn("status: open", notes)
                found = True
        self.assertTrue(found or any("L1" in n for n in b_cables), b_cables)
        self.assertTrue(result.severed or result.relocated)

    def test_suggest_location(self) -> None:
        loc = suggest_location_after_delete(
            "Room/Box_A", deleted_places={("Room", "Box_A")}
        )
        self.assertEqual(loc, "Room")


if __name__ == "__main__":
    unittest.main()
