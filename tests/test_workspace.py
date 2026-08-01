"""Workspace / document API (site = document; views are client-side)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fixtures import add_place, init_site, save_site
from housewire.ui.workspace import create_workspace


class TestWorkspaceUnit(unittest.TestCase):
    def test_open_close_save_as_unit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "site_a"
            root.mkdir()
            doc = init_site(root, type_id="House", label="Site A")
            add_place(doc, "Parking", type_id="Floor", label="Parking")
            save_site(root, doc)

            ws = create_workspace(root)
            self.assertEqual(ws.status()["document"]["name"], "site_a")

            dest = Path(tmp) / "site_b"
            ws.save_as(dest)
            self.assertEqual(ws.require_root(), dest.resolve())
            self.assertTrue((dest / "housewire.yaml").is_file())

            ws.close(force=True)
            self.assertIsNone(ws.document)

            ws.open_site(root)
            self.assertEqual(ws.status()["document"]["name"], "site_a")

            path, live = ws.require_session().ensure_doc()
            live["notes"] = "dirty"
            ws.require_session().mark_dirty(path)
            with self.assertRaises(ValueError):
                ws.open_site(dest)
            ws.open_site(dest, force=True)
            self.assertEqual(ws.status()["document"]["name"], "site_b")


class TestWorkspaceApi(unittest.TestCase):
    def test_open_close_save_as(self) -> None:
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            self.skipTest("fastapi not installed")

        from housewire.ui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "site_a"
            root.mkdir()
            doc = init_site(root, type_id="House", label="Site A")
            add_place(doc, "Parking", type_id="Floor", label="Parking")
            add_place(
                doc,
                "Box_1",
                under=["Parking"],
                type_id="JunctionBox",
                label="Box 1",
            )
            save_site(root, doc)

            client = TestClient(create_app(root))
            st = client.get("/api/workspace").json()
            self.assertEqual(st["document"]["name"], "site_a")
            self.assertEqual(st["dirty"], [])

            dest = Path(tmp) / "site_b"
            saved = client.post(
                "/api/workspace/save-as", json={"path": str(dest)}
            ).json()
            self.assertEqual(saved["document"]["name"], "site_b")
            self.assertTrue((dest / "housewire.yaml").is_file())

            closed = client.post(
                "/api/workspace/close", json={"force": True}
            ).json()
            self.assertIsNone(closed["document"])

            again = client.post(
                "/api/workspace/open", json={"path": str(root)}
            ).json()
            self.assertEqual(again["document"]["name"], "site_a")

            client.patch(
                "/api/physical/page",
                json={"location_id": ".", "representation": "tube"},
            )
            blocked = client.post(
                "/api/workspace/open", json={"path": str(dest)}
            )
            self.assertEqual(blocked.status_code, 409)
            forced = client.post(
                "/api/workspace/open",
                json={"path": str(dest), "force": True},
            )
            self.assertEqual(forced.status_code, 200)
            self.assertEqual(forced.json()["document"]["name"], "site_b")


if __name__ == "__main__":
    unittest.main()
