"""Tests for view.physical layout helpers and UI physical graph."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from housewire.project import abm
from housewire.project.io import create_location_index
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
)


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
            create_location_index(root, type_id="House", label="Site")
            parking = root / "Parking"
            create_location_index(parking, type_id="Floor", label="Parking")
            create_location_index(
                parking / "Caja_4",
                type_id="JunctionBox",
                label="Caja 4",
            )
            create_location_index(
                parking / "Enchufe_1",
                type_id="DeviceBox",
                label="Enchufe 1",
            )
            caja_yaml = parking / "Caja_4" / "housewire.yaml"
            caja_doc = abm.load_editable(caja_yaml, root)
            caja_doc["openings"] = ["W2", "B1-1"]
            abm.add_element(caja_doc, "Regleta", type_id="TerminalStrip")
            abm.persist(caja_doc, caja_yaml, root)

            enchufe_yaml = parking / "Enchufe_1" / "housewire.yaml"
            enchufe_doc = abm.load_editable(enchufe_yaml, root)
            abm.add_element(enchufe_doc, "Socket", type_id="Socket")
            abm.persist(enchufe_doc, enchufe_yaml, root)

            parking_yaml = parking / "housewire.yaml"
            doc = abm.load_editable(parking_yaml, root)
            abm.add_cable(doc, "Linea_1", section="1.5", colors=["BN", "BU"])
            abm.add_conduit(
                doc,
                "Conducto_1",
                contains=["Linea_1"],
                from_ref="Caja_4.W2",
                to_ref="Enchufe_1.N1",
            )
            abm.add_connection(
                doc,
                from_ref="Caja_4/Regleta.1",
                via_ref="Linea_1.1",
                to_ref="Enchufe_1/Socket.L",
            )
            abm.persist(doc, parking_yaml, root)

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


class TestServeApi(unittest.TestCase):
    def test_create_app_endpoints(self) -> None:
        try:
            from fastapi.testclient import TestClient
        except (ImportError, RuntimeError):
            self.skipTest("fastapi/httpx not installed")

        from housewire.ui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_location_index(root, type_id="House", label="Site")
            parking = root / "Parking"
            create_location_index(parking, type_id="Floor", label="Parking")
            create_location_index(
                parking / "Caja_4", type_id="JunctionBox", label="Caja 4"
            )
            create_location_index(
                parking / "Enchufe_1", type_id="DeviceBox", label="Enchufe 1"
            )
            caja_yaml = parking / "Caja_4" / "housewire.yaml"
            caja_doc = abm.load_editable(caja_yaml, root)
            abm.add_element(caja_doc, "Regleta", type_id="TerminalStrip")
            abm.persist(caja_doc, caja_yaml, root)
            parking_yaml = parking / "housewire.yaml"
            doc = abm.load_editable(parking_yaml, root)
            abm.add_cable(doc, "Linea_1", section="1.5", colors=["BN"])
            abm.add_conduit(
                doc,
                "Conducto_1",
                contains=["Linea_1"],
                from_ref="Caja_4.W2",
                to_ref="Enchufe_1.N1",
            )
            abm.persist(doc, parking_yaml, root)

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

            caja = abm.load_editable(
                parking / "Caja_4" / "housewire.yaml", root
            )
            self.assertEqual(caja["view"]["physical"]["x"], 11.0)
            self.assertEqual(
                caja["elements"]["Regleta"]["view"]["electrical"]["x"], 5.0
            )
            loc_doc = abm.load_editable(parking_yaml, root)
            self.assertEqual(loc_doc["views"]["physical"]["representation"], "tube")

    def test_place_detail_and_socket_recipe(self) -> None:
        try:
            from fastapi.testclient import TestClient
        except (ImportError, RuntimeError):
            self.skipTest("fastapi/httpx not installed")

        from housewire.ui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_location_index(root, type_id="House", label="Site")
            parking = root / "Parking"
            create_location_index(parking, type_id="Floor", label="Parking")
            create_location_index(
                parking / "Caja_4", type_id="JunctionBox", label="Caja 4"
            )
            caja_yaml = parking / "Caja_4" / "housewire.yaml"
            caja = abm.load_editable(caja_yaml, root)
            caja["openings"] = ["N1", "W2"]
            abm.add_element(caja, "Regleta", type_id="TerminalStrip", subtype="3")
            abm.persist(caja, caja_yaml, root)
            set_physical_position(caja, 100, 80)
            abm.persist(caja, caja_yaml, root)

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


if __name__ == "__main__":
    unittest.main()
