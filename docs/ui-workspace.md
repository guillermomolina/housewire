# UI workspace model

housewire’s interactive UI is heading toward a multi-document editor, but the
**file** unit and the **view** unit stay separate.

## Document = site

A **document** is one complete site directory:

- `$SITE/<name>.yaml` or `$SITE/<name>.yml` (any filename; nested places under
  `elements:`). New sites still default to `housewire.yaml`.
- optional `$SITE/catalog/` overlay
- optional `$SITE/out/` (generated; not part of the editable document identity)

If several YAML files sit at the site root and none is `housewire.yaml` /
`housewire.yml`, open the specific file (not only the directory).

There is a **File** menu for whole documents (Open site / Save / Save as / Close).
View tabs are separate (canvas locations inside the open site).

| Action | Meaning |
|--------|---------|
| Open site… | Native OS file dialog for a `.yaml`/`.yml` (fallback: path modal; Ctrl+O) |
| Save | Persist dirty buffers (Ctrl+S; also toolbar) |
| Save as… | Native OS save dialog for the new site folder path; then duplicate and open |
| Close | Drop the document (prompt if dirty) |

**Why not the browser file picker?** A normal browser cannot give the server a
real filesystem path. Because `housewire serve` runs locally, Open / Save as use
a **system** dialog (`zenity`, `kdialog`, or Python `tkinter`) on the server
process. If none is available, the UI falls back to typing an absolute path.

**Not yet:** New site, Export. Changing canvas location / depth / Elements is **View**, not File.

## Tabs = views

**View tabs** open locations (canvas roots) **inside** the active document — like
Figma pages, not like separate Atom files.

- Opening `Parking` and `Planta_baja` as tabs = two views of the same YAML.
- Opening another site = another **document** (future multi-doc workspace).

```text
Workspace
  └── Document (site A)
        ├── View tab: Parking
        └── View tab: Planta_baja
```

## API surface

- `GET /api/workspace` — active document path, dirty flag, `dialogs.native`
- `POST /api/workspace/open` — `{ "path": "…" }` or `{ "dialog": true }` to pick
  a site YAML / directory
- `POST /api/workspace/close` — unload active document (optional `{ "force": true }`)
- `POST /api/workspace/save-as` — `{ "path": "…" }` or `{ "dialog": true }`
- `POST /api/save` — save active document (unchanged)

Server process may start with one site (`housewire serve $SITE`); Open/Close/Save As
mutate the in-process workspace.
