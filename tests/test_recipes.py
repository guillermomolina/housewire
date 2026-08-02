"""Tests for capture recipes (socket, lamp, feed)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fixtures import add_place, init_site, save_site
from housewire.site import abm, recipes
from housewire.site.io import HOUSEWIRE_YAML
from housewire.site.tree import get_place_node


class TestRecipeHelpers(unittest.TestCase):
    def test_format_terminal_ref(self) -> None:
        self.assertEqual(recipes.format_terminal_ref("Regleta", "1"), "Regleta.N1")
        self.assertEqual(
            recipes.format_terminal_ref("Caja/Regleta", "3"),
            "Caja/Regleta.N3",
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
        self.assertEqual(recipes.parse_pins("3,2,1"), ["N3", "N2", "N1"])
        self.assertEqual(recipes.parse_pins("[6, 5, 2]"), ["N6", "N5", "N2"])


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
            result.from_terminals,
            (
                "Caja_derivacion_2/Regleta.N3",
                "Caja_derivacion_2/Regleta.N2",
                "Caja_derivacion_2/Regleta.N1",
            ),
        )
        self.assertEqual(
            result.to_terminals,
            ("Enchufe_5/Socket.N1", "Enchufe_5/Socket.N2", "Enchufe_5/Socket.N3"),
        )
        self.assertEqual(
            result.conductor_names,
            ("Linea_a_Enchufe_5_1", "Linea_a_Enchufe_5_2", "Linea_a_Enchufe_5_3"),
        )
        cable = place["cables"]["Linea_a_Enchufe_5"]
        self.assertEqual(cable["type"], "Cable")
        self.assertEqual(cable["contains"], list(result.conductor_names))
        self.assertEqual(place["cables"]["Linea_a_Enchufe_5_1"]["color"], "GY")
        conduit = place["cables"]["Conducto_a_Enchufe_5"]
        self.assertEqual(conduit["from"], "Caja_derivacion_2.N1")
        self.assertEqual(conduit["to"], "Enchufe_5.N1")
        self.assertNotIn("connections", place)


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
            result.from_terminals,
            (
                "Caja_derivacion_3/Regleta.N6",
                "Caja_derivacion_3/Regleta.N5",
                "Caja_derivacion_3/Regleta.N2",
            ),
        )
        self.assertEqual(
            result.to_terminals,
            (
                "Lampara_3/Luminaire.N1",
                "Lampara_3/Luminaire.N2",
                "Lampara_3/Luminaire.N3",
            ),
        )
        self.assertEqual(
            [place["cables"][c]["color"] for c in result.conductor_names],
            ["BN", "GNYE", "BU"],
        )
        self.assertEqual(
            place["cables"][result.conduit_name]["to"], "Lampara_3.B1-1"
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
            to_pin="Regleta.N1",
            colors=["BK"],
            section="1.5",
        )
        self.assertEqual(result.cable_name, "Linea_CD4_a_CD3_fase")
        self.assertEqual(result.conduit_name, "Conducto_Linea_CD4_a_CD3_fase")
        self.assertEqual(
            result.from_terminals, ("Caja_derivacion_4/Regleta_2.N1",)
        )
        self.assertEqual(result.to_terminals, ("Caja_derivacion_3/Regleta.N1",))
        self.assertEqual(result.conductor_names, ("Linea_CD4_a_CD3_fase_1",))
        self.assertEqual(
            place["cables"]["Linea_CD4_a_CD3_fase_1"]["color"], "BK"
        )


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
        from housewire.site.session import SiteSession

        return SiteSession(self.root)

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
        self.assertIn("Conducto_a_Enchufe_5", parking["cables"])
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
            "--from-pin Regleta.N1 --to-pin Regleta.N2 --colors BK",
        )
        self.assertEqual(code, 0)
        _path, doc = s.ensure_doc()
        parking = get_place_node(doc, ("Parking",))
        self.assertIn("Linea_A_a_B", parking["cables"])
        self.assertEqual(
            parking["cables"]["Linea_A_a_B_1"]["from"], "Caja_A/Regleta.N1"
        )
        self.assertEqual(
            parking["cables"]["Linea_A_a_B_1"]["to"], "Caja_B/Regleta.N2"
        )
