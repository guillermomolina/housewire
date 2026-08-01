"""Tests for view.physical layout helpers and UI physical graph."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from housewire.project import abm
from housewire.project.io import create_location_index
from housewire.project.view_layout import (
    get_physical_page,
    get_physical_position,
    set_physical_page,
    set_physical_position,
)
from housewire.ui.physical_graph import (
    apply_auto_layout,
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
            abm.persist(caja_doc, caja_yaml, root)

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
            abm.persist(doc, parking_yaml, root)

            locations = list_canvas_locations(root)
            ids = {row["id"] for row in locations}
            self.assertIn("Parking", ids)
            self.assertIn(".", ids)  # House root also has children

            graph = build_physical_graph(root, "Parking")
            self.assertEqual(graph["location"]["id"], "Parking")
            self.assertEqual(len(graph["nodes"]), 2)
            self.assertEqual(len(graph["edges"]), 1)
            self.assertEqual(graph["edges"][0]["from"], "Caja_4")
            self.assertEqual(graph["edges"][0]["to"], "Enchufe_1")
            caja_node = next(n for n in graph["nodes"] if n["id"] == "Caja_4")
            faces = {o["id"]: o["face"] for o in caja_node["openings"]}
            self.assertEqual(faces.get("B1-1"), "B")
            self.assertIsNone(caja_node["x"])

            session_docs: dict[Path, dict] = {}
            updated = apply_auto_layout(
                root, "Parking", session_docs=session_docs, force=False
            )
            self.assertEqual(sorted(updated), ["Caja_4", "Enchufe_1"])
            graph2 = build_physical_graph(
                root, "Parking", session_docs=session_docs
            )
            for node in graph2["nodes"]:
                self.assertIsNotNone(node["x"])
                self.assertIsNotNone(node["y"])

            apply_positions(
                root,
                "Parking",
                {"Caja_4": {"x": 42, "y": 99}},
                session_docs=session_docs,
            )
            graph3 = build_physical_graph(
                root, "Parking", session_docs=session_docs
            )
            caja = next(n for n in graph3["nodes"] if n["id"] == "Caja_4")
            self.assertEqual(caja["x"], 42.0)
            self.assertEqual(caja["y"], 99.0)


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

            laid = client.post(
                "/api/physical/auto-layout",
                json={"location_id": "Parking", "force": True},
            ).json()
            self.assertEqual(len(laid["updated"]), 2)

            patched = client.patch(
                "/api/physical/positions",
                json={
                    "location_id": "Parking",
                    "positions": {"Caja_4": {"x": 11, "y": 22}},
                },
            ).json()
            self.assertEqual(patched["updated"], ["Caja_4"])

            page = client.patch(
                "/api/physical/page",
                json={"location_id": "Parking", "representation": "tube"},
            ).json()
            self.assertEqual(page["page"]["representation"], "tube")

            status = client.get("/api/status").json()
            self.assertTrue(status["dirty"])

            saved = client.post("/api/save").json()
            self.assertTrue(saved["saved"])

            caja = abm.load_editable(
                parking / "Caja_4" / "housewire.yaml", root
            )
            self.assertEqual(caja["view"]["physical"]["x"], 11.0)
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
