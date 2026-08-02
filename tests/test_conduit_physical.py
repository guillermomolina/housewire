"""Tests for conduit LocationRef.OpeningId endpoints and physical edges."""
from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from fixtures import add_place, init_site, save_site
from housewire.house.conduit_ref import (
    conduit_endpoints,
    resolve_location_ref,
    split_conduit_endpoint,
)
from housewire.house.physical import build_physical_model, model_to_dot
from housewire.site import abm
from housewire.site.io import HOUSEWIRE_YAML
from housewire.site.tree import get_place_node


class TestConduitEndpoints(unittest.TestCase):
    def test_split_endpoint(self) -> None:
        self.assertEqual(split_conduit_endpoint("Caja_derivacion_4.W2"), ("Caja_derivacion_4", "W2"))
        self.assertEqual(
            split_conduit_endpoint("Parking/Caja_derivacion_4.B2-1"),
            ("Parking/Caja_derivacion_4", "B2-1"),
        )
        self.assertEqual(split_conduit_endpoint(".N1"), (".", "N1"))

    def test_conduit_endpoints_require_from_to(self) -> None:
        ends = conduit_endpoints({"from": "A.N1", "to": "B.S1"})
        self.assertEqual(ends, ("A.N1", "B.S1"))
        with self.assertRaises(ValueError):
            conduit_endpoints({"contains": ["X"]})

    def test_resolve_sibling_under_current(self) -> None:
        known = {("Parking",), ("Parking", "Caja_derivacion_4"), ("Parking", "Enchufe_1")}
        self.assertEqual(
            resolve_location_ref(
                "Caja_derivacion_4",
                current_parts=["Parking"],
                known=known,
            ),
            ("Parking", "Caja_derivacion_4"),
        )

    def test_resolve_dot_is_current(self) -> None:
        known = {("Parking", "Caja_2")}
        self.assertEqual(
            resolve_location_ref(".", current_parts=["Parking", "Caja_2"], known=known),
            ("Parking", "Caja_2"),
        )


class TestPhysicalConduits(unittest.TestCase):
    def test_edges_from_conduits_not_connections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = init_site(root, type_id="House", label="Site")
            add_place(doc, "Parking", type_id="Floor", label="Parking")
            add_place(
                doc,
                "Caja_4",
                under=("Parking",),
                type_id="JunctionBox",
                label="Caja 4",
            )
            add_place(
                doc,
                "Enchufe_1",
                under=("Parking",),
                type_id="DeviceBox",
                label="Enchufe 1",
            )
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
            save_site(root, doc)

            site_yaml = root / HOUSEWIRE_YAML
            model = build_physical_model(root, [site_yaml])
            self.assertEqual(len(model.edges), 1)
            edge = model.edges[0]
            self.assertIn("Conducto_1", edge.label)
            self.assertIn("W2", edge.label)
            self.assertIn("N1", edge.label)
            self.assertNotIn("Linea", edge.label)
            titles = {n.title for n in model.nodes.values()}
            self.assertTrue(any("Caja 4" in t or "Caja_4" in t for t in titles), titles)
            self.assertFalse(any("Regleta" in t for t in titles), titles)
            self.assertFalse(any("Socket" in t for t in titles), titles)

            dot = model_to_dot(model)
            self.assertIn("subgraph cluster_Parking {", dot)
            self.assertNotIn("subgraph cluster_Parking_Caja_4", dot, dot)
            self.assertIn("Parking_Caja_4 [", dot, dot)
            self.assertIn("Parking_Enchufe_1 [", dot, dot)
            self.assertIsNone(re.search(r"(?m)^\s+Parking \[", dot), dot)
            # Openings stay in the label; Graphviz picks border clip by placement.
            self.assertIn("Parking_Caja_4 -> Parking_Enchufe_1", dot, dot)
            self.assertNotIn("Parking_Caja_4:w", dot, dot)
            self.assertIn("W2 ↔ N1", dot, dot)
            self.assertIn("dir=none", dot)
            self.assertIn("splines=true", dot)
            # Type-based styling
            self.assertIn('bgcolor="#EAF6EA"', dot)  # Floor cluster
            self.assertIn("shape=note", dot)  # DeviceBox
            self.assertIn('fillcolor="#FFFFFF"', dot)  # JunctionBox
