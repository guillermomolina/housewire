"""Tests for shell in-memory document buffer (dirty / save / leave)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fixtures import add_place, init_site, save_site
from housewire.project.io import HOUSEWIRE_YAML, load_yaml
from housewire.project.tree import get_place_node


class TestShellDirtyBuffer(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        doc = init_site(self.root, type_id="House")
        add_place(doc, "zona_a", type_id="Floor")
        add_place(doc, "zona_b", type_id="Floor")
        save_site(self.root, doc)
        self.site_yaml = (self.root / HOUSEWIRE_YAML).resolve()
        self.answers: list[str] = []

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _session(self):
        from housewire.project.session import ProjectSession

        s = ProjectSession(self.root)

        def fake_input(prompt: str = "") -> str:
            if not self.answers:
                raise AssertionError(f"Unexpected prompt: {prompt!r}")
            return self.answers.pop(0)

        s.input_fn = fake_input
        return s

    def _run(self, session, line: str) -> int | None:
        from housewire.commands import run_shell_line

        return run_shell_line(session, line, generate_fn=lambda root, force=False: 0)

    def test_add_element_does_not_write_until_save(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        self._run(s, "add element MT_A --type MCB --subtype C10")
        self.assertTrue(s.is_dirty())
        disk = load_yaml(self.site_yaml)
        zona = get_place_node(disk, ("zona_a",))
        self.assertNotIn("MT_A", zona.get("elements") or {})
        _path, doc = s.ensure_doc()
        place = get_place_node(doc, ("zona_a",))
        self.assertIn("MT_A", place["elements"])
        code = self._run(s, "save")
        self.assertEqual(code, 0)
        self.assertFalse(s.is_dirty())
        disk2 = load_yaml(self.site_yaml)
        self.assertIn("MT_A", get_place_node(disk2, ("zona_a",))["elements"])

    def test_prompt_label_shows_dirty_star(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        self.assertNotIn("*", s.prompt_label())
        self._run(s, "add element MT_A --type MCB --subtype C10")
        self.assertTrue(s.prompt_label().endswith("*"))

    def test_cd_keeps_dirty_buffers_in_memory(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        self._run(s, "add element MT_A --type MCB --subtype C10")
        self.assertTrue(s.is_dirty(self.site_yaml))
        code = self._run(s, "cd /zona_b")
        self.assertEqual(code, 0)
        self.assertEqual(s.logical_parts, ["zona_b"])
        self.assertTrue(s.is_dirty(self.site_yaml))
        self.assertIn("*", s.prompt_label())
        disk = load_yaml(self.site_yaml)
        self.assertNotIn("MT_A", get_place_node(disk, ("zona_a",)).get("elements") or {})
        code = self._run(s, "save")
        self.assertEqual(code, 0)
        self.assertFalse(s.is_dirty(self.site_yaml))
        disk2 = load_yaml(self.site_yaml)
        self.assertIn("MT_A", get_place_node(disk2, ("zona_a",))["elements"])

    def test_cd_away_from_dirty_does_not_prompt(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        self._run(s, "add element MT_A --type MCB --subtype C10")
        code = self._run(s, "cd /zona_b")
        self.assertEqual(code, 0)
        self.assertEqual(s.logical_parts, ["zona_b"])
        self.assertTrue(s.is_dirty(self.site_yaml))

    def test_request_leave_save(self) -> None:
        from housewire.commands import request_leave

        s = self._session()
        self._run(s, "cd zona_a")
        self._run(s, "add element MT_A --type MCB --subtype C10")
        self.answers = ["g"]
        self.assertTrue(request_leave(s))
        self.assertFalse(s.is_dirty())
        disk = load_yaml(self.site_yaml)
        self.assertIn("MT_A", get_place_node(disk, ("zona_a",))["elements"])

    def test_request_leave_cancel(self) -> None:
        from housewire.commands import request_leave

        s = self._session()
        self._run(s, "cd zona_a")
        self._run(s, "add element MT_A --type MCB --subtype C10")
        self.answers = ["c"]
        self.assertFalse(request_leave(s))
        self.assertTrue(s.is_dirty())

    def test_reload_discards(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        self._run(s, "add element MT_A --type MCB --subtype C10")
        self.answers = ["s"]
        code = self._run(s, "reload")
        self.assertEqual(code, 0)
        self.assertFalse(s.is_dirty())
        _path, doc = s.ensure_doc()
        place = get_place_node(doc, ("zona_a",))
        self.assertNotIn("MT_A", place.get("elements") or {})

    def test_cd_within_same_yaml_no_prompt(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        self._run(s, "add location Caja_in --type JunctionBox")
        self.assertTrue(s.is_dirty())
        code = self._run(s, "cd ..")
        self.assertEqual(code, 0)
        self.assertEqual(s.logical_parts, ["zona_a"])
        self.assertEqual(self.answers, [])

    def test_add_location_does_not_write_until_save(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        code = self._run(s, "add location Caja_1 --type JunctionBox --label Caja")
        self.assertEqual(code, 0)
        self.assertTrue(s.is_dirty())
        self.assertEqual(s.logical_parts, ["zona_a", "Caja_1"])
        disk = load_yaml(self.site_yaml)
        self.assertNotIn("Caja_1", get_place_node(disk, ("zona_a",)).get("elements") or {})
        names = [c.name for c in s.list_location_children()]
        self.assertEqual(names, [])
        code = self._run(s, "cd ..")
        self.assertEqual(code, 0)
        self.assertEqual(s.logical_parts, ["zona_a"])
        child_names = [c.name for c in s.list_location_children()]
        self.assertIn("Caja_1", child_names)
        code = self._run(s, "save")
        self.assertEqual(code, 0)
        saved = load_yaml(self.site_yaml)
        self.assertIn("Caja_1", get_place_node(saved, ("zona_a",))["elements"])

    def test_discard_location_on_leave(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        self._run(s, "add location Caja_tmp --type JunctionBox")
        code = self._run(s, "cd ..")
        self.assertEqual(code, 0)
        self.assertIn("Caja_tmp", [c.name for c in s.list_location_children()])
        from housewire.commands import request_leave

        self.answers = ["d"]
        self.assertTrue(request_leave(s))
        child_names = [c.name for c in s.list_location_children()]
        self.assertNotIn("Caja_tmp", child_names)
        saved = load_yaml(self.site_yaml)
        self.assertNotIn(
            "Caja_tmp",
            get_place_node(saved, ("zona_a",)).get("elements") or {},
        )

    def test_set_place_and_add_location_set(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        code = self._run(
            s,
            "add location Mech --type DeviceBox --subtype 1-gang "
            "--set install=surface --set mount=wall "
            "--set openings=[N1] --set opening_grid.N=1",
        )
        self.assertEqual(code, 0)
        self.assertTrue(s.is_dirty())
        _path, doc = s.ensure_doc()
        mech = get_place_node(doc, ("zona_a", "Mech"))
        self.assertEqual(mech["install"], "surface")
        self.assertEqual(mech["mount"], "wall")
        self.assertEqual(mech["openings"], ["N1"])
        self.assertEqual(mech["opening_grid"], {"N": 1})
        code = self._run(s, "set notes 'desde shell'")
        self.assertEqual(code, 0)
        self.assertEqual(mech["notes"], "desde shell")
        code = self._run(s, "unset notes")
        self.assertEqual(code, 0)
        self.assertNotIn("notes", mech)
        code = self._run(s, "set elements=nope")
        self.assertEqual(code, 1)

    def test_set_element_field(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        self._run(s, "add element SW --type Switch --subtype unipolar")
        code = self._run(s, "set --element SW notes cableado")
        self.assertEqual(code, 0)
        _path, doc = s.ensure_doc()
        place = get_place_node(doc, ("zona_a",))
        self.assertEqual(place["elements"]["SW"]["notes"], "cableado")

    def test_set_list_with_spaces(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        code = self._run(s, "set openings=[W1, S2, E1, E2]")
        self.assertEqual(code, 0)
        _path, doc = s.ensure_doc()
        place = get_place_node(doc, ("zona_a",))
        self.assertEqual(place["openings"], ["W1", "S2", "E1", "E2"])
        code = self._run(s, "set openings [N1, N2]")
        self.assertEqual(code, 0)
        self.assertEqual(place["openings"], ["N1", "N2"])

    def test_add_location_set_notes_two_tokens(self) -> None:
        """--set notes 'text' must not leave 'text' as a stray argparse arg."""
        s = self._session()
        self._run(s, "cd zona_a")
        code = self._run(
            s,
            'add location Box_n --type DeviceBox --set notes "back to parking"',
        )
        self.assertEqual(code, 0)
        _path, doc = s.ensure_doc()
        box = get_place_node(doc, ("zona_a", "Box_n"))
        self.assertEqual(box.get("notes"), "back to parking")


if __name__ == "__main__":
    unittest.main()
