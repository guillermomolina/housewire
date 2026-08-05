# UI workspace model

## Document = site YAML (one file per tab)

A **document** is one site YAML (any ``.yaml`` / ``.yml`` name) plus the site
directory around it when known:

- editable YAML with nested places under `elements:`
- optional `$SITE/catalog/` overlay (when opened from a real site path)
- optional leftover `$SITE/out/` directories (ignored; not part of the document)

New sites use a technical YAML stem from the localized label
(``NewSite.yaml`` / ``NuevoSitio.yaml``) with matching root ``name``/``label``.
The tab shows the filename (with ``.yaml``) and stays dirty until Save.

**Tabs = open files.** Each tab is one document. File → Open adds another tab
(or activates it if that YAML is already open). The tab × closes that file.

Canvas location (which place is drawn) is chosen from the **Outline**, not from
tabs. The last location/depth per open file is remembered while switching tabs.
**Depth** controls nested place expansion; **Electrical** toggles elements and
cables (and sets depth to max while on, restoring the prior depth when off).
The outline tree is filtered to match the current canvas depth and Electrical
state.

| Action | Meaning |
|--------|---------|
| New | Empty House site in a new dirty tab (Ctrl+N); localized title/filename; use Save as… to keep it |
| Open… | Browser/OS file picker; opens a new document tab (Ctrl+O) |
| Save | Persist the **active** document |
| Save as… | Browser/OS save picker; opens the copy as another tab |
| Close / tab × | Close that document (prompt if dirty) |
| Edit → Delete | Cascade-delete selected places/elements (`Del` / Backspace); cross-boundary cables become open runs |
| Edit → Cut / Copy / Paste | Clipboard (`Ctrl+X`/`C`/`V`); place clipboard nests into a selected destination place (siblings when the copy source stays selected); elements into a selected place (or original box) |
| Drag place onto place | Reparent into the drop target (`POST /api/edit/reparent`) |

```text
Workspace
  ├── Tab: my-site.yaml   ← active
  └── Tab: other-site.yml
        └── canvas location via Outline (e.g. Parking)
```

## API surface

- `GET /api/workspace` — `{ documents, active, document, dirty }`
- `POST /api/workspace/new` — optional `{ "type", "label" }`; empty House tab (temp)
- `POST /api/workspace/open` — `{ "path": "…" }` open/activate from server FS
- `POST /api/workspace/open-content` — `{ "filename", "content" }` new tab from picker
- `POST /api/workspace/activate` — `{ "id": "…" }` switch active tab
- `GET /api/workspace/yaml` — current YAML text for Save as
- `POST /api/workspace/close` — `{ "id"?, "force"? }` close one tab (active if omitted)
- `POST /api/workspace/save-as` — `{ "path": "…" }` duplicate site tree as a new tab
- `POST /api/save` — save active document; returns YAML text for client write-back
- `POST /api/edit/delete` — `{ "ids": ["Place/…"], "location_id"?, "depth"? }` cascade delete selection
- `POST /api/edit/copy` — `{ "ids": […] }` pack selection (no mutation)
- `POST /api/edit/cut` — pack + cascade delete (one undo)
- `POST /api/edit/paste` — `{ "parent_id", "payload", "location_id"?, "depth"? }`
- `POST /api/edit/reparent` — `{ "ids", "parent_id", "positions"?, "location_id"?, "depth"? }` move places into another place

`housewire serve $SITE` may start with one site on disk; File → New / Open adds more
tabs beside it.
