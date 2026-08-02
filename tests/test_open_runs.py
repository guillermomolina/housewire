"""Tests for open → claim → land open-ended runs."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fixtures import add_place, init_site, save_site
from housewire.project import abm, open_runs
from housewire.project.io import HOUSEWIRE_YAML
from housewire.project.tree import get_place_node


class TestOpenRunHelpers(unittest.TestCase):
    def test_parse_and_format_notes(self) -> None:
        notes = open_runs.format_open_notes(
            status="open", leaves="CG.S2", extra="guess recibidor"
        )
        meta = open_runs.parse_open_notes(notes)
        self.assertEqual(meta.status, "open")
        self.assertEqual(meta.leaves, "CG.S2")
        self.assertIn("guess", meta.extra)

    def test_resolve_leave_ref(self) -> None:
        self.assertEqual(
            open_runs.resolve_leave_ref("S2", current_location_ref="Cuadro_General"),
            "Cuadro_General.S2",
        )
        self.assertEqual(
            open_runs.resolve_leave_ref(
                "A/B.S2", current_location_ref="Cuadro_General"
            ),
            "A/B.S2",
        )


class TestOpenClaimLandABM(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        doc = init_site(self.root, type_id="House")
        add_place(doc, "Floor", type_id="Floor", label="Floor")
        save_site(self.root, doc)
        self.site_yaml = self.root / HOUSEWIRE_YAML

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_open_claim_land_flow(self) -> None:
        doc = abm.load_editable(self.site_yaml, self.root)
        floor = get_place_node(doc, ("Floor",))
        name = open_runs.add_open_cable(
            floor, leaves="Cuadro_General.S2", colors=["BN", "BU"], section="1.5"
        )
        self.assertEqual(name, "OPEN_Linea_01")
        self.assertEqual(floor.get("conduits") or {}, {})
        meta = open_runs.parse_open_notes(floor["cables"][name]["notes"])
        self.assertEqual(meta.status, "open")
        self.assertEqual(meta.leaves, "Cuadro_General.S2")

        cd, meta2 = open_runs.claim_open_cable(
            floor,
            name,
            enter="Caja_derivacion_1.N1",
            exit="Caja_derivacion_1.E2",
        )
        self.assertEqual(cd, "Conducto_OPEN_Linea_01_01")
        self.assertEqual(meta2.status, "claimed")
        self.assertEqual(meta2.enters, "Caja_derivacion_1.N1")
        self.assertEqual(meta2.exits, "Caja_derivacion_1.E2")
        self.assertEqual(
            floor["conduits"][cd]["from"], "Cuadro_General.S2"
        )
        self.assertEqual(
            floor["conduits"][cd]["to"], "Caja_derivacion_1.N1"
        )

        final = open_runs.land_open_cable(
            floor,
            name,
            from_ref="Cuadro_General/MT.2",
            to_ref="Caja_derivacion_1/Regleta.1",
            as_name="Linea_CG_a_CD1",
        )
        self.assertEqual(final, "Linea_CG_a_CD1")
        self.assertNotIn(name, floor["cables"])
        self.assertIn("Linea_CG_a_CD1", floor["cables"])
        self.assertEqual(
            floor["conduits"][cd]["contains"], ["Linea_CG_a_CD1"]
        )
        conn = floor["connections"][-1]
        self.assertEqual(conn["via"], "Linea_CG_a_CD1.[1, 2]")
        self.assertEqual(conn["from"], "Cuadro_General/MT.2")
        self.assertEqual(conn["to"], "Caja_derivacion_1/Regleta.1")

    def test_second_claim_uses_exits(self) -> None:
        doc = abm.load_editable(self.site_yaml, self.root)
        floor = get_place_node(doc, ("Floor",))
        name = open_runs.add_open_cable(floor, leaves="CG.S2", colors=["BN"])
        open_runs.claim_open_cable(
            floor, name, enter="CD1.N1", exit="CD1.E2"
        )
        cd2, meta = open_runs.claim_open_cable(
            floor, name, enter="CD2.W1"
        )
        self.assertEqual(floor["conduits"][cd2]["from"], "CD1.E2")
        self.assertEqual(floor["conduits"][cd2]["to"], "CD2.W1")
        self.assertEqual(meta.enters, "CD2.W1")
        self.assertIsNone(meta.exits)

    def test_land_requires_as_for_open_id(self) -> None:
        doc = abm.load_editable(self.site_yaml, self.root)
        floor = get_place_node(doc, ("Floor",))
        name = open_runs.add_open_cable(floor, leaves="CG.S2", colors=["BN"])
        with self.assertRaises(ValueError) as ctx:
            open_runs.land_open_cable(
                floor, name, from_ref="A.1", to_ref="B.1"
            )
        self.assertIn("--as", str(ctx.exception))


class TestShellOpenClaimLand(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        doc = init_site(self.root, type_id="House")
        add_place(doc, "CG", type_id="Panel", label="CG")
        add_place(doc, "CD1", type_id="JunctionBox", label="CD1")
        get_place_node(doc, ("CG",))["openings"] = ["S2"]
        get_place_node(doc, ("CD1",))["openings"] = ["N1", "E2"]
        save_site(self.root, doc)
        self.site_yaml = self.root / HOUSEWIRE_YAML

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _session(self):
        from housewire.project.session import ProjectSession

        return ProjectSession(self.root)

    def _run(self, session, line):
        from housewire.commands import run_shell_line

        return run_shell_line(
            session, line
        )

    def test_shell_open_claim_land(self) -> None:
        s = self._session()
        self._run(s, "cd CG")
        code = self._run(s, "open S2 1.5 --colors BN,BU")
        self.assertEqual(code, 0)
        _path, doc = s.ensure_doc()
        cg = get_place_node(doc, ("CG",))
        self.assertIn("OPEN_Linea_01", cg["cables"])

        code = self._run(s, "claim OPEN_Linea_01 --enter CD1.N1 --exit CD1.E2")
        self.assertEqual(code, 0)

        _path, doc = s.ensure_doc()
        cg = get_place_node(doc, ("CG",))
        self.assertTrue(cg["conduits"])
        meta = open_runs.parse_open_notes(cg["cables"]["OPEN_Linea_01"]["notes"])
        self.assertEqual(meta.status, "claimed")
        self.assertTrue(str(meta.enters).endswith("N1"))

        code = self._run(
            s,
            "land OPEN_Linea_01 --from CG/MT.1 --to CD1/Regleta.1 "
            "--as Linea_CG_a_CD1",
        )
        self.assertEqual(code, 0)
        _path, doc = s.ensure_doc()
        cg = get_place_node(doc, ("CG",))
        self.assertIn("Linea_CG_a_CD1", cg["cables"])
        self.assertNotIn("OPEN_Linea_01", cg["cables"])

    def test_opens_lists_runs(self) -> None:
        from io import StringIO
        import sys

        s = self._session()
        self._run(s, "cd CG")
        self._run(s, "open S2")
        buf = StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            code = self._run(s, "opens")
        finally:
            sys.stdout = old
        self.assertEqual(code, 0)
        self.assertIn("OPEN_Linea_01", buf.getvalue())
