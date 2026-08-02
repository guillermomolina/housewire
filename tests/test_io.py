"""Tests for site.io."""
from __future__ import annotations

import unittest

from housewire.site.io import (
    create_empty_house_file,
    load_yaml,
    require_house_document,
    save_yaml,
)
from tests.helpers import make_site


# ---------------------------------------------------------------------------
# io.py
# ---------------------------------------------------------------------------

class TestIO(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp, self.root, self.yaml = make_site()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_create_empty_file_has_schema(self) -> None:
        doc = load_yaml(self.yaml)
        self.assertEqual(doc.get("schema"), "house/v2")
        self.assertIsInstance(doc.get("elements"), dict)
        self.assertIsInstance(doc.get("cables"), dict)
        self.assertIsInstance(doc.get("cables"), dict)

    def test_create_empty_file_already_exists_raises(self) -> None:
        with self.assertRaises(FileExistsError):
            create_empty_house_file(self.yaml)

    def test_save_yaml_creates_backup(self) -> None:
        doc = load_yaml(self.yaml)
        save_yaml(self.yaml, doc, backup=True)
        backup = self.yaml.with_suffix(self.yaml.suffix + ".bak")
        self.assertTrue(backup.exists())

    def test_save_yaml_no_backup(self) -> None:
        doc = load_yaml(self.yaml)
        save_yaml(self.yaml, doc, backup=False)
        backup = self.yaml.with_suffix(self.yaml.suffix + ".bak")
        self.assertFalse(backup.exists())

    def test_require_house_document_passes(self) -> None:
        doc = load_yaml(self.yaml)
        require_house_document(doc)

    def test_require_house_document_fails_on_legacy(self) -> None:
        with self.assertRaises(ValueError):
            require_house_document({"connectors": {}, "cables": {}})
