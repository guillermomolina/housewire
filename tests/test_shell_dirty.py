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

    def test_discard_on_cd_to_other_yaml(self) -> None:
        create_location_index(self.root / "zona_b", type_id="Floor")
        s = self._session()
        self._run(s, "cd zona_a")
        self._run(s, "add element MT_A --type MCB --subtype C10")
        self.answers = ["d"]  # discard
        code = self._run(s, "cd /zona_b")
        self.assertEqual(code, 0)
        self.assertEqual(s.logical_parts, ["zona_b"])
        disk = load_yaml(self.root / "zona_a" / "housewire.yaml")
        self.assertNotIn("MT_A", disk.get("elements") or {})

    def test_save_on_cd_to_other_yaml(self) -> None:
        create_location_index(self.root / "zona_b", type_id="Floor")
        s = self._session()
        self._run(s, "cd zona_a")
        self._run(s, "add element MT_A --type MCB --subtype C10")
        self.answers = ["g"]  # save
        code = self._run(s, "cd /zona_b")
        self.assertEqual(code, 0)
        disk = load_yaml(self.root / "zona_a" / "housewire.yaml")
        self.assertIn("MT_A", disk["elements"])

    def test_cancel_cd_keeps_location(self) -> None:
        create_location_index(self.root / "zona_b", type_id="Floor")
        s = self._session()
        self._run(s, "cd zona_a")
        self._run(s, "add element MT_A --type MCB --subtype C10")
        self.answers = ["c"]
        code = self._run(s, "cd /zona_b")
        self.assertEqual(code, 0)
        self.assertEqual(s.logical_parts, ["zona_a"])
        self.assertTrue(s.is_dirty())

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


if __name__ == "__main__":
    unittest.main()
