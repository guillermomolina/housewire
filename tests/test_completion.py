"""Tab completion tests for the interactive shell."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fixtures import add_place, init_site, save_site
from housewire.site.io import create_empty_house_file


class TestShellCompletion(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        doc = init_site(self.root, type_id="House")
        add_place(doc, "Parking", type_id="Floor", notes="zone")
        add_place(
            doc,
            "Caja_derivacion_1",
            under=("Parking",),
            type_id="JunctionBox",
            subtype="ip40",
        )
        save_site(self.root, doc)
        (self.root / "out").mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _session(self):
        from housewire.site.session import SiteSession

        return SiteSession(self.root)

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
        self.assertIn("location ", hits)
        self.assertNotIn("file ", hits)
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
        hits = complete_candidates(s, "cd Parking/", "Parking/", begidx=3)
        self.assertTrue(any("Caja" in h for h in hits), f"expected Caja… in {hits}")

    def test_complete_cd_includes_nested_places(self) -> None:
        from housewire.completion import complete_candidates

        s = self._session()
        s.cd("Parking")
        hits = complete_candidates(s, "cd ", "", begidx=3)
        self.assertTrue(any("Caja_derivacion_1" in h for h in hits), hits)

    def test_complete_use_index_only(self) -> None:
        from housewire.completion import complete_candidates

        s = self._session()
        create_empty_house_file(self.root / "fragment.yaml")
        hits = complete_candidates(s, "use ", "", begidx=4)
        self.assertTrue(any("housewire.yaml" in h for h in hits), hits)
        self.assertFalse(any("fragment.yaml" in h for h in hits), hits)

    def test_enable_readline_returns_bool(self) -> None:
        from housewire.completion import enable_readline_completion

        s = self._session()
        result = enable_readline_completion(s)
        self.assertIsInstance(result, bool)
