"""Tests for capture recipes (socket, lamp, feed)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fixtures import add_place, init_site, save_site
from housewire.project import abm, recipes
from housewire.project.io import HOUSEWIRE_YAML
from housewire.project.tree import get_place_node


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
        doc = init_site(self.root, type_id="House")
        add_place(doc, "Parking", type_id="Floor", label="Parking")
        save_site(self.root, doc)
        self.site_yaml = self.root / HOUSEWIRE_YAML

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_socket_wired_run(self) -> None:
        doc = abm.load_editable(self.site_yaml, self.root)
        place = get_place_node(doc, ("Parking",))
        result = recipes.socket_wired_run(
            place,
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
        cable = place["cables"]["Linea_a_Enchufe_5"]
        self.assertEqual(cable["colors"], ["GY", "GNYE", "BU"])
        self.assertEqual(cable["section"], "2.5 mm2")
        conduit = place["conduits"]["Conducto_a_Enchufe_5"]
        self.assertEqual(conduit["from"], "Caja_derivacion_2.N1")
        self.assertEqual(conduit["to"], "Enchufe_5.N1")
        self.assertEqual(len(place["connections"]), 1)


class TestLampRecipeABM(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        doc = init_site(self.root, type_id="House")
        add_place(doc, "Parking", type_id="Floor", label="Parking")
        save_site(self.root, doc)
        self.site_yaml = self.root / HOUSEWIRE_YAML

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_lamp_wired_run_three_wire(self) -> None:
        doc = abm.load_editable(self.site_yaml, self.root)
        place = get_place_node(doc, ("Parking",))
        result = recipes.lamp_wired_run(
            place,
            place_id="Lampara_3",
            from_ref="Caja_derivacion_3.S1",
            strip="Regleta",
            pins=["6", "5", "2"],
        )
        self.assertEqual(
            result.from_terminals, "Caja_derivacion_3/Regleta.[6, 5, 2]"
        )
        self.assertEqual(result.to_terminals, "Lampara_3/Luminaire.[1, 2, 3]")
        self.assertEqual(place["cables"][result.cable_name]["colors"], ["BN", "GNYE", "BU"])
        self.assertEqual(
            place["conduits"][result.conduit_name]["to"], "Lampara_3.B1-1"
        )


class TestFeedRecipeABM(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        doc = init_site(self.root, type_id="House")
        add_place(doc, "Parking", type_id="Floor", label="Parking")
        save_site(self.root, doc)
        self.site_yaml = self.root / HOUSEWIRE_YAML

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_feed_wired_run(self) -> None:
        doc = abm.load_editable(self.site_yaml, self.root)
        place = get_place_node(doc, ("Parking",))
        result = recipes.feed_wired_run(
            place,
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
        self.assertEqual(place["cables"][result.cable_name]["colors"], ["BK"])


class TestShellRecipes(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        doc = init_site(self.root, type_id="House")
        add_place(doc, "Parking", type_id="Floor", label="Parking")
        save_site(self.root, doc)
        self.site_yaml = self.root / HOUSEWIRE_YAML

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _session(self):
        from housewire.project.session import ProjectSession

        return ProjectSession(self.root)

    def _run(self, session, line):
        from housewire.commands import run_shell_line

        return run_shell_line(session, line)

    def test_add_socket_via_shell(self) -> None:
        s = self._session()
        self._run(s, "cd Parking")
        code = self._run(
            s,
            "add socket Enchufe_5 --from Caja_derivacion_2.N1 --strip Regleta",
        )
        self.assertEqual(code, 0)
        _path, doc = s.ensure_doc()
        parking = get_place_node(doc, ("Parking",))
        self.assertIn("Linea_a_Enchufe_5", parking["cables"])
        self.assertIn("Conducto_a_Enchufe_5", parking["conduits"])
        child = get_place_node(doc, ("Parking", "Enchufe_5"))
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
        _path, doc = s.ensure_doc()
        parking = get_place_node(doc, ("Parking",))
        self.assertIn("Linea_a_Lampara_3", parking["cables"])
        child = get_place_node(doc, ("Parking", "Lampara_3"))
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
        parking = get_place_node(doc, ("Parking",))
        self.assertIn("Linea_A_a_B", parking["cables"])
        self.assertEqual(parking["connections"][0]["from"], "Caja_A/Regleta.1")
        self.assertEqual(parking["connections"][0]["to"], "Caja_B/Regleta.2")
