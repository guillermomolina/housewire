"""Workspace / document API (site = document; views are client-side)."""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from fixtures import add_place, init_site, save_site
from housewire.project.io import load_yaml, save_yaml
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
            self.assertEqual(ws.status()["document"]["yaml"], "housewire.yaml")

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

    def test_open_custom_yaml_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "custom"
            root.mkdir()
            init_site(root, type_id="House", label="Custom")
            yaml_path = root / "housewire.yaml"
            custom = root / "instalacion.yml"
            shutil.move(str(yaml_path), str(custom))
            save_yaml(custom, load_yaml(custom), backup=False)

            ws = create_workspace(custom)
            st = ws.status()
            self.assertEqual(st["document"]["yaml"], "instalacion.yml")
            self.assertTrue(str(st["document"]["yaml_path"]).endswith("instalacion.yml"))

            ws2 = create_workspace(root)
            self.assertEqual(ws2.status()["document"]["yaml"], "instalacion.yml")


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

            # Open by YAML file path (custom name)
            custom_root = Path(tmp) / "named"
            custom_root.mkdir()
            cdoc = init_site(custom_root, type_id="House", label="N")
            save_site(custom_root, cdoc)
            named = custom_root / "plan.yaml"
            shutil.move(str(custom_root / "housewire.yaml"), str(named))
            opened = client.post(
                "/api/workspace/open",
                json={"path": str(named), "force": True},
            )
            self.assertEqual(opened.status_code, 200)
            self.assertEqual(opened.json()["document"]["yaml"], "plan.yaml")

            content = named.read_text(encoding="utf-8")
            via_content = client.post(
                "/api/workspace/open-content",
                json={
                    "filename": "from_browser.yml",
                    "content": content,
                    "force": True,
                },
            )
            self.assertEqual(via_content.status_code, 200)
            body = via_content.json()
            self.assertEqual(body["document"]["yaml"], "from_browser.yml")
            self.assertTrue(body["document"]["browser_origin"])
            exported = client.get("/api/workspace/yaml").json()
            self.assertEqual(exported["filename"], "from_browser.yml")
            self.assertIn("schema:", exported["content"])


if __name__ == "__main__":
    unittest.main()
