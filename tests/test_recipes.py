"""Tests for capture recipes (socket, lamp, feed)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from housewire.project import abm, recipes
from housewire.project.io import create_location_index


class TestRecipeHelpers(unittest.TestCase):
    def test_format_terminal_ref_single_and_array(self) -> None:
        self.assertEqual(recipes.format_terminal_ref("Regleta", ["1"]), "Regleta.1")
        self.assertEqual(
            recipes.format_terminal_ref("Caja/Regleta", ["3", "2", "1"]),
            "Caja/Regleta.[3, 2, 1]",
        )

    def test_qualify_element_path(self) -> None:
        self.assertEqual(
            recipes.qualify_element_path("Caja_2", "Regleta"),
            "Caja_2/Regleta",
        )
        self.assertEqual(
            recipes.qualify_element_path(".", "Regleta"),
            "Regleta",
        )
        self.assertEqual(
            recipes.qualify_element_path("Caja_2", "Other/Regleta"),
            "Other/Regleta",
        )

    def test_parse_pins(self) -> None:
        self.assertEqual(recipes.parse_pins("3,2,1"), ["3", "2", "1"])
        self.assertEqual(recipes.parse_pins("[6, 5, 2]"), ["6", "5", "2"])


class TestSocketRecipeABM(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.floor = self.root / "Parking"
        create_location_index(self.floor, type_id="Floor", label="Parking")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_socket_wired_run(self) -> None:
        doc = abm.load_editable(self.floor / "housewire.yaml", self.root)
        result = recipes.socket_wired_run(
            doc,
            place_id="Enchufe_5",
            from_ref="Caja_derivacion_2.N1",
            strip="Regleta",
        )
        self.assertEqual(result.cable_name, "Linea_a_Enchufe_5")
        self.assertEqual(result.conduit_name, "Conducto_a_Enchufe_5")
        self.assertEqual(
            result.from_terminals, "Caja_derivacion_2/Regleta.[3, 2, 1]"
        )
        self.assertEqual(result.via_ref, "Linea_a_Enchufe_5.[1, 2, 3]")
        self.assertEqual(result.to_terminals, "Enchufe_5/Socket.[L, PE, N]")
        cable = doc["cables"]["Linea_a_Enchufe_5"]
        self.assertEqual(cable["colors"], ["GY", "GNYE", "BU"])
        self.assertEqual(cable["section"], "2.5 mm2")
        conduit = doc["conduits"]["Conducto_a_Enchufe_5"]
        self.assertEqual(conduit["from"], "Caja_derivacion_2.N1")
        self.assertEqual(conduit["to"], "Enchufe_5.N1")
        self.assertEqual(len(doc["connections"]), 1)


class TestLampRecipeABM(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.floor = self.root / "Parking"
        create_location_index(self.floor, type_id="Floor", label="Parking")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_lamp_wired_run_three_wire(self) -> None:
        doc = abm.load_editable(self.floor / "housewire.yaml", self.root)
        result = recipes.lamp_wired_run(
            doc,
            place_id="Lampara_3",
            from_ref="Caja_derivacion_3.S1",
            strip="Regleta",
            pins=["6", "5", "2"],
        )
        self.assertEqual(
            result.from_terminals, "Caja_derivacion_3/Regleta.[6, 5, 2]"
        )
        self.assertEqual(result.to_terminals, "Lampara_3/Luminaire.[1, 2, 3]")
        self.assertEqual(doc["cables"][result.cable_name]["colors"], ["BN", "GNYE", "BU"])
        self.assertEqual(
            doc["conduits"][result.conduit_name]["to"], "Lampara_3.B1-1"
        )


class TestFeedRecipeABM(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.floor = self.root / "Parking"
        create_location_index(self.floor, type_id="Floor", label="Parking")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_feed_wired_run(self) -> None:
        doc = abm.load_editable(self.floor / "housewire.yaml", self.root)
        result = recipes.feed_wired_run(
            doc,
            name="Linea_CD4_a_CD3_fase",
            from_opening="Caja_derivacion_4.E1",
            to_opening="Caja_derivacion_3.N1",
            from_pin="Regleta_2.1",
            to_pin="Regleta.1",
            colors=["BK"],
            section="1.5",
        )
        self.assertEqual(result.cable_name, "Linea_CD4_a_CD3_fase")
        self.assertEqual(result.conduit_name, "Conducto_Linea_CD4_a_CD3_fase")
        self.assertEqual(
            result.from_terminals, "Caja_derivacion_4/Regleta_2.1"
        )
        self.assertEqual(result.to_terminals, "Caja_derivacion_3/Regleta.1")
        self.assertEqual(result.via_ref, "Linea_CD4_a_CD3_fase.1")
        self.assertEqual(doc["cables"][result.cable_name]["colors"], ["BK"])


class TestShellRecipes(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.floor = self.root / "Parking"
        create_location_index(self.floor, type_id="Floor", label="Parking")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _session(self):
        from housewire.project.session import ProjectSession

        return ProjectSession(self.root)

    def _run(self, session, line):
        from housewire.commands import run_shell_line

        return run_shell_line(session, line, generate_fn=lambda root, force=False: 0)

    def test_add_socket_via_shell(self) -> None:
        s = self._session()
        self._run(s, "cd Parking")
        code = self._run(
            s,
            "add socket Enchufe_5 --from Caja_derivacion_2.N1 --strip Regleta",
        )
        self.assertEqual(code, 0)
        _parent_path, parent_doc = s.ensure_doc()
        self.assertIn("Linea_a_Enchufe_5", parent_doc["cables"])
        self.assertIn("Conducto_a_Enchufe_5", parent_doc["conduits"])
        child_yaml = self.floor / "Enchufe_5" / "housewire.yaml"
        _cpath, child = s.ensure_doc(child_yaml)
        self.assertEqual(child["type"], "DeviceBox")
        self.assertIn("Socket", child["elements"])
        self.assertEqual(child["openings"], ["N1"])

    def test_add_lamp_via_shell(self) -> None:
        s = self._session()
        self._run(s, "cd Parking")
        code = self._run(
            s,
            "add lamp Lampara_3 --from Caja_derivacion_3.S1 --strip Regleta --pins 6,5,2",
        )
        self.assertEqual(code, 0)
        _path, parent = s.ensure_doc()
        self.assertIn("Linea_a_Lampara_3", parent["cables"])
        child_yaml = self.floor / "Lampara_3" / "housewire.yaml"
        _cpath, child = s.ensure_doc(child_yaml)
        self.assertEqual(child["type"], "LightPoint")
        self.assertIn("Luminaire", child["elements"])

    def test_add_feed_via_shell(self) -> None:
        s = self._session()
        self._run(s, "cd Parking")
        code = self._run(
            s,
            "add feed Linea_A_a_B --from Caja_A.E1 --to Caja_B.N1 "
            "--from-pin Regleta.1 --to-pin Regleta.2 --colors BK",
        )
        self.assertEqual(code, 0)
        _path, doc = s.ensure_doc()
        self.assertIn("Linea_A_a_B", doc["cables"])
        self.assertEqual(doc["connections"][0]["from"], "Caja_A/Regleta.1")
        self.assertEqual(doc["connections"][0]["to"], "Caja_B/Regleta.2")
