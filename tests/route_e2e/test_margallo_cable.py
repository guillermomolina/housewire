"""Live E2E: one cable remains one jacket across different terminal pairs."""
from __future__ import annotations

import unittest
from pathlib import Path

from tests.route_e2e._harness import REPO, dump_live_canvas


class TestMargalloCable(unittest.TestCase):
    def test_three_conductor_cable_has_one_jacket(self) -> None:
        site = REPO / "sites" / "Margalló 4A" / "Test.yaml"
        if not site.is_file():
            raise unittest.SkipTest(f"fixture not found: {site}")

        data = dump_live_canvas(site, require_tubes=True)
        self.assertNotIn("err", data, msg=data)
        jackets = [
            jacket for jacket in data.get("jackets") or []
            if jacket.get("id") == "Funda"
        ]
        self.assertEqual(
            len(jackets),
            1,
            msg=f"Funda must be one shared jacket, got {jackets!r}",
        )
        self.assertGreaterEqual(
            jackets[0]["width"],
            19.0,
            msg=f"Funda jacket must enclose its three conductors: {jackets!r}",
        )


if __name__ == "__main__":
    unittest.main()
