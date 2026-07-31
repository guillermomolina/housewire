"""Tests for shell in-memory document buffer (dirty / save / leave)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from housewire.project.io import create_location_index, load_yaml


class TestShellDirtyBuffer(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        create_location_index(self.root / "zona_a", type_id="Floor")
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
        disk = load_yaml(self.root / "zona_a" / "housewire.yaml")
        self.assertNotIn("MT_A", disk.get("elements") or {})
        # In memory it is there
        _path, doc = s.ensure_doc()
        self.assertIn("MT_A", doc["elements"])
        code = self._run(s, "save")
        self.assertEqual(code, 0)
        self.assertFalse(s.is_dirty())
        disk2 = load_yaml(self.root / "zona_a" / "housewire.yaml")
        self.assertIn("MT_A", disk2["elements"])

    def test_prompt_label_shows_dirty_star(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        self.assertNotIn("*", s.prompt_label())
        self._run(s, "add element MT_A --type MCB --subtype C10")
        self.assertTrue(s.prompt_label().endswith("*"))

    def test_cd_keeps_dirty_buffers_in_memory(self) -> None:
        create_location_index(self.root / "zona_b", type_id="Floor")
        s = self._session()
        self._run(s, "cd zona_a")
        self._run(s, "add element MT_A --type MCB --subtype C10")
        zona_a_yaml = (self.root / "zona_a" / "housewire.yaml").resolve()
        self.assertTrue(s.is_dirty(zona_a_yaml))
        code = self._run(s, "cd /zona_b")
        self.assertEqual(code, 0)
        self.assertEqual(s.logical_parts, ["zona_b"])
        self.assertTrue(s.is_dirty(zona_a_yaml))
        self.assertIn("*", s.prompt_label())
        disk = load_yaml(self.root / "zona_a" / "housewire.yaml")
        self.assertNotIn("MT_A", disk.get("elements") or {})
        code = self._run(s, "save")
        self.assertEqual(code, 0)
        self.assertFalse(s.is_dirty(zona_a_yaml))
        disk2 = load_yaml(self.root / "zona_a" / "housewire.yaml")
        self.assertIn("MT_A", disk2["elements"])

    def test_cd_away_from_dirty_does_not_prompt(self) -> None:
        create_location_index(self.root / "zona_b", type_id="Floor")
        s = self._session()
        self._run(s, "cd zona_a")
        self._run(s, "add element MT_A --type MCB --subtype C10")
        # No answers queued — would fail if cd prompted
        code = self._run(s, "cd /zona_b")
        self.assertEqual(code, 0)
        self.assertEqual(s.logical_parts, ["zona_b"])
        self.assertTrue(s.is_dirty((self.root / "zona_a" / "housewire.yaml").resolve()))

    def test_request_leave_save(self) -> None:
        from housewire.commands import request_leave

        s = self._session()
        self._run(s, "cd zona_a")
        self._run(s, "add element MT_A --type MCB --subtype C10")
        self.answers = ["g"]
        self.assertTrue(request_leave(s))
        self.assertFalse(s.is_dirty())
        disk = load_yaml(self.root / "zona_a" / "housewire.yaml")
        self.assertIn("MT_A", disk["elements"])

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
        self.assertNotIn("MT_A", doc.get("elements") or {})

    def test_cd_within_same_yaml_no_prompt(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        self._run(s, "add location Caja_in --type JunctionBox --inline")
        self.assertTrue(s.is_dirty())
        # Still same hosting yaml — no prompt, answers must stay unused
        code = self._run(s, "cd ..")
        self.assertEqual(code, 0)
        self.assertEqual(s.logical_parts, ["zona_a"])
        self.assertEqual(self.answers, [])

    def test_add_outline_location_does_not_write_until_save(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        code = self._run(s, "add location Caja_1 --type JunctionBox --label Caja")
        self.assertEqual(code, 0)
        self.assertTrue(s.is_dirty())
        self.assertEqual(s.logical_parts, ["zona_a", "Caja_1"])
        disk_path = self.root / "zona_a" / "Caja_1" / "housewire.yaml"
        self.assertFalse(disk_path.is_file())
        self.assertFalse(disk_path.parent.is_dir())
        names = [c.name for c in s.list_location_children()]
        # We're inside Caja_1; children of empty box
        self.assertEqual(names, [])
        code = self._run(s, "cd ..")
        self.assertEqual(code, 0)
        self.assertEqual(s.logical_parts, ["zona_a"])
        # Still only in memory after cd
        self.assertFalse(disk_path.is_file())
        self.assertTrue(s.is_dirty(disk_path.resolve()))
        child_names = [c.name for c in s.list_location_children()]
        self.assertIn("Caja_1", child_names)
        code = self._run(s, "save")
        self.assertEqual(code, 0)
        self.assertTrue(disk_path.is_file())
        self.assertFalse(s.is_dirty(disk_path.resolve()))

    def test_discard_outline_location_on_leave(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        self._run(s, "add location Caja_tmp --type JunctionBox")
        disk_path = self.root / "zona_a" / "Caja_tmp" / "housewire.yaml"
        self.assertFalse(disk_path.is_file())
        code = self._run(s, "cd ..")
        self.assertEqual(code, 0)
        self.assertIn("Caja_tmp", [c.name for c in s.list_location_children()])
        from housewire.commands import request_leave

        self.answers = ["d"]  # discard staged outline on exit
        self.assertTrue(request_leave(s))
        self.assertFalse(disk_path.is_file())
        self.assertFalse(disk_path.parent.is_dir())
        child_names = [c.name for c in s.list_location_children()]
        self.assertNotIn("Caja_tmp", child_names)

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
        self.assertEqual(doc["install"], "surface")
        self.assertEqual(doc["mount"], "wall")
        self.assertEqual(doc["openings"], ["N1"])
        self.assertEqual(doc["opening_grid"], {"N": 1})
        disk = self.root / "zona_a" / "Mech" / "housewire.yaml"
        self.assertFalse(disk.is_file())
        code = self._run(s, "set notes 'desde shell'")
        self.assertEqual(code, 0)
        self.assertEqual(doc["notes"], "desde shell")
        code = self._run(s, "unset notes")
        self.assertEqual(code, 0)
        self.assertNotIn("notes", doc)
        code = self._run(s, "set elements=nope")
        self.assertEqual(code, 1)

    def test_set_element_field(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        self._run(s, "add element SW --type Switch --subtype unipolar")
        code = self._run(s, "set --element SW notes cableado")
        self.assertEqual(code, 0)
        _path, doc = s.ensure_doc()
        self.assertEqual(doc["elements"]["SW"]["notes"], "cableado")

    def test_set_list_with_spaces(self) -> None:
        s = self._session()
        self._run(s, "cd zona_a")
        code = self._run(s, "set openings=[W1, S2, E1, E2]")
        self.assertEqual(code, 0)
        _path, doc = s.ensure_doc()
        self.assertEqual(doc["openings"], ["W1", "S2", "E1", "E2"])
        code = self._run(s, "set openings [N1, N2]")
        self.assertEqual(code, 0)
        self.assertEqual(doc["openings"], ["N1", "N2"])

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
        self.assertEqual(doc.get("notes"), "back to parking")


if __name__ == "__main__":
    unittest.main()
