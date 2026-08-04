"""Locale helpers and catalog label_es."""

from __future__ import annotations

import unittest

from fixtures import add_place
from housewire.house import catalog_type_description, catalog_type_label
from housewire.i18n import about_description_for, normalize_locale, unlabeled_for, unnamed_for
from housewire.site import abm
from housewire.site.clipboard import pack_selection, paste_payload
from housewire.site.tree import get_place_node
from tests.helpers import make_site


class TestNormalizeLocale(unittest.TestCase):
    def test_primary_tags(self) -> None:
        self.assertEqual(normalize_locale("en"), "en")
        self.assertEqual(normalize_locale("es"), "es")
        self.assertEqual(normalize_locale("ES-es"), "es")
        self.assertEqual(normalize_locale("en-US"), "en")

    def test_fallback(self) -> None:
        self.assertEqual(normalize_locale(None), "en")
        self.assertEqual(normalize_locale(""), "en")
        self.assertEqual(normalize_locale("fr"), "en")


class TestPastePlaceholders(unittest.TestCase):
    def test_unnamed_unlabeled(self) -> None:
        self.assertEqual(unnamed_for("en"), "Unnamed")
        self.assertEqual(unlabeled_for("en"), "Unlabeled")
        self.assertEqual(unnamed_for("es"), "Sin nombre")
        self.assertEqual(unlabeled_for("es"), "Sin etiqueta")

    def test_about_description(self) -> None:
        en = about_description_for("en")
        es = about_description_for("es")
        self.assertIn("YAML", en)
        self.assertIn("house/v2", en)
        self.assertIn("YAML", es)
        self.assertIn("lienzo", es)


class TestCatalogTypeLabelLocale(unittest.TestCase):
    def test_spanish_label_es(self) -> None:
        en = catalog_type_label("Room", locale="en")
        es = catalog_type_label("Room", locale="es")
        self.assertEqual(en, "Room")
        self.assertEqual(es, "Habitación")

    def test_spanish_description_es(self) -> None:
        en = catalog_type_description("MCB", locale="en")
        es = catalog_type_description("MCB", locale="es")
        self.assertIn("Miniature circuit breaker", en)
        self.assertIn("Magnetotérmico", es)
        self.assertIn("diferencial", es)


class TestClipboardLocale(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp, self.root, self.yaml = make_site()
        self.doc = abm.load_editable(self.yaml, self.root)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_paste_spanish_placeholders(self) -> None:
        add_place(self.doc, "Room", type_id="Room")
        add_place(self.doc, "Box", under=("Room",), type_id="JunctionBox")
        payload = pack_selection(self.doc, ["Room/Box"])
        paste_payload(
            self.doc, parent_id="Room", payload=payload, mode="copy", locale="es"
        )
        room = get_place_node(self.doc, ("Room",))
        elements = room.get("elements") or {}
        self.assertEqual(elements["Box_1"].get("name"), "Sin nombre")
        self.assertEqual(elements["Box_1"].get("label"), "Sin etiqueta")


if __name__ == "__main__":
    unittest.main()
