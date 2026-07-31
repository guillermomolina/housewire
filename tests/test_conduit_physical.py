"""Tests for conduit LocationRef.OpeningId endpoints and physical edges."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from housewire.house.conduit_ref import (
    conduit_endpoints,
    resolve_location_ref,
    split_conduit_endpoint,
)
from housewire.house.physical import build_physical_model
from housewire.project.io import create_location_index
from housewire.project import abm


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

            files = [
                root / "housewire.yaml",
                parking_yaml,
                parking / "Caja_4" / "housewire.yaml",
                parking / "Enchufe_1" / "housewire.yaml",
            ]
            model = build_physical_model(root, files)
            self.assertEqual(len(model.edges), 1)
            edge = model.edges[0]
            self.assertIn("Conducto_1", edge.label)
            self.assertIn("W2", edge.label)
            self.assertIn("N1", edge.label)
            titles = {n.title for n in model.nodes.values()}
            self.assertTrue(any("Caja 4" in t or "Caja_4" in t for t in titles), titles)
            self.assertFalse(any("Regleta" in t for t in titles), titles)
            self.assertFalse(any("Socket" in t for t in titles), titles)
