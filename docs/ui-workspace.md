# UI workspace model

## Document = site YAML (one file per tab)

A **document** is one site YAML (any ``.yaml`` / ``.yml`` name) plus the site
directory around it when known:

- editable YAML with nested places under `elements:`
- optional `$SITE/catalog/` overlay (when opened from a real site path)
- optional `$SITE/out/` (generated; not part of the editable document identity)

New sites still default to `housewire.yaml`.

**Tabs = open files.** Each tab is one document. File → Open adds another tab
(or activates it if that YAML is already open). The tab × closes that file.

Canvas location (which place is drawn) is chosen from the **Outline**, not from
tabs. The last location/depth per open file is remembered while switching tabs.

| Action | Meaning |
|--------|---------|
| Open… | Browser/OS file picker; opens a new document tab (Ctrl+O) |
| Save | Persist the **active** document |
| Save as… | Browser/OS save picker; opens the copy as another tab |
| Close / tab × | Close that document (prompt if dirty) |

```text
Workspace
  ├── Tab: housewire.yaml   ← active
  └── Tab: other-site.yml
        └── canvas location via Outline (e.g. Parking)
```

## API surface

- `GET /api/workspace` — `{ documents, active, document, dirty }`
- `POST /api/workspace/open` — `{ "path": "…" }` open/activate from server FS
- `POST /api/workspace/open-content` — `{ "filename", "content" }` new tab from picker
- `POST /api/workspace/activate` — `{ "id": "…" }` switch active tab
- `GET /api/workspace/yaml` — current YAML text for Save as
- `POST /api/workspace/close` — `{ "id"?, "force"? }` close one tab (active if omitted)
- `POST /api/workspace/save-as` — `{ "path": "…" }` duplicate site tree as a new tab
- `POST /api/save` — save active document; returns YAML text for client write-back

`housewire serve $SITE` may start with one site on disk; File → Open adds more
tabs beside it.
