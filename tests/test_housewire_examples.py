"""Tests for the housewire-examples package discovery API."""
from __future__ import annotations

import unittest
from pathlib import Path

import yaml


class TestHousewireExamples(unittest.TestCase):
    def test_site_yaml_route21(self) -> None:
        try:
            from housewire_examples import iter_site_names, site_yaml
        except ImportError as exc:
            raise unittest.SkipTest(
                "housewire-examples not installed "
                "(pip install -e packages/housewire-examples)"
            ) from exc

        names = iter_site_names()
        self.assertIn("Route_21", names)
        path = site_yaml("Route_21")
        self.assertTrue(path.is_file(), msg=path)
        text = path.read_text(encoding="utf-8")
        self.assertIn("schema: house/v2", text)
        self.assertIn("Route 21", text)

    def test_all_bundled_sites_are_valid_yaml(self) -> None:
        """Every packaged Route_*.yaml must parse (File → Open loads them)."""
        sites = (
            Path(__file__).resolve().parents[1]
            / "packages"
            / "housewire-examples"
            / "src"
            / "housewire_examples"
            / "sites"
        )
        if not sites.is_dir():
            raise unittest.SkipTest("housewire-examples sites dir missing")
        files = sorted(sites.glob("Route_*.yaml"))
        self.assertTrue(files, msg=f"no Route_*.yaml under {sites}")
        for path in files:
            with self.subTest(site=path.name):
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
                self.assertIsInstance(data, dict, msg=path.name)
                self.assertEqual(data.get("schema"), "house/v2", msg=path.name)


if __name__ == "__main__":
    unittest.main()
