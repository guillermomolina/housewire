from __future__ import annotations

import unittest

from housewire.project.terminals import (
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

    def test_mcb2p_collapse_mapping(self) -> None:
        terminals = {
            "1": {"direction": "in"},
            "2": {"direction": "out"},
            "3": {"direction": "in"},
            "4": {"direction": "out"},
        }
        grid = expand_terminal_grid({"NS": 2})
        cells = pin_to_cells(terminals, grid, [[1, 2], [3, 4]])
        self.assertEqual(cells["1"], ["N1"])
        self.assertEqual(cells["2"], ["S1"])
        self.assertEqual(cells["3"], ["N2"])
        self.assertEqual(cells["4"], ["S2"])

    def test_strip_inout_columns(self) -> None:
        terminals = {
            "1": {"direction": "inout"},
            "2": {"direction": "inout"},
            "3": {"direction": "inout"},
        }
        grid = expand_terminal_grid({"NS": 3})
        cells = pin_to_cells(terminals, grid, None)
        self.assertEqual(cells["1"], ["N1", "S1"])
        self.assertEqual(cells["3"], ["N3", "S3"])

    def test_derive_from_collapse(self) -> None:
        self.assertEqual(
            derive_terminal_grid({"1": {}, "2": {}}, [[1, 2], [3, 4]]),
            {"NS": 2},
        )

    def test_element_layout_catalog(self) -> None:
        catalog = {
            "MCB2P": {
                "terminal_grid": {"NS": 2},
                "terminals": {
                    "1": {"direction": "in"},
                    "2": {"direction": "out"},
                    "3": {"direction": "in"},
                    "4": {"direction": "out"},
                },
                "wireviz_collapse": [[1, 2], [3, 4]],
            }
        }
        terminals, grid, cells = element_terminal_layout(
            {"type": "MCB2P"}, catalog
        )
        self.assertEqual(sorted(terminals), ["1", "2", "3", "4"])
        self.assertEqual(grid["N"], (2, 1))
        self.assertEqual(cells["1"], ["N1"])
        self.assertEqual(cells["4"], ["S2"])

    def test_instance_overrides_grid(self) -> None:
        catalog = {
            "TerminalStrip": {
                "terminal_grid": {"NS": 3},
                "terminals": {
                    "1": {"direction": "inout"},
                    "2": {"direction": "inout"},
                    "3": {"direction": "inout"},
                },
            }
        }
        _t, grid, cells = element_terminal_layout(
            {
                "type": "TerminalStrip",
                "terminal_grid": {"NS": 6},
                "terminals": {
                    str(i): {"direction": "inout"} for i in range(1, 7)
                },
            },
            catalog,
        )
        self.assertEqual(grid["N"], (6, 1))
        self.assertEqual(cells["6"], ["N6", "S6"])


if __name__ == "__main__":
    unittest.main()
