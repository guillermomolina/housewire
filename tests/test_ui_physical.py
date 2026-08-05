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
    get_electrical_flips,
    get_electrical_position,
    get_electrical_size,
    get_physical_flips,
    get_physical_page,
    get_physical_position,
    get_physical_size,
    set_electrical_flips,
    set_electrical_position,
    set_electrical_size,
    set_physical_flips,
    set_physical_page,
    set_physical_position,
    set_physical_size,
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

    def test_normalize_view_xy_siblings(self) -> None:
        from housewire.site.view_layout import normalize_view_xy_siblings

        a: dict = {"type": "JunctionBox"}
        b: dict = {"type": "JunctionBox"}
        set_physical_position(a, -20, 10, allow_negative=True)
        set_physical_position(b, 40, -5, allow_negative=True)
        dx, dy = normalize_view_xy_siblings([a, b], layer="physical")
        self.assertEqual((dx, dy), (20.0, 5.0))
        self.assertEqual(get_physical_position(a), (0.0, 15.0))
        self.assertEqual(get_physical_position(b), (60.0, 0.0))

    def test_normalize_noop_when_non_negative(self) -> None:
        from housewire.site.view_layout import normalize_view_xy_siblings

        a: dict = {"type": "JunctionBox"}
        set_physical_position(a, 10, 20)
        dx, dy = normalize_view_xy_siblings([a], layer="physical")
        self.assertEqual((dx, dy), (0.0, 0.0))
        self.assertEqual(get_physical_position(a), (10.0, 20.0))

    def test_apply_positions_normalizes_negatives(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = init_site(root, type_id="House", label="Site")
            add_place(doc, "Room", type_id="Room")
            add_place(doc, "A", under=("Room",), type_id="JunctionBox")
            add_place(doc, "B", under=("Room",), type_id="JunctionBox")
            room = get_place_node(doc, ("Room",))
            set_physical_position(room, 50, 60)
            set_physical_size(room, 400, 300)
            set_physical_position(get_place_node(doc, ("Room", "A")), 0, 40)
            set_physical_position(get_place_node(doc, ("Room", "B")), 100, 40)
            save_site(root, doc)
            session_docs: dict[Path, dict] = {}
            apply_positions(
                root,
                "Room",
                {"A": {"x": -25, "y": 40}},
                session_docs=session_docs,
            )
            yaml = root / HOUSEWIRE_YAML
            a = get_place_node(session_docs[yaml], ("Room", "A"))
            b = get_place_node(session_docs[yaml], ("Room", "B"))
            room2 = get_place_node(session_docs[yaml], ("Room",))
            self.assertEqual(get_physical_position(a), (0.0, 40.0))
            self.assertEqual(get_physical_position(b), (125.0, 40.0))
            # Room wall moves west with the content (x-=25, w+=25).
            self.assertEqual(get_physical_position(room2), (25.0, 60.0))
            self.assertEqual(get_physical_size(room2), (425.0, 300.0))

    def test_page_defaults_and_set(self) -> None:
        place: dict = {"schema": "house/v2", "type": "Room"}
        page = get_physical_page(place)
        self.assertEqual(page["representation"], "Tube")
        self.assertEqual(page["width"], 2000.0)
        set_physical_page(place, representation="Tube", width=1200)
        page2 = get_physical_page(place)
        self.assertEqual(page2["representation"], "Tube")
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

    def test_physical_and_electrical_sizes(self) -> None:
        place: dict = {"schema": "house/v2", "type": "Room"}
        self.assertIsNone(get_physical_size(place))
        set_physical_position(place, 10, 20)
        set_physical_size(place, 200, 120)
        self.assertEqual(get_physical_size(place), (200.0, 120.0))
        self.assertEqual(place["view"]["physical"]["x"], 10.0)
        with self.assertRaises(ValueError):
            set_physical_size(place, 0, 10)

        element: dict = {"type": "Socket"}
        set_electrical_position(element, 4, 8)
        set_electrical_size(element, 90, 48)
        self.assertEqual(get_electrical_size(element), (90.0, 48.0))
        with self.assertRaises(ValueError):
            set_electrical_size(element, -1, 10)

    def test_physical_and_electrical_flips(self) -> None:
        place: dict = {"schema": "house/v2", "type": "Room"}
        self.assertEqual(get_physical_flips(place), (False, False))
        set_physical_flips(place, flip_ns=True, flip_we=True)
        self.assertEqual(get_physical_flips(place), (True, True))
        self.assertEqual(
            place["view"]["physical"],
            {"flip_ns": True, "flip_we": True},
        )
        set_physical_flips(place, flip_ns=False, flip_we=False)
        self.assertNotIn("view", place)

        set_physical_position(place, 10, 20)
        set_physical_flips(place, flip_we=True)
        self.assertEqual(place["view"]["physical"]["x"], 10.0)
        self.assertTrue(place["view"]["physical"]["flip_we"])
        self.assertNotIn("flip_ns", place["view"]["physical"])

        element: dict = {"type": "Socket"}
        self.assertEqual(get_electrical_flips(element), (False, False))
        set_electrical_flips(element, flip_ns=True)
        self.assertEqual(get_electrical_flips(element), (True, False))
        set_electrical_flips(element, flip_ns=False)
        self.assertNotIn("view", element)


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
                {"Caja_4": {"x": 42, "y": 99, "w": 220, "h": 180}},
                session_docs=session_docs,
            )
            apply_electrical_positions(
                root,
                "Parking",
                {"Caja_4/Regleta": {"x": 12, "y": 34, "w": 96, "h": 52}},
                session_docs=session_docs,
            )
            graph3 = build_physical_graph(
                root, "Parking", session_docs=session_docs
            )
            caja = next(n for n in graph3["nodes"] if n["id"] == "Caja_4")
            self.assertEqual(caja["x"], 42.0)
            self.assertEqual(caja["y"], 99.0)
            # Stored size wins when larger than auto content bounds.
            self.assertEqual(caja["w"], 220.0)
            self.assertEqual(caja["h"], 180.0)
            self.assertTrue(caja["size_locked"])
            regleta = next(
                e for e in graph3["elements"] if e["id"] == "Caja_4/Regleta"
            )
            self.assertEqual(regleta["x"], 12.0)
            self.assertEqual(regleta["y"], 34.0)
            self.assertEqual(regleta["w"], 96.0)
            self.assertEqual(regleta["h"], 52.0)
            self.assertTrue(regleta["size_locked"])

            outline = list_site_outline(root)
            kinds = {(row["kind"], row["id"]) for row in outline}
            self.assertIn(("place", "Parking"), kinds)
            self.assertIn(("place", "Parking/Caja_4"), kinds)
            self.assertIn(("element", "Parking/Caja_4/Regleta"), kinds)
            self.assertIn(("element", "Parking/Enchufe_1/Socket"), kinds)
            socket = next(
                r for r in outline if r["id"] == "Parking/Enchufe_1/Socket"
            )
            self.assertEqual(socket.get("icon"), "plug")

    def test_empty_house_lists_root_canvas(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            from housewire.site.io import create_site_document

            create_site_document(root, type_id="House", label="Blank")
            locations = list_canvas_locations(root)
            self.assertEqual(len(locations), 1)
            self.assertEqual(locations[0]["id"], ".")
            self.assertTrue(locations[0]["selectable"])
            graph = build_physical_graph(root, ".", depth=1)
            self.assertEqual(graph["nodes"], [])
            self.assertEqual(graph["elements"], [])

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

    def test_opposite_direction_strands_share_cable_edge(self) -> None:
        """Sheath conductors with flipped from/to still paint as one jacket."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = init_site(root, type_id="House", label="Site")
            add_place(doc, "Room", type_id="Room", label="Room")
            add_place(
                doc,
                "Caja",
                under=("Room",),
                type_id="JunctionBox",
                label="Caja",
            )
            add_place(
                doc,
                "Caja2",
                under=("Room",),
                type_id="JunctionBox",
                label="Caja2",
            )
            for parts in (("Room", "Caja"), ("Room", "Caja2")):
                box = get_place_node(doc, parts)
                box["openings"] = ["E1", "W1"]
                abm.add_element(box, "Regleta", type_id="TerminalStrip")
            room = get_place_node(doc, ("Room",))
            abm.add_cable(room, "Linea", section="1.5", colors=["BN", "BK"])
            abm.add_conduit(
                room,
                "Conducto",
                contains=["Linea"],
                from_ref="Caja.E1",
                to_ref="Caja2.W1",
            )
            # Outbound brown, return black (opposite endpoints).
            room["cables"]["Linea_1"]["from"] = "Caja/Regleta.N1"
            room["cables"]["Linea_1"]["to"] = "Caja2/Regleta.N1"
            room["cables"]["Linea_2"]["from"] = "Caja2/Regleta.N2"
            room["cables"]["Linea_2"]["to"] = "Caja/Regleta.N2"
            save_site(root, doc)

            graph = build_physical_graph(root, "Room")
            self.assertEqual(len(graph["cable_edges"]), 1)
            edge = graph["cable_edges"][0]
            self.assertEqual(edge.get("colors"), ["BN", "BK"])
            self.assertEqual(edge.get("from_pins"), ["N1", "N2"])
            self.assertEqual(edge.get("to_pins"), ["N1", "N2"])
            self.assertEqual(edge.get("from"), "Caja/Regleta")
            self.assertEqual(edge.get("to"), "Caja2/Regleta")

    def test_sheath_jacket_color_on_cable_edge(self) -> None:
        """Cable sheath ``color:`` becomes ``jacket_color`` for the UI jacket."""
        root = Path(__file__).resolve().parents[1] / "sites" / "Tests"
        if not root.is_dir() or not any(root.glob("*.yaml")):
            self.skipTest("sites/Tests fixture not present")
        graph = build_physical_graph(root, "Habitacion")
        edges = {
            e["id"]: e for e in graph.get("cable_edges") or [] if e.get("id")
        }
        lamp = edges.get("Linea_lampara")
        self.assertIsNotNone(lamp)
        self.assertEqual(lamp.get("jacket_color"), "WH")
        self.assertEqual(lamp.get("colors"), ["BK", "BU"])
        # Bare PE conductor must not get a fake jacket (would paint as a peer
        # "white/green" band on the conduit centerline).
        pe = edges.get("Linea_lampara_T")
        self.assertIsNotNone(pe)
        self.assertIsNone(pe.get("jacket_color"))
        self.assertEqual(pe.get("colors"), ["GNYE"])

    def test_conduit_nesting_lamp_bundle(self) -> None:
        """BK conduit holds WH(BK+BU) sheath + bare GNYE — graph nesting."""
        root = Path(__file__).resolve().parents[1] / "sites" / "Tests"
        if not root.is_dir() or not any(root.glob("*.yaml")):
            self.skipTest("sites/Tests fixture not present")
        graph = build_physical_graph(root, "Habitacion")
        by_id = {e["id"]: e for e in graph.get("edges") or []}
        tube = by_id.get("Conducto_lampara")
        self.assertIsNotNone(tube)
        self.assertEqual(tube.get("color"), "BK")
        contains = set(tube.get("contains") or [])
        self.assertIn("Linea_lampara", contains)
        self.assertIn("Linea_lampara_T", contains)

    def test_conduit_color_on_graph_edge(self) -> None:
        root = Path(__file__).resolve().parents[1] / "sites" / "Tests"
        if not root.is_dir() or not any(root.glob("*.yaml")):
            self.skipTest("sites/Tests fixture not present")
        graph = build_physical_graph(root, "Habitacion")
        by_id = {e["id"]: e for e in graph.get("edges") or []}
        self.assertEqual(by_id["Conducto_lampara"].get("color"), "BK")
        self.assertEqual(by_id["Conducto_interruptor"].get("color"), "BK")


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

            about = client.get("/api/about").json()
            self.assertEqual(about["title"], "HouseWire")
            self.assertEqual(about["author"], "Guillermo Adrián Molina")
            self.assertEqual(about["license"], "SSPL-1.0")
            self.assertIn("github.com/guillermomolina/housewire", about["repository"])
            self.assertTrue(about["version"])
            self.assertTrue(about["description"])
            self.assertIn("YAML", about["description"])

            about_es = client.get("/api/about", params={"lang": "es"}).json()
            self.assertEqual(about_es["lang"], "es")
            self.assertIn("lienzo", about_es["description"])

            inserted = client.post(
                "/api/insert/catalog-item",
                json={
                    "location_id": "Parking",
                    "place_id": "Caja_4",
                    "type_id": "LightPoint",
                    "name": "Punto_1",
                    "depth": 2,
                },
            ).json()
            self.assertEqual(inserted["result"]["kind"], "place")
            self.assertEqual(inserted["result"]["id"], "Caja_4/Punto_1")
            inserted_ids = {n["id"] for n in inserted["graph"]["nodes"]}
            self.assertIn("Caja_4/Punto_1", inserted_ids)

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
                json={"location_id": "Parking", "representation": "Tube"},
            ).json()
            self.assertEqual(page["page"]["representation"], "Tube")

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
                parking_place["views"]["physical"]["representation"], "Tube"
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
            abm.add_element(caja, "Regleta", type_id="TerminalStrip")
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

    def test_place_detail_conduits_include_nested_endpoints(self) -> None:
        """Parent place lists ancestor conduits that attach to a child place."""
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
                doc, "Escalera", under=(), type_id="Stair", label="Escalera"
            )
            add_place(
                doc,
                "Caja_4",
                under=("Parking",),
                type_id="JunctionBox",
                label="Caja 4",
            )
            add_place(
                doc,
                "Interruptor_2",
                under=("Escalera",),
                type_id="DeviceBox",
                label="Int 2",
            )
            caja = get_place_node(doc, ("Parking", "Caja_4"))
            caja["openings"] = ["W1"]
            inter = get_place_node(doc, ("Escalera", "Interruptor_2"))
            inter["openings"] = ["N1"]
            house = get_place_node(doc, ())
            abm.add_cable(house, "Linea_escalera", section="1.5", colors=["BN"])
            abm.add_conduit(
                house,
                "Conducto_CD4_a_Escalera",
                contains=["Linea_escalera"],
                from_ref="Parking/Caja_4.W1",
                to_ref="Escalera/Interruptor_2.N1",
            )
            save_site(root, doc)

            client = TestClient(create_app(root))
            caja_detail = client.get(
                "/api/place",
                params={"location": ".", "id": "Parking/Caja_4"},
            ).json()
            esc_detail = client.get(
                "/api/place",
                params={"location": ".", "id": "Escalera"},
            ).json()
            inter_detail = client.get(
                "/api/place",
                params={"location": ".", "id": "Escalera/Interruptor_2"},
            ).json()
            for detail in (caja_detail, esc_detail, inter_detail):
                ids = {c["id"] for c in detail.get("conduits") or []}
                self.assertIn(
                    "Conducto_CD4_a_Escalera",
                    ids,
                    msg=f"missing on {detail.get('id')}: {ids}",
                )

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
            abm.add_element(caja, "Regleta", type_id="TerminalStrip")
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
            flips = client.patch(
                "/api/place/properties",
                json={
                    "location_id": "Parking",
                    "id": "Caja_4",
                    "fields": {"flip_ns": True, "flip_we": False},
                    "depth": 1,
                },
            )
            self.assertEqual(flips.status_code, 200, flips.text)
            self.assertTrue(flips.json()["detail"]["flip_ns"])
            self.assertFalse(flips.json()["detail"]["flip_we"])
            node = next(
                n for n in flips.json()["graph"]["nodes"] if n["id"] == "Caja_4"
            )
            self.assertTrue(node["flip_ns"])
            self.assertFalse(node["flip_we"])
            elem_flips = client.patch(
                "/api/place/properties",
                json={
                    "location_id": "Parking",
                    "id": "Caja_4",
                    "element": "Regleta",
                    "fields": {"flip_we": True},
                    "depth": 1,
                },
            )
            self.assertEqual(elem_flips.status_code, 200, elem_flips.text)
            graphed = next(
                e
                for e in elem_flips.json()["graph"]["elements"]
                if e["leaf_id"] == "Regleta" or e["id"].endswith("/Regleta")
            )
            self.assertTrue(graphed["flip_we"])
            canvas_flip = client.patch(
                "/api/place/properties",
                json={
                    "location_id": "Parking",
                    "id": ".",
                    "fields": {"flip_ns": True},
                    "depth": 1,
                },
            )
            self.assertEqual(canvas_flip.status_code, 200, canvas_flip.text)
            self.assertTrue(canvas_flip.json()["detail"]["flip_ns"])
            self.assertTrue(canvas_flip.json()["graph"]["location"]["flip_ns"])
            self.assertTrue(canvas_flip.json().get("can_undo"))
            dirty = client.get("/api/workspace").json()
            self.assertTrue(dirty.get("dirty"))

    def test_flip_save_reload_and_undo(self) -> None:
        """Flips must persist on Save and reverse with Undo before Save."""
        try:
            from fastapi.testclient import TestClient
        except (ImportError, RuntimeError):
            self.skipTest("fastapi/httpx not installed")

        from housewire.site.io import load_yaml
        from housewire.site.view_layout import get_physical_flips
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
            client.get("/api/physical?location=Parking&depth=1")

            flipped = client.patch(
                "/api/place/properties",
                json={
                    "location_id": "Parking",
                    "id": "Caja_4",
                    "fields": {"flip_ns": True, "flip_we": False},
                    "depth": 1,
                },
            )
            self.assertEqual(flipped.status_code, 200, flipped.text)
            self.assertTrue(flipped.json().get("can_undo"))
            self.assertTrue(flipped.json().get("dirty"))

            undone = client.post(
                "/api/edit/undo",
                json={"location_id": "Parking", "depth": 1},
            )
            self.assertEqual(undone.status_code, 200, undone.text)
            self.assertTrue(undone.json().get("changed"))
            node = next(
                n for n in undone.json()["graph"]["nodes"] if n["id"] == "Caja_4"
            )
            self.assertFalse(node.get("flip_ns"))

            redone = client.post(
                "/api/edit/redo",
                json={"location_id": "Parking", "depth": 1},
            )
            self.assertEqual(redone.status_code, 200, redone.text)
            node = next(
                n for n in redone.json()["graph"]["nodes"] if n["id"] == "Caja_4"
            )
            self.assertTrue(node.get("flip_ns"))

            saved = client.post("/api/save", json={})
            self.assertEqual(saved.status_code, 200, saved.text)
            self.assertTrue(saved.json().get("saved"))

            yaml_path = next(root.rglob("housewire.yaml"))
            disk = load_yaml(yaml_path)
            caja = disk["elements"]["Parking"]["elements"]["Caja_4"]
            self.assertEqual(get_physical_flips(caja), (True, False))

            # Fresh app process reads the same file — flips survive reload.
            client2 = TestClient(create_app(root))
            graph = client2.get("/api/physical?location=Parking&depth=1").json()
            node = next(n for n in graph["nodes"] if n["id"] == "Caja_4")
            self.assertTrue(node.get("flip_ns"))
            self.assertFalse(node.get("flip_we"))

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

    def test_edit_delete_selection(self) -> None:
        try:
            from fastapi.testclient import TestClient
        except (ImportError, RuntimeError):
            self.skipTest("fastapi/httpx not installed")

        from housewire.ui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = init_site(root, type_id="House", label="Site")
            add_place(doc, "Room", type_id="Room", label="Room")
            add_place(
                doc, "Box_A", under=("Room",), type_id="JunctionBox", label="A"
            )
            add_place(
                doc, "Box_B", under=("Room",), type_id="JunctionBox", label="B"
            )
            box_a = get_place_node(doc, ("Room", "Box_A"))
            box_b = get_place_node(doc, ("Room", "Box_B"))
            box_a["openings"] = ["E1"]
            box_b["openings"] = ["W1"]
            abm.add_element(box_a, "Strip", type_id="TerminalStrip")
            abm.add_element(box_b, "Strip", type_id="TerminalStrip")
            room = get_place_node(doc, ("Room",))
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
            save_site(root, doc)

            client = TestClient(create_app(root))
            client.get("/api/physical?location=Room&depth=1")
            deleted = client.post(
                "/api/edit/delete",
                json={
                    "ids": ["Room/Box_A"],
                    "location_id": "Room",
                    "depth": 1,
                },
            )
            self.assertEqual(deleted.status_code, 200, deleted.text)
            body = deleted.json()
            self.assertIn("Room/Box_A", body.get("deleted") or [])
            self.assertTrue(body.get("dirty"))
            self.assertTrue(body.get("can_undo"))
            node_ids = {n["id"] for n in body["graph"]["nodes"]}
            self.assertNotIn("Box_A", node_ids)
            self.assertIn("Box_B", node_ids)

    def test_edit_copy_cut_paste(self) -> None:
        try:
            from fastapi.testclient import TestClient
        except (ImportError, RuntimeError):
            self.skipTest("fastapi/httpx not installed")

        from housewire.ui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = init_site(root, type_id="House", label="Site")
            add_place(doc, "Room", type_id="Room", label="Room")
            add_place(
                doc, "Box", under=("Room",), type_id="JunctionBox", label="Box"
            )
            save_site(root, doc)

            client = TestClient(create_app(root))
            client.get("/api/physical?location=Room&depth=1")
            copied = client.post(
                "/api/edit/copy",
                json={"ids": ["Room/Box"]},
            )
            self.assertEqual(copied.status_code, 200, copied.text)
            payload = copied.json()["payload"]
            self.assertEqual(len(payload.get("items") or []), 1)

            pasted = client.post(
                "/api/edit/paste",
                json={
                    "parent_id": "Room",
                    "payload": payload,
                    "location_id": "Room",
                    "depth": 1,
                },
            )
            self.assertEqual(pasted.status_code, 200, pasted.text)
            self.assertTrue(pasted.json().get("dirty"))
            created = pasted.json().get("created") or []
            self.assertTrue(any("Box_1" in c for c in created), created)

            cut = client.post(
                "/api/edit/cut",
                json={
                    "ids": ["Room/Box_1"],
                    "location_id": "Room",
                    "depth": 1,
                },
            )
            self.assertEqual(cut.status_code, 200, cut.text)
            self.assertTrue(cut.json().get("payload"))
            node_ids = {n["id"] for n in cut.json()["graph"]["nodes"]}
            self.assertNotIn("Box_1", node_ids)

            # Outline must reflect unsaved paste (session buffer, not disk).
            pasted2 = client.post(
                "/api/edit/paste",
                json={
                    "parent_id": "Room",
                    "payload": payload,
                    "location_id": "Room",
                    "depth": 1,
                },
            )
            self.assertEqual(pasted2.status_code, 200, pasted2.text)
            outline = client.get("/api/outline").json()
            oids = {n["id"] for n in outline["nodes"]}
            self.assertTrue(
                any(oid.endswith("/Box_1") or oid == "Room/Box_1" for oid in oids),
                oids,
            )

        with tempfile.TemporaryDirectory() as tmp2:
            root2 = Path(tmp2)
            doc2 = init_site(root2, type_id="House", label="Site")
            add_place(doc2, "Room", type_id="Room", label="Room")
            add_place(
                doc2, "Box", under=("Room",), type_id="JunctionBox", label="Box"
            )
            add_place(
                doc2, "Host", under=("Room",), type_id="JunctionBox", label="Host"
            )
            save_site(root2, doc2)
            client2 = TestClient(create_app(root2))
            client2.get("/api/physical?location=Room&depth=2")
            moved = client2.post(
                "/api/edit/reparent",
                json={
                    "ids": ["Room/Box"],
                    "parent_id": "Room/Host",
                    "positions": {"Room/Box": {"x": 40, "y": 50}},
                    "location_id": "Room",
                    "depth": 2,
                },
            )
            self.assertEqual(moved.status_code, 200, moved.text)
            body = moved.json()
            self.assertTrue(body.get("dirty"))
            self.assertIn("Room/Host/Box", body.get("moved") or [])
            node_ids = {n["id"] for n in body["graph"]["nodes"]}
            self.assertIn("Host/Box", node_ids)
            self.assertNotIn("Box", node_ids)


if __name__ == "__main__":
    unittest.main()
