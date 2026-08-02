"""Tests for view.physical layout helpers and UI physical graph."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fixtures import add_place, init_site, save_site
from housewire.site import abm
from housewire.site.io import HOUSEWIRE_YAML
from housewire.site.tree import get_place_node
from housewire.site.view_layout import (
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
    parking["cables"]["Linea_1_1"]["from"] = "Caja_4/Regleta.N1"
    parking["cables"]["Linea_1_1"]["to"] = "Enchufe_1/Socket.N1"
    parking["cables"]["Linea_1_2"]["from"] = "Caja_4/Regleta.N3"
    parking["cables"]["Linea_1_2"]["to"] = "Enchufe_1/Socket.N3"
    save_site(root, doc)


class TestViewLayout(unittest.TestCase):
    def test_set_get_physical_position(self) -> None:
        place: dict = {"schema": "house/v2", "type": "JunctionBox"}
        self.assertIsNone(get_physical_position(place))
        set_physical_position(place, 10, 20, rotation=90)
        self.assertEqual(get_physical_position(place), (10.0, 20.0))
        self.assertEqual(place["view"]["physical"]["rotation"], 90)

    def test_physical_position_rejects_negatives(self) -> None:
        place: dict = {"schema": "house/v2", "type": "JunctionBox"}
        with self.assertRaises(ValueError):
            set_physical_position(place, -1, 10)
        with self.assertRaises(ValueError):
            set_physical_position(place, 10, -0.5)
        place["view"] = {"physical": {"x": -5, "y": 20}}
        self.assertIsNone(get_physical_position(place))

    def test_page_defaults_and_set(self) -> None:
        place: dict = {"schema": "house/v2", "type": "Room"}
        page = get_physical_page(place)
        self.assertEqual(page["representation"], "tube")
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
            # Sheath keeps per-strand pins (not only the first conductor's).
            self.assertEqual(
                graph["cable_edges"][0].get("from_pins"), ["N1", "N3"]
            )
            self.assertEqual(
                graph["cable_edges"][0].get("to_pins"), ["N1", "N3"]
            )
            self.assertEqual(graph["cable_edges"][0].get("colors"), ["BN", "BU"])
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
            parking["cables"]["Linea_AC"]["from"] = "A/Regleta.N1"
            parking["cables"]["Linea_AC"]["to"] = "C/Regleta.N1"
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
            root_detail = client.get(
                "/api/place",
                params={"location": ".", "id": "."},
            )
            self.assertEqual(root_detail.status_code, 200, root_detail.text)
            self.assertEqual(root_detail.json()["type"], "House")
            self.assertEqual(root_detail.json()["id"], ".")

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

    def test_place_properties_patch(self) -> None:
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
            abm.add_element(caja, "Regleta", type_id="TerminalStrip", subtype="3")
            save_site(root, doc)

            client = TestClient(create_app(root))
            edited = client.patch(
                "/api/place/properties",
                json={
                    "location_id": "Parking",
                    "id": "Caja_4",
                    "fields": {"label": "Caja cuatro", "notes": "UI edit"},
                    "depth": 1,
                },
            )
            self.assertEqual(edited.status_code, 200, edited.text)
            body = edited.json()
            self.assertEqual(body["detail"]["label"], "Caja cuatro")
            self.assertEqual(body["detail"]["notes"], "UI edit")
            colon_notes = client.patch(
                "/api/place/properties",
                json={
                    "location_id": "Parking",
                    "id": "Caja_4",
                    "fields": {
                        "notes": "Regleta_1: 5 bornes; Regleta_2: N luces",
                    },
                    "depth": 1,
                },
            )
            self.assertEqual(colon_notes.status_code, 200, colon_notes.text)
            self.assertEqual(
                colon_notes.json()["detail"]["notes"],
                "Regleta_1: 5 bornes; Regleta_2: N luces",
            )
            elem_edit = client.patch(
                "/api/place/properties",
                json={
                    "location_id": "Parking",
                    "id": "Caja_4",
                    "element": "Regleta",
                    "fields": {"label": "Strip A"},
                    "depth": 1,
                },
            )
            self.assertEqual(elem_edit.status_code, 200, elem_edit.text)
            reg = next(
                e
                for e in elem_edit.json()["detail"]["elements"]
                if e["id"] == "Regleta"
            )
            self.assertEqual(reg["label"], "Strip A")
            dirty = client.get("/api/workspace").json()
            self.assertTrue(dirty.get("dirty"))

    def test_cable_edge_via_indices(self) -> None:
        from housewire.ui.physical_graph import _via_wire_indices

        self.assertEqual(_via_wire_indices("Linea_x.1"), [1])
        self.assertEqual(_via_wire_indices("Linea_x.[1, 2, 3]"), [1, 2, 3])
        self.assertEqual(_via_wire_indices("Linea_x"), [])

    def test_unified_edit_undo_redo_reset(self) -> None:
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
            save_site(root, doc)

            client = TestClient(create_app(root))
            # Seed graph / session buffer.
            client.get("/api/physical?location=Parking&depth=1")

            props = client.patch(
                "/api/place/properties",
                json={
                    "location_id": "Parking",
                    "id": "Caja_4",
                    "fields": {"label": "Moved label"},
                    "depth": 1,
                },
            )
            self.assertEqual(props.status_code, 200, props.text)
            self.assertTrue(props.json().get("can_undo"))
            self.assertEqual(props.json()["detail"]["label"], "Moved label")

            pos = client.patch(
                "/api/physical/positions",
                json={
                    "location_id": "Parking",
                    "positions": {"Caja_4": {"x": 120, "y": 80}},
                },
            )
            self.assertEqual(pos.status_code, 200, pos.text)
            self.assertTrue(pos.json().get("can_undo"))

            undo_layout = client.post(
                "/api/edit/undo",
                json={"location_id": "Parking", "depth": 1},
            )
            self.assertEqual(undo_layout.status_code, 200, undo_layout.text)
            self.assertTrue(undo_layout.json().get("changed"))
            # Position undone; label edit still present.
            graph = undo_layout.json()["graph"]
            caja = next(n for n in graph["nodes"] if n["id"] == "Caja_4")
            self.assertNotEqual((caja.get("x"), caja.get("y")), (120, 80))

            detail = client.get(
                "/api/place?location=Parking&id=Caja_4"
            ).json()
            self.assertEqual(detail["label"], "Moved label")

            undo_props = client.post(
                "/api/edit/undo",
                json={"location_id": "Parking", "depth": 1},
            )
            self.assertEqual(undo_props.status_code, 200, undo_props.text)
            self.assertTrue(undo_props.json().get("changed"))
            detail = client.get(
                "/api/place?location=Parking&id=Caja_4"
            ).json()
            self.assertEqual(detail["label"], "Caja 4")

            redo = client.post(
                "/api/edit/redo",
                json={"location_id": "Parking", "depth": 1},
            )
            self.assertEqual(redo.status_code, 200, redo.text)
            self.assertTrue(redo.json().get("changed"))
            detail = client.get(
                "/api/place?location=Parking&id=Caja_4"
            ).json()
            self.assertEqual(detail["label"], "Moved label")

            reset = client.post(
                "/api/edit/reset",
                json={"location_id": "Parking", "depth": 1},
            )
            self.assertEqual(reset.status_code, 200, reset.text)
            self.assertTrue(reset.json().get("changed"))
            detail = client.get(
                "/api/place?location=Parking&id=Caja_4"
            ).json()
            self.assertEqual(detail["label"], "Caja 4")
            self.assertFalse(reset.json().get("can_undo"))
            self.assertFalse(reset.json().get("can_reset"))
            # Reset keeps the redo trail from the save point.
            self.assertTrue(reset.json().get("can_redo"))
            redo_after_reset = client.post(
                "/api/edit/redo",
                json={"location_id": "Parking", "depth": 1},
            )
            self.assertEqual(redo_after_reset.status_code, 200, redo_after_reset.text)
            self.assertTrue(redo_after_reset.json().get("changed"))
            detail = client.get(
                "/api/place?location=Parking&id=Caja_4"
            ).json()
            self.assertEqual(detail["label"], "Moved label")
            self.assertTrue(redo_after_reset.json().get("can_reset"))


if __name__ == "__main__":
    unittest.main()
