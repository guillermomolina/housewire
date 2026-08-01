# UI workspace model

housewire’s interactive UI is heading toward a multi-document editor, but the
**file** unit and the **view** unit stay separate.

## Document = site

A **document** is one complete site directory:

- `$SITE/housewire.yaml` (nested places under `elements:`)
- optional `$SITE/catalog/` overlay
- optional `$SITE/out/` (generated; not part of the editable document identity)

There is a **File** menu for whole documents (Open site / Save / Save as / Close).
View tabs are separate (canvas locations inside the open site).

| Action | Meaning |
|--------|---------|
| Open site… | Another `$SITE` path (modal; Ctrl+O) |
| Save | Persist dirty buffers (Ctrl+S; also toolbar) |
| Save as… | Duplicate the site tree to a new path and open it |
| Close | Drop the document (prompt if dirty) |

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

- `GET /api/workspace` — active document path, dirty flag, open view hints
- `POST /api/workspace/open` — `{ "path": "…" }` switch/load a site document
- `POST /api/workspace/close` — unload active document (optional `{ "force": true }`)
- `POST /api/workspace/save-as` — `{ "path": "…" }` duplicate site and open copy
- `POST /api/save` — save active document (unchanged)

Server process may start with one site (`housewire serve $SITE`); Open/Close/Save As
mutate the in-process workspace.
