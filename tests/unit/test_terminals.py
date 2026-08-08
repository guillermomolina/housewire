from __future__ import annotations

import unittest

from housewire.site.terminals import (
    derive_terminal_grid,
    element_terminal_layout,
    expand_terminal_grid,
    pin_to_cells,
)


class TestTerminalGrid(unittest.TestCase):
    def test_ns_means_both_faces(self) -> None:
        grid = expand_terminal_grid({"NS": 2})
        self.assertEqual(grid["N"], (2, 1))
        self.assertEqual(grid["S"], (2, 1))
        self.assertNotIn("E", grid)

    def test_n_only(self) -> None:
        grid = expand_terminal_grid({"N": 2})
        self.assertEqual(grid["N"], (2, 1))
        self.assertNotIn("S", grid)

    def test_face_cell_pins_map_to_self(self) -> None:
        terminals = {
            "N1": {"direction": "in"},
            "S1": {"direction": "out"},
            "N2": {"direction": "in"},
            "S2": {"direction": "out"},
        }
        grid = expand_terminal_grid({"NS": 2})
        cells = pin_to_cells(terminals, grid)
        self.assertEqual(cells["N1"], ["N1"])
        self.assertEqual(cells["S1"], ["S1"])
        self.assertEqual(cells["N2"], ["N2"])
        self.assertEqual(cells["S2"], ["S2"])

    def test_strip_inout_adds_opposite_face(self) -> None:
        terminals = {
            "N1": {"direction": "InOut"},
            "N2": {"direction": "InOut"},
            "N3": {"direction": "InOut"},
        }
        grid = expand_terminal_grid({"NS": 3})
        cells = pin_to_cells(terminals, grid)
        self.assertEqual(cells["N1"], ["N1", "S1"])
        self.assertEqual(cells["N3"], ["N3", "S3"])

    def test_derive_from_face_ids(self) -> None:
        self.assertEqual(
            derive_terminal_grid({"N1": {}, "S1": {}, "N2": {}, "S2": {}}),
            {"NS": 2},
        )

    def test_element_layout_catalog(self) -> None:
        catalog = {
            "MCB2P": {
                "terminal_grid": {"NS": 2},
                "terminals": {
                    "N1": {"direction": "in"},
                    "S1": {"direction": "out"},
                    "N2": {"direction": "in"},
                    "S2": {"direction": "out"},
                },
            }
        }
        terminals, grid, cells = element_terminal_layout(
            {"type": "MCB2P"}, catalog
        )
        self.assertEqual(sorted(terminals), ["N1", "N2", "S1", "S2"])
        self.assertEqual(grid["N"], (2, 1))
        self.assertEqual(cells["N1"], ["N1"])
        self.assertEqual(cells["S2"], ["S2"])

    def test_instance_subset_keeps_grid_face_cells(self) -> None:
        catalog = {
            "MCB": {
                "terminal_grid": {"NS": 2},
                "terminals": {
                    "N1": {"direction": "in"},
                    "S1": {"direction": "out"},
                    "N2": {"direction": "in"},
                    "S2": {"direction": "out"},
                },
            }
        }
        terminals, grid, cells = element_terminal_layout(
            {
                "type": "MCB",
                "terminals": {
                    "N1": {"label": ""},
                    "S1": {"label": ""},
                },
            },
            catalog,
        )
        self.assertEqual(grid["N"], (2, 1))
        self.assertIn("N2", terminals)
        self.assertEqual(cells["N2"], ["N2"])

    def test_instance_overrides_grid(self) -> None:
        catalog = {
            "TerminalStrip": {
                "terminal_grid": {"NS": 3},
                "terminals": {
                    "N1": {"direction": "InOut"},
                    "N2": {"direction": "InOut"},
                    "N3": {"direction": "InOut"},
                },
            }
        }
        terminals, grid, cells = element_terminal_layout(
            {
                "type": "TerminalStrip",
                "terminal_grid": {"NS": 6},
                "terminals": {
                    f"N{i}": {"direction": "InOut"} for i in range(1, 7)
                },
            },
            catalog,
        )
        self.assertEqual(len(terminals), 6)
        self.assertEqual(grid["N"], (6, 1))
        self.assertEqual(cells["N6"], ["N6", "S6"])

    def test_wide_instance_grid_fills_missing_inout_cells(self) -> None:
        """Catalog N1..N3 + instance NS:9 still yields N5→[N5,S5] for routing."""
        catalog = {
            "TerminalStrip": {
                "terminal_grid": {"NS": 3},
                "terminals": {
                    "N1": {"direction": "InOut"},
                    "N2": {"direction": "InOut"},
                    "N3": {"direction": "InOut"},
                },
            }
        }
        terminals, grid, cells = element_terminal_layout(
            {"type": "TerminalStrip", "terminal_grid": {"NS": 9}},
            catalog,
        )
        self.assertEqual(grid["N"], (9, 1))
        self.assertEqual(grid["S"], (9, 1))
        self.assertEqual(cells["N1"], ["N1", "S1"])
        self.assertEqual(cells["N5"], ["N5", "S5"])
        self.assertEqual(cells["N9"], ["N9", "S9"])
        self.assertEqual(len(terminals), 3)


if __name__ == "__main__":
    unittest.main()
