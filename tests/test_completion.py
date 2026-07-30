"""Tests de autocompletado Tab del shell."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from housewire.project.io import create_empty_house_file


# ---------------------------------------------------------------------------
# Tab completion
# ---------------------------------------------------------------------------

class TestShellCompletion(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "Parking").mkdir()
        (self.root / "Parking" / "Caja derivacion 1").mkdir()
        create_empty_house_file(self.root / "Parking" / "caja.yaml")
        create_empty_house_file(self.root / "Parking" / "Caja derivacion 1" / "caja.yaml")
        (self.root / "out").mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _session(self):
        from housewire.project.session import ProjectSession
        return ProjectSession(self.root)

    def test_complete_commands(self) -> None:
        from housewire.completion import complete_candidates
        s = self._session()
        hits = complete_candidates(s, "c", "c", begidx=0)
        self.assertTrue(any(h.startswith("cd") for h in hits))
        self.assertIn("cd ", hits)

    def test_complete_add_subcommands(self) -> None:
        from housewire.completion import complete_candidates
        s = self._session()
        hits = complete_candidates(s, "add ", "", begidx=4)
        self.assertIn("element ", hits)
        self.assertIn("pend ", hits)
        hits_e = complete_candidates(s, "add e", "e", begidx=4)
        self.assertEqual(hits_e, ["element "])

    def test_complete_cd_dirs(self) -> None:
        from housewire.completion import complete_candidates
        s = self._session()
        hits = complete_candidates(s, "cd ", "", begidx=3)
        self.assertTrue(any(h.startswith("Parking") for h in hits))
        self.assertFalse(any(h.startswith("out") for h in hits))

    def test_complete_cd_nested_with_spaces(self) -> None:
        from housewire.completion import complete_candidates
        s = self._session()
        # Con delims sin '/', el token completo es 'Parking/'
        hits = complete_candidates(s, "cd Parking/", "Parking/", begidx=3)
        self.assertTrue(
            any("Caja" in h for h in hits),
            f"esperado Caja… en {hits}",
        )

    def test_complete_use_yaml_only(self) -> None:
        from housewire.completion import complete_candidates
        s = self._session()
        s.cd("Parking")
        hits = complete_candidates(s, "use ", "", begidx=4)
        self.assertTrue(any("caja.yaml" in h for h in hits))
        self.assertFalse(any(h.endswith("/") for h in hits))

    def test_enable_readline_returns_bool(self) -> None:
        from housewire.completion import enable_readline_completion
        s = self._session()
        result = enable_readline_completion(s)
        self.assertIsInstance(result, bool)
