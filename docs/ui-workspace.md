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
state. When the canvas is **inside** a place (Outline → selectable box), the
outline shows a **breadcrumb** from site root (``.``) to that location (click
any segment to go up) plus places and elements **under** the current location
only—not siblings at ancestor levels. Moving **up** the breadcrumb adds one
to depth per level (keeping Electrical as set); entering a container still
resets depth to 1 for that view.

**Chrome layout:** the **app header** groups logo, menu bar, and open-file
**tabs** on one row; the toolbar holds file and edit actions; depth,
Electrical, fit, and zoom sit on the status strip under the canvas.

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
- `POST /api/workspace/save-as-file` — `{ "path": "…" }` write active YAML buffer to a
  file path and open it (Electron / path-aware clients; closes a prior
  browser-origin temp tab when applicable)
- `POST /api/save` — save active document; returns YAML text for client write-back
- `POST /api/edit/delete` — `{ "ids": ["Place/…"], "location_id"?, "depth"? }` cascade delete selection
- `POST /api/edit/copy` — `{ "ids": […] }` pack selection (no mutation)
- `POST /api/edit/cut` — pack + cascade delete (one undo)
- `POST /api/edit/paste` — `{ "parent_id", "payload", "location_id"?, "depth"? }`
- `POST /api/edit/reparent` — `{ "ids", "parent_id", "positions"?, "location_id"?, "depth"? }` move places into another place

`housewire serve` may start with an empty workspace (no site argument) or with
`$SITE` already open. File → New / Open adds more tabs beside it.

## Web vs desktop (Electron)

| | Web (`housewire serve`) | Desktop (`desktop/` Electron shell) |
|--|-------------------------|-------------------------------------|
| Open | Browser picker → `open-content` (temp site + optional File System Access handle) | Native dialog → absolute path → `POST /workspace/open` |
| Save | Handle write-back + `/api/save`, or Save As if no target; serve-opened sites save via `/api/save` | `/api/save` to the real path when `browser_origin` is false |
| Save As | Picker/download + `open-content` | Native dialog → `POST /workspace/save-as-file` |
| Path in UI | Temp path (or filename only) | Real `yaml_path` from the server |

Desktop uses a **system** Electron binary (`electron` on `PATH`, e.g. Arch
`pacman -S electron`). The UI detects desktop mode when `window.housewireDesktop`
is present (preload bridge). Help → About shows `desktop` or `server` next to
the version. `GET /api/about` includes `"runtime": "server"`; the client labels
desktop when the bridge is available.
