"""Tests for view.physical layout helpers and UI physical graph."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fixtures import add_place, init_site, save_site
from housewire.project import abm
from housewire.project.io import HOUSEWIRE_YAML
from housewire.project.tree import get_place_node
from housewire.project.view_layout import (
    get_electrical_position,
    get_physical_page,
    get_physical_position,
    set_electrical_position,
    set_physical_page,
    set_physical_position,
)
from housewire.ui.physical_graph import (
    apply_auto_layout,
    apply_electrical_auto_layout,
    apply_electrical_positions,
    apply_positions,
    build_physical_graph,
    list_canvas_locations,
    list_site_outline,
)


def _build_parking_wiring_site(root: Path) -> None:
    doc = init_site(root, type_id="House", label="Site")
    add_place(doc, "Parking", type_id="Floor", label="Parking")
    add_place(
        doc, "Caja_4", under=("Parking",), type_id="JunctionBox", label="Caja 4"
    )
    add_place(
        doc, "Enchufe_1", under=("Parking",), type_id="DeviceBox", label="Enchufe 1"
    )
    caja = get_place_node(doc, ("Parking", "Caja_4"))
    caja["openings"] = ["W2", "B1-1"]
    abm.add_element(caja, "Regleta", type_id="TerminalStrip")
    enchufe = get_place_node(doc, ("Parking", "Enchufe_1"))
    abm.add_element(enchufe, "Socket", type_id="Socket")
    parking = get_place_node(doc, ("Parking",))
    abm.add_cable(parking, "Linea_1", section="1.5", colors=["BN", "BU"])
    abm.add_conduit(
        parking,
        "Conducto_1",
        contains=["Linea_1"],
        from_ref="Caja_4.W2",
        to_ref="Enchufe_1.N1",
    )
    abm.add_connection(
        parking,
        from_ref="Caja_4/Regleta.1",
        via_ref="Linea_1.1",
        to_ref="Enchufe_1/Socket.L",
    )
    save_site(root, doc)


class TestViewLayout(unittest.TestCase):
    def test_set_get_physical_position(self) -> None:
        place: dict = {"schema": "house/v1", "type": "JunctionBox"}
        self.assertIsNone(get_physical_position(place))
        set_physical_position(place, 10, 20, rotation=90)
        self.assertEqual(get_physical_position(place), (10.0, 20.0))
        self.assertEqual(place["view"]["physical"]["rotation"], 90)

    def test_physical_position_rejects_negatives(self) -> None:
        place: dict = {"schema": "house/v1", "type": "JunctionBox"}
        with self.assertRaises(ValueError):
            set_physical_position(place, -1, 10)
        with self.assertRaises(ValueError):
            set_physical_position(place, 10, -0.5)
        place["view"] = {"physical": {"x": -5, "y": 20}}
        self.assertIsNone(get_physical_position(place))

    def test_page_defaults_and_set(self) -> None:
        place: dict = {"schema": "house/v1", "type": "Room"}
        page = get_physical_page(place)
        self.assertEqual(page["representation"], "line")
        self.assertEqual(page["width"], 2000.0)
        set_physical_page(place, representation="tube", width=1200)
        page2 = get_physical_page(place)
        self.assertEqual(page2["representation"], "tube")
        self.assertEqual(page2["width"], 1200.0)
        with self.assertRaises(ValueError):
            set_physical_page(place, representation="blob")

    def test_set_get_electrical_position(self) -> None:
        element: dict = {"type": "Socket"}
        self.assertIsNone(get_electrical_position(element))
        set_electrical_position(element, 24, 40, rotation=90)
        self.assertEqual(get_electrical_position(element), (24.0, 40.0))
        self.assertEqual(element["view"]["electrical"]["rotation"], 90)
        with self.assertRaises(ValueError):
            set_electrical_position(element, -1, 0)


class TestPhysicalGraph(unittest.TestCase):
    def test_build_graph_and_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build_parking_wiring_site(root)

            locations = list_canvas_locations(root)
            ids = {row["id"] for row in locations}
            self.assertIn("Parking", ids)
            self.assertIn(".", ids)  # House root also has children
            by_id = {row["id"]: row for row in locations}
            self.assertEqual(by_id["."]["depth"], 0)
            self.assertEqual(by_id["Parking"]["depth"], 1)
            self.assertTrue(by_id["Parking"]["selectable"])
            # Tree order: root before child
            self.assertLess(
                [r["id"] for r in locations].index("."),
                [r["id"] for r in locations].index("Parking"),
            )

            # House canvas depth 1: only direct children (Parking)
            house_graph = build_physical_graph(root, ".", depth=1)
            self.assertEqual(
                {n["id"] for n in house_graph["nodes"]}, {"Parking"}
            )
            self.assertEqual(house_graph["depth"], 1)
            self.assertEqual(house_graph["max_depth"], 2)
            parking_node = next(
                n for n in house_graph["nodes"] if n["id"] == "Parking"
            )
            self.assertTrue(parking_node["expandable"])
            self.assertIsNone(parking_node["parent"])
            # No YAML name → canvas display is the leaf id
            self.assertEqual(parking_node["display_name"], "Parking")
            self.assertEqual(parking_node["display_label"], "Parking")
            # Window size includes hidden descendants (same at deeper depth).
            self.assertGreater(parking_node["w"], 120)
            self.assertGreater(parking_node["h"], 56)

            # House depth 2: boxes nested under Parking
            deep = build_physical_graph(root, ".", depth=2)
            self.assertEqual(
                {n["id"] for n in deep["nodes"]},
                {"Parking", "Parking/Caja_4", "Parking/Enchufe_1"},
            )
            parking_deep = next(n for n in deep["nodes"] if n["id"] == "Parking")
            self.assertEqual(parking_deep["w"], parking_node["w"])
            self.assertEqual(parking_deep["h"], parking_node["h"])
            caja_nested = next(
                n for n in deep["nodes"] if n["id"] == "Parking/Caja_4"
            )
            self.assertEqual(caja_nested["parent"], "Parking")
            self.assertEqual(len(deep["edges"]), 1)
            self.assertEqual(deep["edges"][0]["from"], "Parking/Caja_4")
            self.assertEqual(deep["edges"][0]["to"], "Parking/Enchufe_1")

            graph = build_physical_graph(root, "Parking")
            self.assertEqual(graph["location"]["id"], "Parking")
            self.assertEqual(len(graph["nodes"]), 2)
            self.assertEqual(len(graph["edges"]), 1)
            self.assertEqual(graph["edges"][0]["from"], "Caja_4")
            self.assertEqual(graph["edges"][0]["to"], "Enchufe_1")
            elem_ids = {e["id"] for e in graph["elements"]}
            self.assertEqual(elem_ids, {"Caja_4/Regleta", "Enchufe_1/Socket"})
            self.assertEqual(len(graph["cable_edges"]), 1)
            self.assertEqual(graph["cable_edges"][0]["from"], "Caja_4/Regleta")
            self.assertEqual(graph["cable_edges"][0]["to"], "Enchufe_1/Socket")
            self.assertEqual(graph["cable_edges"][0].get("conduit"), "Conducto_1")
            self.assertEqual(graph["cable_edges"][0].get("from_opening"), "W2")
            hops = graph["cable_edges"][0].get("conduit_hops")
            self.assertEqual(len(hops), 1)
            self.assertEqual(hops[0]["conduit"], "Conducto_1")
            self.assertEqual(hops[0]["from_opening"], "W2")
            self.assertEqual(hops[0]["to_opening"], "N1")
            caja_node = next(n for n in graph["nodes"] if n["id"] == "Caja_4")
            # Elements enlarge the leaf window past the default leaf size.
            self.assertGreater(caja_node["h"], 56)
            faces = {o["id"]: o["face"] for o in caja_node["openings"]}
            self.assertEqual(faces.get("B1-1"), "B")
            self.assertIsNotNone(caja_node["x"])
            self.assertIsNotNone(caja_node["w"])

            session_docs: dict[Path, dict] = {}
            updated = apply_auto_layout(
                root, "Parking", session_docs=session_docs, force=False
            )
            self.assertEqual(sorted(updated), ["Caja_4", "Enchufe_1"])
            elem_updated = apply_electrical_auto_layout(
                root, "Parking", session_docs=session_docs, force=False
            )
            self.assertEqual(
                sorted(elem_updated), ["Caja_4/Regleta", "Enchufe_1/Socket"]
            )
            graph2 = build_physical_graph(
                root, "Parking", session_docs=session_docs
            )
            for node in graph2["nodes"]:
                self.assertIsNotNone(node["x"])
                self.assertIsNotNone(node["y"])
            for elem in graph2["elements"]:
                self.assertIsNotNone(elem["x"])
                self.assertIsNotNone(elem["y"])

            apply_positions(
                root,
                "Parking",
                {"Caja_4": {"x": 42, "y": 99}},
                session_docs=session_docs,
            )
            apply_electrical_positions(
                root,
                "Parking",
                {"Caja_4/Regleta": {"x": 12, "y": 34}},
                session_docs=session_docs,
            )
            graph3 = build_physical_graph(
                root, "Parking", session_docs=session_docs
            )
            caja = next(n for n in graph3["nodes"] if n["id"] == "Caja_4")
            self.assertEqual(caja["x"], 42.0)
            self.assertEqual(caja["y"], 99.0)
            regleta = next(
                e for e in graph3["elements"] if e["id"] == "Caja_4/Regleta"
            )
            self.assertEqual(regleta["x"], 12.0)
            self.assertEqual(regleta["y"], 34.0)

            outline = list_site_outline(root)
            kinds = {(row["kind"], row["id"]) for row in outline}
            self.assertIn(("place", "Parking"), kinds)
            self.assertIn(("place", "Parking/Caja_4"), kinds)
            self.assertIn(("element", "Parking/Caja_4/Regleta"), kinds)
            self.assertIn(("element", "Parking/Enchufe_1/Socket"), kinds)
            socket = next(
                r for r in outline if r["id"] == "Parking/Enchufe_1/Socket"
            )
            self.assertEqual(socket.get("icon"), "fa-plug")

    def test_multi_hop_cable_follows_conduit_chain(self) -> None:
        """Cable listed in several conduits gets a hop path between hosts."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = init_site(root, type_id="House", label="Site")
            add_place(doc, "Parking", type_id="Floor", label="Parking")
            for name, label in (
                ("A", "Caja A"),
                ("B", "Caja B"),
                ("C", "Caja C"),
            ):
                add_place(
                    doc,
                    name,
                    under=("Parking",),
                    type_id="JunctionBox",
                    label=label,
                )
            for parts in (("Parking", "A"), ("Parking", "B"), ("Parking", "C")):
                box = get_place_node(doc, parts)
                box["openings"] = ["N1", "S1"]
                abm.add_element(box, "Regleta", type_id="TerminalStrip")
            parking = get_place_node(doc, ("Parking",))
            abm.add_cable(parking, "Linea_AC", section="1.5", colors=["BN"])
            abm.add_conduit(
                parking,
                "Conducto_AB",
                contains=["Linea_AC"],
                from_ref="A.S1",
                to_ref="B.N1",
            )
            abm.add_conduit(
                parking,
                "Conducto_BC",
                contains=["Linea_AC"],
                from_ref="B.S1",
                to_ref="C.N1",
            )
            abm.add_connection(
                parking,
                from_ref="A/Regleta.1",
                via_ref="Linea_AC.1",
                to_ref="C/Regleta.1",
            )
            save_site(root, doc)

            graph = build_physical_graph(root, "Parking")
            self.assertEqual(len(graph["cable_edges"]), 1)
            edge = graph["cable_edges"][0]
            hops = edge.get("conduit_hops") or []
            self.assertEqual(
                [h["conduit"] for h in hops],
                ["Conducto_AB", "Conducto_BC"],
            )
            self.assertEqual(edge.get("conduit_from"), "A")
            self.assertEqual(edge.get("conduit_to"), "C")
            self.assertEqual(edge.get("from_opening"), "S1")
            self.assertEqual(edge.get("to_opening"), "N1")
            # Multi-hop: no single conduit id
            self.assertIsNone(edge.get("conduit"))


class TestServeApi(unittest.TestCase):
    def test_create_app_endpoints(self) -> None:
        try:
            from fastapi.testclient import TestClient
        except (ImportError, RuntimeError):
            self.skipTest("fastapi/httpx not installed")

        from housewire.ui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build_parking_wiring_site(root)
            parking_yaml = root / HOUSEWIRE_YAML

            client = TestClient(create_app(root))
            locations = client.get("/api/locations").json()
            ids = {row["id"] for row in locations["locations"]}
            self.assertIn("Parking", ids)

            graph = client.get(
                "/api/physical", params={"location": "Parking"}
            ).json()
            self.assertEqual(len(graph["nodes"]), 2)
            self.assertEqual(graph["location"]["id"], "Parking")
            self.assertIn("Caja_4/Regleta", {e["id"] for e in graph["elements"]})

            outline = client.get("/api/outline").json()
            oids = {n["id"] for n in outline["nodes"]}
            self.assertIn("Parking", oids)
            self.assertIn("Parking/Caja_4", oids)
            self.assertIn("Parking/Caja_4/Regleta", oids)

            house = client.get(
                "/api/physical", params={"location": ".", "depth": 2}
            ).json()
            self.assertEqual(house["depth"], 2)
            ids = {n["id"] for n in house["nodes"]}
            self.assertIn("Parking", ids)
            self.assertIn("Parking/Caja_4", ids)

            laid = client.post(
                "/api/physical/auto-layout",
                json={"location_id": "Parking", "force": True},
            ).json()
            self.assertEqual(len(laid["updated"]), 2)

            el_laid = client.post(
                "/api/electrical/auto-layout",
                json={"location_id": "Parking", "force": True},
            ).json()
            self.assertIn("Caja_4/Regleta", el_laid["updated"])

            patched = client.patch(
                "/api/physical/positions",
                json={
                    "location_id": "Parking",
                    "positions": {"Caja_4": {"x": 11, "y": 22}},
                },
            ).json()
            self.assertEqual(patched["updated"], ["Caja_4"])

            el_patched = client.patch(
                "/api/electrical/positions",
                json={
                    "location_id": "Parking",
                    "positions": {"Caja_4/Regleta": {"x": 5, "y": 6}},
                },
            ).json()
            self.assertEqual(el_patched["updated"], ["Caja_4/Regleta"])

            page = client.patch(
                "/api/physical/page",
                json={"location_id": "Parking", "representation": "tube"},
            ).json()
            self.assertEqual(page["page"]["representation"], "tube")

            status = client.get("/api/status").json()
            self.assertTrue(status["dirty"])

            saved = client.post("/api/save").json()
            self.assertTrue(saved["saved"])

            # Move then restore saved coords → dirty clears (undo-to-saved).
            client.patch(
                "/api/physical/positions",
                json={
                    "location_id": "Parking",
                    "positions": {"Caja_4": {"x": 99, "y": 88}},
                },
            )
            self.assertTrue(client.get("/api/status").json()["dirty"])
            client.patch(
                "/api/physical/positions",
                json={
                    "location_id": "Parking",
                    "positions": {"Caja_4": {"x": 11, "y": 22}},
                },
            )
            self.assertEqual(client.get("/api/status").json()["dirty"], [])

            caja = get_place_node(
                abm.load_editable(parking_yaml, root), ("Parking", "Caja_4")
            )
            self.assertEqual(caja["view"]["physical"]["x"], 11.0)
            self.assertEqual(
                caja["elements"]["Regleta"]["view"]["electrical"]["x"], 5.0
            )
            loc_doc = abm.load_editable(parking_yaml, root)
            parking_place = get_place_node(loc_doc, ("Parking",))
            self.assertEqual(
                parking_place["views"]["physical"]["representation"], "tube"
            )

    def test_place_detail_and_socket_recipe(self) -> None:
        try:
            from fastapi.testclient import TestClient
        except (ImportError, RuntimeError):
            self.skipTest("fastapi/httpx not installed")

        from housewire.ui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = init_site(root, type_id="House", label="Site")
            add_place(doc, "Parking", type_id="Floor", label="Parking")
            add_place(
                doc, "Caja_4", under=("Parking",), type_id="JunctionBox", label="Caja 4"
            )
            caja = get_place_node(doc, ("Parking", "Caja_4"))
            caja["openings"] = ["N1", "W2"]
            abm.add_element(caja, "Regleta", type_id="TerminalStrip", subtype="3")
            set_physical_position(caja, 100, 80)
            save_site(root, doc)

            client = TestClient(create_app(root))
            detail = client.get(
                "/api/place",
                params={"location": "Parking", "id": "Caja_4"},
            ).json()
            self.assertEqual(detail["type"], "JunctionBox")
            self.assertIn("N1", detail["openings"])
            self.assertTrue(
                any(e["id"] == "Regleta" for e in detail["elements"])
            )
            self.assertEqual(detail["conduits"], [])
            self.assertEqual(detail["cables"], [])

            cooked = client.post(
                "/api/recipes/socket",
                json={
                    "location_id": "Parking",
                    "name": "Enchufe_9",
                    "from": "Caja_4.N1",
                    "strip": "Regleta",
                },
            )
            self.assertEqual(cooked.status_code, 200, cooked.text)
            body = cooked.json()
            self.assertEqual(body["result"]["place_id"], "Enchufe_9")
            ids = {n["id"] for n in body["graph"]["nodes"]}
            self.assertIn("Enchufe_9", ids)
            self.assertTrue(
                any(e["to"] == "Enchufe_9" for e in body["graph"]["edges"])
            )

            caja_after = client.get(
                "/api/place",
                params={"location": "Parking", "id": "Caja_4"},
            ).json()
            self.assertTrue(caja_after["conduits"])
            self.assertTrue(
                any(
                    "Enchufe_9" in str(c.get("to") or "")
                    or "Enchufe_9" in str(c.get("from") or "")
                    for c in caja_after["conduits"]
                )
            )
            self.assertTrue(caja_after["cables"])
            enchufe = client.get(
                "/api/place",
                params={"location": "Parking", "id": "Enchufe_9"},
            ).json()
            self.assertTrue(enchufe["conduits"])
            self.assertTrue(enchufe["cables"])


if __name__ == "__main__":
    unittest.main()
