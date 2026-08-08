"""Workspace / multi-document API (one YAML file per tab)."""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from tests.unit.fixtures import add_place, init_site, save_site
from housewire.site.io import load_yaml, save_yaml
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
            self.assertEqual(len(ws.status()["documents"]), 1)

            dest = Path(tmp) / "site_b"
            ws.save_as(dest)
            self.assertEqual(ws.require_root(), dest.resolve())
            self.assertTrue((dest / "housewire.yaml").is_file())
            # Save as opens a new tab; original stays open.
            self.assertEqual(len(ws.status()["documents"]), 2)

            ws.close(force=True)
            self.assertEqual(len(ws.status()["documents"]), 1)
            ws.close(force=True)
            self.assertIsNone(ws.document)

            ws.open_site(root)
            self.assertEqual(ws.status()["document"]["name"], "site_a")

            path, live = ws.require_session().ensure_doc()
            live["notes"] = "dirty"
            ws.require_session().mark_dirty(path)
            # Opening another site adds a tab; does not discard the dirty one.
            ws.open_site(dest)
            self.assertEqual(ws.status()["document"]["name"], "site_b")
            self.assertEqual(len(ws.status()["documents"]), 2)

            blank = ws.new_site(label="Blank", locale="en")
            self.assertTrue(blank.browser_origin)
            self.assertEqual(blank.yaml_path.name, "Blank.yaml")
            self.assertEqual(blank.title, "Blank.yaml")
            self.assertTrue(blank.force_dirty)
            self.assertEqual(len(ws.status()["documents"]), 3)
            self.assertTrue(ws.status()["dirty"])
            es = ws.new_site(locale="es")
            self.assertEqual(es.yaml_path.name, "NuevoSitio.yaml")
            self.assertEqual(es.title, "NuevoSitio.yaml")
            self.assertTrue(es.force_dirty)
            self.assertTrue(ws.status()["document"]["dirty"])
            _, es_doc = es.session.ensure_doc()
            self.assertEqual(es_doc.get("name"), "Nuevo sitio")
            self.assertEqual(es_doc.get("label"), "Nuevo sitio")
            # Sticky dirty survives reconcile against the temp file on disk.
            es.session.reconcile_dirty(es.yaml_path)
            self.assertTrue(ws.status()["document"]["dirty"])
            ws.clear_force_dirty()
            self.assertFalse(ws.status()["document"]["dirty"])

    def test_save_as_file_and_reopen_same_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "site_a"
            root.mkdir()
            save_site(root, init_site(root, type_id="House", label="Site A"))
            ws = create_workspace(root)
            path, live = ws.require_session().ensure_doc()
            live["notes"] = "from-save-as-file"
            ws.require_session().mark_dirty(path)

            dest = Path(tmp) / "copies" / "plan.yaml"
            doc = ws.save_as_file(dest)
            self.assertFalse(doc.browser_origin)
            self.assertEqual(doc.yaml_path.resolve(), dest.resolve())
            self.assertTrue(dest.is_file())
            self.assertIn("from-save-as-file", dest.read_text(encoding="utf-8"))
            # Original site tab stays open; new file is another tab.
            self.assertEqual(len(ws.status()["documents"]), 2)

            # Opening the same path again activates, does not duplicate.
            again = ws.open_site(dest)
            self.assertEqual(again.id, doc.id)
            self.assertEqual(len(ws.status()["documents"]), 2)

            # Save As from a browser-origin (New) tab closes the temp tab.
            created = ws.new_site(locale="en")
            self.assertTrue(created.browser_origin)
            temp_id = created.id
            n_before = len(ws.status()["documents"])
            out = Path(tmp) / "from_new.yaml"
            saved = ws.save_as_file(out)
            self.assertFalse(saved.browser_origin)
            self.assertNotIn(temp_id, ws.documents)
            self.assertEqual(len(ws.status()["documents"]), n_before)
            self.assertEqual(ws.status()["document"]["yaml"], "from_new.yaml")

    def test_reload_active_discards_dirty_and_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "site"
            root.mkdir()
            save_site(root, init_site(root, type_id="House", label="Site"))
            ws = create_workspace(root)
            path, live = ws.require_session().ensure_doc()
            live["notes"] = "in-memory"
            ws.require_session().commit_edit(path)
            ws.require_session().mark_dirty(path)
            self.assertTrue(ws.status()["document"]["dirty"])
            self.assertTrue(ws.status()["can_undo"])

            # Mutate on disk independently.
            disk = load_yaml(path)
            disk["notes"] = "from-disk"
            save_yaml(path, disk, backup=False)

            ws.reload_active()
            st = ws.status()
            self.assertFalse(st["document"]["dirty"])
            self.assertFalse(st["can_undo"])
            self.assertFalse(st["can_redo"])
            _, doc = ws.require_session().ensure_doc()
            self.assertEqual(doc.get("notes"), "from-disk")

    def test_empty_workspace(self) -> None:
        ws = create_workspace(None)
        self.assertIsNone(ws.document)
        self.assertEqual(ws.status()["documents"], [])
        self.assertIsNone(ws.status()["document"])

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

    def test_activate_and_close_by_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / "a"
            b = Path(tmp) / "b"
            a.mkdir()
            b.mkdir()
            save_site(a, init_site(a, type_id="House", label="A"))
            save_site(b, init_site(b, type_id="House", label="B"))
            ws = create_workspace(a)
            ws.open_site(b)
            self.assertEqual(ws.status()["document"]["name"], "b")
            id_a = next(
                d["id"] for d in ws.status()["documents"] if d["name"] == "a"
            )
            ws.activate(id_a)
            self.assertEqual(ws.status()["document"]["name"], "a")
            ws.close(force=True, doc_id=id_a)
            self.assertEqual(ws.status()["document"]["name"], "b")
            self.assertEqual(len(ws.status()["documents"]), 1)


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
            self.assertEqual(len(st["documents"]), 1)

            dest = Path(tmp) / "site_b"
            saved = client.post(
                "/api/workspace/save-as", json={"path": str(dest)}
            ).json()
            self.assertEqual(saved["document"]["name"], "site_b")
            self.assertTrue((dest / "housewire.yaml").is_file())
            self.assertEqual(len(saved["documents"]), 2)

            closed = client.post(
                "/api/workspace/close", json={"force": True}
            ).json()
            self.assertEqual(len(closed["documents"]), 1)
            client.post("/api/workspace/close", json={"force": True})

            again = client.post(
                "/api/workspace/open", json={"path": str(root)}
            ).json()
            self.assertEqual(again["document"]["name"], "site_a")

            client.patch(
                "/api/physical/page",
                json={"location_id": ".", "representation": "Tube"},
            )
            # Dirty active + open another = two tabs (no 409).
            opened_b = client.post(
                "/api/workspace/open", json={"path": str(dest)}
            )
            self.assertEqual(opened_b.status_code, 200)
            self.assertEqual(opened_b.json()["document"]["name"], "site_b")
            self.assertEqual(len(opened_b.json()["documents"]), 2)

            id_a = next(
                d["id"]
                for d in opened_b.json()["documents"]
                if d["name"] == "site_a"
            )
            act = client.post(
                "/api/workspace/activate", json={"id": id_a}
            ).json()
            self.assertEqual(act["document"]["name"], "site_a")

            # Open by YAML file path (custom name)
            custom_root = Path(tmp) / "named"
            custom_root.mkdir()
            cdoc = init_site(custom_root, type_id="House", label="N")
            save_site(custom_root, cdoc)
            named = custom_root / "plan.yaml"
            shutil.move(str(custom_root / "housewire.yaml"), str(named))
            opened = client.post(
                "/api/workspace/open",
                json={"path": str(named)},
            )
            self.assertEqual(opened.status_code, 200)
            self.assertEqual(opened.json()["document"]["yaml"], "plan.yaml")

            content = named.read_text(encoding="utf-8")
            via_content = client.post(
                "/api/workspace/open-content",
                json={
                    "filename": "from_browser.yml",
                    "content": content,
                },
            )
            self.assertEqual(via_content.status_code, 200)
            body = via_content.json()
            self.assertEqual(body["document"]["yaml"], "from_browser.yml")
            self.assertTrue(body["document"]["browser_origin"])
            exported = client.get("/api/workspace/yaml").json()
            self.assertEqual(exported["filename"], "from_browser.yml")
            self.assertIn("schema:", exported["content"])

            # New empty site tab (no picker)
            created = client.post(
                "/api/workspace/new", json={"locale": "es"}
            )
            self.assertEqual(created.status_code, 200)
            new_body = created.json()
            self.assertEqual(new_body["document"]["yaml"], "NuevoSitio.yaml")
            self.assertEqual(new_body["document"]["title"], "NuevoSitio.yaml")
            self.assertTrue(new_body["document"]["browser_origin"])
            self.assertTrue(new_body["dirty"])
            self.assertTrue(new_body["document"]["dirty"])
            yaml_text = client.get("/api/workspace/yaml").json()["content"]
            self.assertIn("type: House", yaml_text)
            self.assertIn("name: Nuevo sitio", yaml_text)
            self.assertIn("label: Nuevo sitio", yaml_text)
            outline = client.get("/api/outline").json()["nodes"]
            root_row = next(n for n in outline if n["id"] == ".")
            self.assertTrue(root_row.get("selectable"))
            place = client.get("/api/place", params={"location": ".", "id": "."})
            self.assertEqual(place.status_code, 200, place.text)
            self.assertEqual(place.json().get("type"), "House")

    def test_save_as_file_api_and_empty_serve(self) -> None:
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            self.skipTest("fastapi not installed")

        from housewire.ui.app import create_app

        empty = TestClient(create_app(None))
        st = empty.get("/api/workspace").json()
        self.assertIsNone(st["document"])
        self.assertEqual(st["documents"], [])
        about = empty.get("/api/about").json()
        self.assertEqual(about.get("runtime"), "server")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "site"
            root.mkdir()
            save_site(root, init_site(root, type_id="House", label="S"))
            client = TestClient(create_app(root))
            created = client.post("/api/workspace/new", json={"locale": "en"})
            self.assertEqual(created.status_code, 200)
            dest = Path(tmp) / "out" / "saved.yaml"
            saved = client.post(
                "/api/workspace/save-as-file",
                json={"path": str(dest)},
            )
            self.assertEqual(saved.status_code, 200, saved.text)
            body = saved.json()
            self.assertEqual(body["document"]["yaml"], "saved.yaml")
            self.assertFalse(body["document"]["browser_origin"])
            self.assertTrue(dest.is_file())
            # Re-open same path activates existing tab.
            again = client.post(
                "/api/workspace/open", json={"path": str(dest)}
            ).json()
            self.assertEqual(again["document"]["id"], body["document"]["id"])


if __name__ == "__main__":
    unittest.main()
