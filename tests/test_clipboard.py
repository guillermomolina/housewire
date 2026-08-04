"""Tests for clipboard pack/paste and id renaming."""
from __future__ import annotations

import unittest

from fixtures import add_place
from housewire.site import abm
from housewire.site.clipboard import next_available_id, pack_selection, paste_payload
from housewire.site.delete_selection import delete_selection
from housewire.site.natural_sort import natural_sort_key
from housewire.site.tree import get_place_node
from tests.helpers import make_site


class TestNaturalSort(unittest.TestCase):
    def test_numeric_order(self) -> None:
        names = ["Interruptor_10", "Interruptor_2", "Interruptor_1"]
        ordered = sorted(names, key=natural_sort_key)
        self.assertEqual(ordered, ["Interruptor_1", "Interruptor_2", "Interruptor_10"])


class TestNextAvailableId(unittest.TestCase):
    def test_append_suffix(self) -> None:
        self.assertEqual(next_available_id({"Interruptor"}, "Interruptor"), "Interruptor_1")

    def test_increment(self) -> None:
        self.assertEqual(
            next_available_id({"Interruptor_1"}, "Interruptor_1"), "Interruptor_2"
        )

    def test_skip_taken(self) -> None:
        self.assertEqual(
            next_available_id({"Box", "Box_1", "Box_2"}, "Box"), "Box_3"
        )


class TestClipboard(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp, self.root, self.yaml = make_site()
        self.doc = abm.load_editable(self.yaml, self.root)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_pack_paste_place_rename(self) -> None:
        add_place(self.doc, "Room", type_id="Room")
        add_place(self.doc, "Box", under=("Room",), type_id="JunctionBox")
        payload = pack_selection(self.doc, ["Room/Box"])
        self.assertEqual(len(payload["items"]), 1)
        paste_payload(self.doc, parent_id="Room", payload=payload)
        room = get_place_node(self.doc, ("Room",))
        elements = room.get("elements") or {}
        self.assertIn("Box", elements)
        self.assertIn("Box_1", elements)

    def test_pack_cross_becomes_open_stub(self) -> None:
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
        payload = pack_selection(self.doc, ["Room/Box_A"])
        item = payload["items"][0]
        cables = (item["node"].get("cables") or {})
        found_open = False
        for entry in cables.values():
            if not isinstance(entry, dict):
                continue
            notes = str(entry.get("notes") or "")
            if "status: open" in notes:
                found_open = True
                self.assertTrue("from" in entry or "to" in entry)
                self.assertFalse("from" in entry and "to" in entry)
        self.assertTrue(found_open, msg=cables)
        # Broken conduit must not be in parent_cables as a full tube.
        parent_cables = payload.get("parent_cables") or {}
        self.assertNotIn("C1", parent_cables)

    def test_pack_internal_both_boxes(self) -> None:
        add_place(self.doc, "Room", type_id="Room")
        add_place(self.doc, "Box_A", under=("Room",), type_id="JunctionBox")
        add_place(self.doc, "Box_B", under=("Room",), type_id="JunctionBox")
        box_a = get_place_node(self.doc, ("Room", "Box_A"))
        box_b = get_place_node(self.doc, ("Room", "Box_B"))
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
        payload = pack_selection(self.doc, ["Room/Box_A", "Room/Box_B"])
        self.assertEqual(len(payload["items"]), 2)
        self.assertIn("L1_1", payload.get("parent_cables") or {})

    def test_cut_pack_then_delete(self) -> None:
        add_place(self.doc, "Room", type_id="Room")
        add_place(self.doc, "Box", under=("Room",), type_id="JunctionBox")
        payload = pack_selection(self.doc, ["Room/Box"])
        delete_selection(self.doc, ["Room/Box"])
        room = get_place_node(self.doc, ("Room",))
        self.assertNotIn("Box", room.get("elements") or {})
        paste_payload(self.doc, parent_id="Room", payload=payload)
        self.assertIn("Box", (room.get("elements") or {}))


if __name__ == "__main__":
    unittest.main()
