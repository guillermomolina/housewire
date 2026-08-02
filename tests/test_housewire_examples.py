"""Tests for the housewire-examples package discovery API."""
from __future__ import annotations

import unittest


class TestHousewireExamples(unittest.TestCase):
    def test_site_yaml_test01(self) -> None:
        try:
            from housewire_examples import iter_site_names, site_yaml
        except ImportError as exc:
            raise unittest.SkipTest(
                "housewire-examples not installed "
                "(pip install -e packages/housewire-examples)"
            ) from exc

        names = iter_site_names()
        self.assertIn("Test_01", names)
        path = site_yaml("Test_01")
        self.assertTrue(path.is_file(), msg=path)
        text = path.read_text(encoding="utf-8")
        self.assertIn("schema: house/v2", text)
        self.assertIn("Test 01", text)


if __name__ == "__main__":
    unittest.main()
