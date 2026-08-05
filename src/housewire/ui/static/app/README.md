# UI app fragments

`app.js` is generated from these files (one IIFE, classic `<script>` load).

| File | Domain |
|------|--------|
| `01-core.js` | State, API, documents, selection, layout helpers |
| `02-openings.js` | Opening marks, mouths, mirrors, edge-refresh scheduling |
| `03-routing.js` | Ortho routing, lanes, cable layout, tube/cable helpers |
| `04-render.js` | Paint, progressive render, inspectors, electrical |
| `05-shell.js` | Zoom, tabs, menus, palette, boot |

After editing a fragment:

```bash
python scripts/bundle_ui_app.py
# or: make bundle-ui
```

Do not edit `../app.js` by hand.
