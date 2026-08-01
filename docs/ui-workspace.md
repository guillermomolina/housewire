# UI workspace model

housewire’s interactive UI is heading toward a multi-document editor, but the
**file** unit and the **view** unit stay separate.

## Document = site YAML

A **document** is one site YAML (any ``.yaml`` / ``.yml`` name) plus the site
directory around it when known:

- editable YAML with nested places under `elements:`
- optional `$SITE/catalog/` overlay (when opened from a real site path, e.g.
  `housewire serve $SITE`)
- optional `$SITE/out/` (generated; not part of the editable document identity)

New sites still default to `housewire.yaml`.

There is a **File** menu for documents (Open / Save / Save as / Close).
View tabs are separate (canvas locations inside the open document).

| Action | Meaning |
|--------|---------|
| Open… | Browser/OS file picker for a `.yaml`/`.yml` (Ctrl+O) |
| Save | Persist dirty buffers; write back via File System Access when available |
| Save as… | Browser/OS save picker (or download) for the YAML |
| Close | Drop the document (prompt if dirty) |

Open/Save as use the same system file dialog you get from a web “Browse /
Examinar” control (`<input type="file">` or the File System Access API). No
typed paths and no server-side dialog helpers.

When the browser cannot write back to the original file (no File System Access
handle), Save may download a copy so you keep your changes.

**Not yet:** New site, Export. Changing canvas location / depth / Elements is **View**, not File.

## Tabs = views

**View tabs** open locations (canvas roots) **inside** the active document — like
Figma pages, not like separate Atom files.

- Closing a view tab removes that canvas location from the tab strip.
- Closing the **last** view tab closes the **document** (same as File → Close).

- Opening `Parking` and `Planta_baja` as tabs = two views of the same YAML.
- Opening another YAML = another **document** (future multi-doc workspace).

```text
Workspace
  └── Document (site A)
        ├── View tab: Parking
        └── View tab: Planta_baja
```

## API surface

- `GET /api/workspace` — active document path, dirty flag
- `POST /api/workspace/open` — `{ "path": "…" }` (server filesystem; used by serve)
- `POST /api/workspace/open-content` — `{ "filename", "content" }` from the browser picker
- `GET /api/workspace/yaml` — current YAML text for Save as
- `POST /api/workspace/close` — unload active document (optional `{ "force": true }`)
- `POST /api/workspace/save-as` — `{ "path": "…" }` duplicate site tree (API / tests)
- `POST /api/save` — save active document; returns YAML text for client write-back

`housewire serve $SITE` may start with one site on disk; File → Open replaces it
with a picked YAML (loaded into a server temp site, written back through the
browser handle when possible).
