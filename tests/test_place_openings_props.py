"""Properties panel API: opening_grid / openings edits."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fixtures import add_place, init_site, save_site
from housewire.site.openings import list_grid_cell_ids
from housewire.site.recipe_actions import place_detail, update_place_properties
from housewire.site.session import SiteSession
from housewire.site.tree import get_place_node


class TestListGridCellIds(unittest.TestCase):
    def test_side_and_plane(self) -> None:
        self.assertEqual(list_grid_cell_ids("N", 3), ["N1", "N2", "N3"])
        self.assertEqual(
            list_grid_cell_ids("B", 2, 2),
            ["B1-1", "B1-2", "B2-1", "B2-2"],
        )


class TestPlaceOpeningProperties(unittest.TestCase):
    def test_patch_opening_grid_and_openings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = init_site(root, type_id="House", label="Site")
            add_place(
                doc,
                "Caja",
                type_id="JunctionBox",
                subtype="IP40",
                label="Caja",
            )
            caja = get_place_node(doc, ("Caja",))
            caja["opening_grid"] = {"N": 1}
            caja["openings"] = ["N1"]
            save_site(root, doc)

            session = SiteSession(root)
            detail = update_place_properties(
                session,
                canvas_location_id=".",
                place_id="Caja",
                fields={
                    "opening_grid": {"N": 2, "B": "2x1"},
                    "openings": ["N1", "N2", "B1-1"],
                },
            )
            self.assertEqual(sorted(detail["openings"]), ["B1-1", "N1", "N2"])
            self.assertEqual(detail["opening_grid"]["N"], 2)
            self.assertEqual(detail["opening_grid"]["B"], "2x1")
            self.assertNotIn("connects", detail)

            again = place_detail(session, canvas_location_id=".", place_id="Caja")
            self.assertEqual(sorted(again["openings"]), ["B1-1", "N1", "N2"])


if __name__ == "__main__":
    unittest.main()
