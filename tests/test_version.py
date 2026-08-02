"""CLI / shell version reporting."""
from __future__ import annotations

import unittest
from io import StringIO
from unittest.mock import patch

from housewire import __version__
from housewire.cli import main


class TestVersion(unittest.TestCase):
    def test_version_flag(self) -> None:
        buf = StringIO()
        with patch("sys.stdout", buf):
            with self.assertRaises(SystemExit) as ctx:
                main(["--version"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn(__version__, buf.getvalue())

    def test_version_subcommand(self) -> None:
        buf = StringIO()
        with patch("sys.stdout", buf):
            code = main(["version"])
        self.assertEqual(code, 0)
        self.assertEqual(buf.getvalue().strip(), f"HouseWire {__version__}")
