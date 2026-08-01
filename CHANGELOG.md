# Changelog

All notable changes to **housewire** are documented in this file.

Format inspired by [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.27.15] — 2026-08-01

### Changed

- Replace Diagram Physical/Electrical/Both with a single **Electrical**
  on/off toggle (elements + cables; off by default). Places and conduits
  always show.

## [0.27.14] — 2026-08-01

### Changed

- Place and element boxes show the catalog type icon before the type label.

## [0.27.13] — 2026-08-01

### Changed

- Replace Elements/Cables checkboxes with a **Diagram** control: Physical
  (places + conduits), Electrical (elements + cables), or Both.

## [0.27.12] — 2026-08-01

### Fixed

- Cable overlay rides the exact conduit path (on top of the tube) plus in-box
  tails, so cables stay visible and do not fork outside the tube.

## [0.27.11] — 2026-08-01

### Fixed

- Draw cable edges above conduits and elements so in-box tails are not covered
  by tube caps.

## [0.27.10] — 2026-08-01

### Changed

- Outline active row uses the same amber ``--selection`` as canvas selection.

## [0.27.9] — 2026-08-01

### Changed

- Conduits always draw as **tubes**; the Representation line/tube control is
  removed. Default ``views.physical.representation`` is ``tube``.
- Cable overlay only draws in-box tails (element↔opening); the tube shows the
  run between places, so cables no longer fan out beside or outside tubes.

## [0.27.8] — 2026-08-01

### Fixed

- Selected places/elements use amber ``--selection`` instead of the same green
  as cable edges.

## [0.27.7] — 2026-08-01

### Fixed

- In-box cable runs approach contour openings from an interior inset so the
  wire stays inside the place instead of traveling along the box border.

## [0.27.6] — 2026-08-01

### Fixed

- Orthogonal conduit routing avoids stacking on the same corridor: later edges
  prefer parallel lanes / alternate elbows when a candidate would overlap a
  prior segment (crossings are only a light penalty).

## [0.27.5] — 2026-08-01

### Fixed

- Cables join conduit openings on the box contour (element→opening without
  outward stubs) so they exit through the tube instead of latching onto it
  outside the box.
- Cables that ride through a chain of conduits (multi-hop ``contains``) follow
  that path; ``cable_edges`` include ``conduit_hops``. Intra-box connections
  still draw direct (no tube).

## [0.27.4] — 2026-08-01

### Fixed

- Orthogonal routing picks the Manhattan path with the fewest bends
  (then shortest length), rejects diagonals and 180° U-turns on the same
  corridor, and keeps exit stubs leaving the box outward.

## [0.27.3] — 2026-08-01

### Fixed

- Orthogonal C-detour: any route that reverses relative to the exit face
  (not only perfectly aligned opposite openings) offsets sideways instead of
  overlapping the outbound stub.

## [0.27.2] — 2026-08-01

### Fixed

- Unify Outline / Inspector panel title typography; keep the first outline
  row from sitting under the title bar.
- Orthogonal routing: opposite faces that would reverse on the same line
  (e.g. exit North then enter South) take a C-shaped detour instead of
  overlapping the outbound path.

## [0.27.1] — 2026-08-01

### Changed

- Unsaved-close uses an in-app dialog (Save / Discard / Cancel) instead of
  ``window.confirm``.

## [0.27.0] — 2026-08-01

### Changed

- **Breaking (UI):** tabs are **open files** (one YAML document per tab), not
  canvas location views. File → Open adds a tab; tab × closes that file.
  Canvas place is selected from the Outline. Multi-document workspace API:
  ``documents`` / ``active`` / ``POST /api/workspace/activate``.

## [0.26.2] — 2026-08-01

### Fixed

- Closing the last view tab (×) closes the document, same as File → Close.

## [0.26.1] — 2026-08-01

### Fixed

- After Close, Open no longer falsely warns about unsaved changes (layout
  dirty only counts while a document and canvas are active).
- File → Save as… / Close stay disabled when no document is open.

## [0.26.0] — 2026-08-01

### Changed

- UI chrome: **HouseWire** brand + logo on the menubar; Save only in File menu;
  full-width status bar at the bottom; Outline and Inspector collapse to the
  sides (state remembered in sessionStorage).

## [0.25.0] — 2026-08-01

### Changed

- File → Open / Save as use the **browser file picker** (OS dialog via
  ``<input type="file">`` / File System Access API). Removed server-side
  zenity/kdialog/tkinter dialogs and the path modal.
- After Close, layout dirty state is cleared so Open no longer falsely warns
  about unsaved changes.

### Added

- ``POST /api/workspace/open-content`` and ``GET /api/workspace/yaml`` for
  browser-picked YAML documents.

## [0.24.0] — 2026-08-01

### Changed

- Site document YAML may use **any** ``.yaml`` / ``.yml`` filename at the site
  root (not only ``housewire.yaml``). Open accepts a directory or a YAML file
  path. New sites still default to ``housewire.yaml``.
- File → Open / Save as prefer a **native OS dialog** via the local server
  (``zenity`` / ``kdialog`` / ``tkinter``); path modal is the fallback. Browser
  pickers cannot expose real paths to the API (see ``docs/ui-workspace.md``).

## [0.23.1] — 2026-08-01

### Fixed

- File menu opens and stays open (document click no longer closes it
  immediately); cache-bust static assets.

## [0.23.0] — 2026-08-01

### Added

- UI **workspace model**: a document is a full site; view tabs are canvas
  locations inside the active document (see ``docs/ui-workspace.md``).
  API: ``GET /api/workspace``, ``POST …/open|close|save-as``.
  **File** menu: Open site… / Save / Save as… / Close (Ctrl+O / Ctrl+S).
  Toolbar Save remains.

### Breaking

- **External type catalog.** Types are no longer shipped inside the package
  (``src/housewire/catalog/`` removed). Clone
  [housewire-catalog](https://github.com/guillermomolina/housewire-catalog) into
  ``catalogs/default``, or set ``HOUSEWIRE_CATALOG`` / ``--catalog``. Optional
  site field ``catalog:`` (name or path). ``$SITE/catalog/`` remains an overlay.
- **Single nested site YAML only.** A site is a directory with one
  ``housewire.yaml``; places nest under ``elements:`` (map key = id).
  Per-place subdirectories and multi-file outline trees are removed.
  Shell ``add location`` always nests; ``--dir`` / ``--inline`` are gone.
  ``create_location_index`` is replaced by ``create_site_document`` +
  ``create_inline_location``. Generate loads only the site-root YAML.

### Added

- Place fields **id** / **name** / **label** are distinct: nested map key is id;
  optional YAML ``name:`` (canvas); optional ``label:`` (human). Helpers
  ``place_name`` / ``place_label``. ``add location --name``.
- Physical UI **depth zoom** (``depth −`` / ``depth +``, or Alt+wheel): nested
  children appear inside their parent boxes. Independent of canvas zoom
  (``+`` / ``−`` / wheel). ``GET /api/physical?depth=N``.
- Physical UI layout **Undo** / **Redo** / **Reset** (positions only;
  Ctrl+Z / Ctrl+Y). Reset restores positions from the last **Save** (or
  location load if nothing was saved yet). Missing ``x``/``y`` are filled
  automatically on location load (marks dirty; **Save** enabled only when
  there are unsaved changes). Manual **Auto-layout** repositions all visible
  places. Canvas **Fit** frames all places in the viewport (also runs after
  load). After **Save**, only the Reset baseline moves to the saved positions
  (Reset greys out; undo/redo history is kept). Undo/redo back to the saved
  layout clears dirty and disables **Save**. Conduit edges use orthogonal
  (axis-aligned) elbows instead of diagonal segments.
- Physical UI **Elements** / **Cables** toggles (session LOD, like depth): show
  electrical elements inside places and connection edges on the same canvas.
  Element positions persist as ``view.electrical``; missing coords auto-fill on
  load. ``PATCH /api/electrical/positions``, ``POST /api/electrical/auto-layout``.
  Graph JSON includes ``elements`` and ``cable_edges``. Cables that ride in a
  conduit ``contains`` follow the conduit path (element→opening→tube→opening→
  element). Element boxes enlarge their host place like nested locations;
  Elements draw only inside leaf places in the current depth view.
- Physical UI left **Outline** tree (all places + elements). Click a place to
  switch the canvas view (or open the nearest canvas ancestor and select it);
  click an element to focus it (enables Elements if needed). ``GET /api/outline``.
  Collapsible branches (session-remembered); icons from catalog ``icon:``
  (site ``catalog/`` overlay + optional per-instance ``icon:``). Toolbar
  location dropdown removed (outline is the navigator). ``GET /api/catalog``.
  Outline opens only the first level by default; elements appear in the tree
  only when the Elements toggle is on. Orthogonal conduit/cable paths use
  S/Z mid elbows (not a single L corner).
- Physical UI **multi-select**: Ctrl/Cmd+click to toggle; Shift+drag a box on
  empty canvas to select everything inside (Ctrl/Cmd+Shift+box adds). Drag any
  selected item to move the whole selection together. Empty-canvas drag pans;
  middle mouse also pans. Wheel zoom anchors on the cursor.

### Fixed

- Physical UI depth changes no longer reset pan/zoom; Fit still runs when
  changing location.
- Physical UI inspector: **locations** list Elements + Conduits; **elements**
  list Cables (connection edges). Place detail API still returns both
  ``conduits`` and ``cables`` for reuse.
- Cables and conduits support optional YAML ``name:`` (short display) beside
  ``label:``; UI lists and tooltips prefer ``name`` → id.
- Physical UI draws each back/front opening (``B2-1``, …) on its face grid
  near the box border; conduit paths terminate at that circle.
- Elements support optional YAML ``name:`` like places/cables; UI prefers
  ``name`` → id (outline, canvas labels, inspector).

### Changed

- Physical canvas / location selector show ``name`` → id (not ``label``).
  Inspector lists id, name, and label separately.
- Physical UI location selector shows the outline **tree** (indented), not a
  flat list; defaults to the site **root** (``.``) when present.
- Physical canvas defaults to **direct** children (depth 1). Higher depth nests
  descendants inside parents instead of flattening them as siblings.

### Fixed

- Physical UI double-click enters a place (or deepens the view): drag no longer
  captures the pointer on ``pointerdown``, which had blocked dblclick.
- Physical UI depth zoom: nested conduit lines were hidden under opaque
  parent fills; draw containers → edges → leaves.
- Depth zoom uses window-style nesting: parent ``w``/``h`` is the bounding
  box of its full descendant layout (same whether interior is drawn), and
  children sit at natural size in parent-local coordinates. Inner padding
  leaves a margin so children do not touch the parent border; leaf width
  grows with the canvas name (ellipsis + tooltip with label if still too long).
- ``view.physical`` ``x``/``y`` must be ``>= 0`` (negatives rejected on write;
  ignored on read so layout defaults apply).

## [0.22.0] — 2026-08-01

### Added

- Place type ``Stair`` for vertical circulation linking two locations via
  ``connects: [A, B]`` (not a plain ``Room``).

## [0.21.0] — 2026-08-01

### Added

- Physical UI side panel: click a place for show-like detail; recipe forms
  for ``socket`` / ``lamp`` / ``feed`` (``POST /api/recipes/…``,
  ``GET /api/place``). Shared orchestration in ``project.recipe_actions``.
- Tube/line edge tooltips list conduit ``contains``.

### Fixed

- Physical UI drag: moving a box no longer freezes when crossing another node
  (live transform update instead of full SVG redraw each pointermove).
- Physical UI: conduit endpoints fan out along each face (``S1``/``S2``/…)
  instead of sharing one midpoint per side.

### Removed

- ``requirements.txt`` and ``dev-requirements.txt`` (use ``pip install -e '.[dev,ui]'``
  or ``make prepare`` / ``make install`` from ``pyproject.toml`` extras).

## [0.20.1] — 2026-08-01

### Changed

- Physical UI: canvas root is any location with children (``location_id``), not
  a Floor-only ``floor_id``. API ``/api/locations``, query ``location=…``.

## [0.20.0] — 2026-08-01

### Added

- Interactive physical floor UI: ``housewire serve SITE`` (optional extra
  ``housewire[ui]`` with FastAPI/uvicorn). Canvas for Floor places: drag
  components, auto-layout, ``line``/``tube`` conduit representation, zoom
  independent of representation. Persists ``view.physical`` on places and
  ``views.physical`` on floors.
- Schema helpers for canvas layout (``view.physical.x/y``, floor page size /
  representation).

## [0.19.3] — 2026-08-01

### Added

- Catalog ``Relay`` subtype ``mini_zbd`` (Sonoff MINI Zigbee Dry: ``L``, ``N``,
  ``NO``, ``COM``, ``NC``).

## [0.19.2] — 2026-08-01

### Changed

- Catalog ``Relay`` subtype ``zbmini_r2`` (Sonoff ZBMiniR2); ``zbmini_extreme``
  kept as legacy alias.

## [0.19.1] — 2026-07-31

### Added

- Catalog type ``Relay`` (smart switch / Zigbee relay) with terminals
  ``N``, ``LIn``, ``LOut``, ``S1``, ``S2`` and subtype ``zbmini_extreme``.

## [0.19.0] — 2026-07-31

### Added

- Open-ended runs: shell ``open`` / ``claim`` / ``land`` / ``opens`` for cables
  that leave a known opening toward an unknown far end (``OPEN_Linea_NN``), then
  attach conduit hops and finally electrical connections with rename.

## [0.18.0] — 2026-07-31

### Added

- Capture recipes in the shell: ``add socket``, ``add lamp``, and ``add feed``
  create place+element (socket/lamp) plus cable, conduit, and connection with
  sensible defaults (Schuko from strip ``[3,2,1]→[L,PE,N]``; LightPoint
  luminaire; strip-to-strip feed).

## [0.17.6] — 2026-07-31

### Changed

- Rewrote ``docs/schema-house-v1.md`` in English; removed obsolete/legacy notes;
  documented current place/element types (incl. ``Luminaire``, Switch subtypes),
  openings, color codes, and in-memory shell ``cd`` behavior.

## [0.17.5] — 2026-07-31

### Added

- Document IEC 60757 cable color codes (``BN``, ``BU``, ``GNYE``, …) in
  ``docs/schema-house-v1.md``.

## [0.17.4] — 2026-07-31

### Changed

- Shell ``cd`` no longer prompts to save/discard when leaving a dirty YAML; buffers
  stay in memory across locations. ``save`` writes all dirty files; ``exit`` still
  asks per dirty document. Prompt ``*`` means any dirty buffer in the session.

## [0.17.3] — 2026-07-31

### Added

- Catalog type ``Luminaire`` (lamp / pendant; terminals 1–3 by default).

## [0.17.2] — 2026-07-31

### Added

- ``Switch`` subtypes ``crossover`` (conmutador: C+1+2) and ``intermediate``;
  element catalog may override ``terminals`` / ``wireviz_collapse`` per subtype.

## [0.17.1] — 2026-07-31

### Fixed

- Shell ``add … --set KEY VALUE`` (two tokens) is accepted, not only
  ``--set KEY=VALUE`` — fixes stray argparse errors on ``--set notes "…"``.

## [0.17.0] — 2026-07-31

### Changed

- Program messages (CLI/shell help, banners, prompts, errors) are English-only;
  internationalization deferred.

## [0.16.15] — 2026-07-31

### Added

- Place type ``LightPoint`` (ceiling/wall light outlet / hole) for physical
  conduit ends; distinct style in the physical diagram. Docs: luminaires use
  ``LightPoint`` + openings (not DeviceBox / not bare elements).

## [0.16.14] — 2026-07-31

### Fixed

- Shell: join lines ending with ``\`` so multi-line paste/continuation works;
  hint when a line starts with ``--`` (orphan flag fragment).

## [0.16.13] — 2026-07-31

### Fixed

- Shell ``set``: re-join tokens so YAML values with spaces work
  (``set openings=[W1, S2, E1]``).

## [0.16.12] — 2026-07-31

### Added

- Shell/CLI: generic ``set`` / ``unset`` and ``--set KEY=VALUE`` on
  ``add location`` / ``add element`` (YAML-parsed values; nested ``a.b``;
  reserved structural keys blocked).

## [0.16.11] — 2026-07-31

### Added

- Catalog type ``Switch`` (mechanism switch; terminals 1→2 phase; default
  subtype ``unipolar``).

## [0.16.10] — 2026-07-31

### Changed

- Shell: outline ``add location`` stays in the dirty buffer until ``save``
  (mkdir + ``housewire.yaml`` on disk only then), same as inline locations and
  element/cable/conduit edits. CLI one-shot ``add location`` still writes
  immediately.

## [0.16.9] — 2026-07-31

### Fixed

- Shell messaging: outline ``add location`` writes to disk immediately (no
  ``save``); clarify banner vs in-memory edits (element/cable/conduit/…).

## [0.16.8] — 2026-07-31

### Added

- Shell / CLI: ``add conduit NAME --from A.Op --to B.Op --contains C1[,C2…]``.

## [0.16.7] — 2026-07-31

### Fixed

- Shell: letter ``b`` swallowed on GNU readline — only apply the libedit Tab
  bind on libedit, not on Linux GNU readline.

## [0.16.6] — 2026-07-31

### Changed

- Physical diagram styles locations by place type (House / Floor / Room /
  Panel / JunctionBox / DeviceBox) with distinct fills, borders, and shapes.

## [0.16.5] — 2026-07-31

### Changed

- Physical edges no longer pin Graphviz to YAML opening faces (W/S/…). Attach
  to the border facing the neighbor; real openings remain in the edge label.

## [0.16.4] — 2026-07-31

### Changed

- Physical layout: drop north-up geo-ordering; Graphviz places boxes freely.
- Edges use side ports + normal splines (not ortho) so lines clip at the
  node border instead of diving into the center.

## [0.16.3] — 2026-07-31

### Fixed

- Physical layout orients conduit edges north-up (northern box above) so N-S
  chains (e.g. Caja 2↔3) stay short instead of looping; undirected ortho edges.

## [0.16.2] — 2026-07-31

### Changed

- Physical edges attach to Graphviz compass ports from opening faces
  (N→top, S→bottom, W→left, E→right); layout `rankdir=TB`.

## [0.16.1] — 2026-07-31

### Fixed

- Physical diagram no longer draws each location twice (cluster + inner node).
  Containers are clusters only; leaves (conduit ends) are single nodes.

## [0.16.0] — 2026-07-31

### Changed

- Physical diagram nests location clusters (Floor ⊃ boxes), not flat sibling
  clusters; site root uses the project name (no bare `raiz`).
- Physical edge labels are conduit + openings only (no cable ids).
- WireViz output drops PNG (SVG/HTML/TSV only) to avoid cairo bitmap scaling.

## [0.15.0] — 2026-07-31

### Removed

- Conduit free-text **`route`** (require structured **`from` / `to`**).
- Place type **`Zone`** (use **`Floor`**).

## [0.14.0] — 2026-07-31

### Changed

- Clear **two-layer** model: physical = locations ↔ conduits; electrical =
  elements ↔ cables/connections.
- Conduits use structured **`from` / `to`** (`LocationRef.OpeningId`).
  `pend` writes `.N1` / `.S1` endpoints.
- Physical export draws **conduit edges between locations** (not connection
  edges between elements).

## [0.13.0] — 2026-07-31

### Added

- Place type **`Floor`** for building levels (ground floor, parking, …).

### Changed

- Prefer **`Floor`** for building levels.
- `generate` scopes to the given directory (CLI path or shell current location);
  dropped `--zones` / `--no-zones` and `out/zones/` multi-cut. Output is always
  WireViz + physical under `<scope>/out/`.

## [0.12.0] — 2026-07-31

### Added

- Place type **`DeviceBox`** for mechanism boxes (socket/switch; 1-/2-/3-gang).
- Optional place field **`install`**: `surface` | `flush` (docs).
- Docs: hanging luminaires terminate at the device element (no DeviceBox).

## [0.11.0] — 2026-07-31

### Changed

- Interactive shell keeps `housewire.yaml` **in memory**: edits mark dirty (`*`
  in the prompt); `save` / `reload` write or discard; `exit`/`quit`/EOF and
  `cd` across YAMLs prompt to save/discard/cancel.
- `generate` auto-saves dirty buffers first.
- One-shot CLI `add`/`rm` still load → mutate → persist in a single step.

## [0.10.0] — 2026-07-31

### Changed

- Shell `cd` / `ls` / `pwd` navigate the **logical location tree** (outline
  directories and inline places under `elements:`), not raw filesystem dirs.
- `ls` lists place-typed children as locations; non-place devices as elements.
- `add location` defaults to outline when the current place is outline, inline
  when already inside an inline place; `--inline` / `--dir` override
  (`--dir` under inline is rejected). Same id as both dir and inline is an error.
- Edits (`show`, `add element`/`cable`/…) apply to the current place node.

## [0.9.0] — 2026-07-31

### Changed

- Cables and conduits use **`type` / `subtype` / `label` / `notes`** like elements
  (still under their own `cables:` / `conduits:` maps).
- Catalog entries **`Cable`** (`cable_type`) and **`Conduit`** (`conduit_type`)
  supply section/colors and tube-size subtype defaults.
- Legacy `kind: power` and `kind: conduit` + `type: M20` still load.

## [0.8.0] — 2026-07-31

### Changed

- Breaking: the `housewire.yaml` **root is the place object** (`type`, `label`,
  `openings`, …). Nested places in `elements` use the same shape.
- Legacy nested `location: { … }` still loads; prefer root fields.

## [0.7.2] — 2026-07-31

### Changed

- Location / element **ids** are technical (`Caja_derivacion_4`); optional
  **`label`** is the human name. Applies to directory trees and inline nested
  locations in one YAML.
- `add location` with spaces creates a normalized folder id and sets
  `location.label` automatically (override with `--label`).
- Physical cluster title uses `location.label` when present.

## [0.7.1] — 2026-07-31

### Changed

- `opening_grid` pair key **`WE`** (W→E) instead of `EW`, matching `NS` order.

## [0.7.0] — 2026-07-31

### Changed

- Opening ids are local to the box (poker frame looking at **`F`**):
  contour `N1`/`S2`/…, back/front `B1-1`/`F2-3` (row N→S, col W→E).
- `location.openings` is a **list** of those ids (no `{B1: {face:…}}` map).
- Optional `location.opening_grid` with per-face / `NS`/`EW` specs; bare
  int means one row (`3` ≡ `3x1`).
- Faces **`F`/`B`** replace `lid`/`back` in the canonical vocabulary
  (legacy tokens still parsed in physical route text).

## [0.6.4] — 2026-07-30

### Changed

- Opening faces `fondo` / `tapa` renamed to English **`back`** / **`lid`**
  (legacy tokens still recognized in physical text).

## [0.6.3] — 2026-07-30

### Added

- Shell `show` lists `openings` as their own section (`B1 face=… index=…`).

## [0.6.2] — 2026-07-30

### Changed

- `location.openings` (`B1`, `B2`, …) also applies to **`Panel`**, not only
  `JunctionBox` (docs + catalog).

## [0.6.1] — 2026-07-30

### Added

- `housewire --version` / `-V`, subcommand `housewire version`, and shell
  command `version`.

## [0.6.0] — 2026-07-30

### Changed (breaking)

- Junction box openings use **local ids** (`B1`, `B2`, …) declared in
  `location.openings` with optional `face` / `index` and `mount` / `facing`.
- `pend` validates opening ids when `openings` is declared.
- Physical diagram recognizes `abertura B*`; legacy cardinals (`W.N`, …) still
  parse from old text.
- Docs and README use `B*` instead of `W.N` / `E.S`.

## [0.5.3] — 2026-07-30

### Changed

- Shell prompt is path-only (`project/cwd`); dropped the redundant
  `[…/housewire.yaml]` suffix and the “Activo (auto)” line on `cd`.

## [0.5.2] — 2026-07-30

### Changed

- Shell `ls` lists only child directories that have **`housewire.yaml`** (real
  locations). Bare path folders are skipped; `cd` into one prints a warning.

## [0.5.1] — 2026-07-30

### Changed

- Shell `ls` lists **locations** (cd targets) and **elements** of the current
  place; dropped filesystem `[d]`/`[f]` markers and `housewire.yaml` file rows.

## [0.5.0] — 2026-07-30

### Changed (breaking)

- Per-directory file renamed from **`index.yaml`** to **`housewire.yaml`**
  (also accepts `housewire.yml`).
- Place type **`Site`** renamed to **`House`** (dwelling; not a privileged root).
- Zone diagrams group by **top-level directory** under `project_path` (no
  hard-coded site layout). Root-level YAMLs form a zone named after the project
  directory. Remap by pointing `project_path` at another subtree or wrapping
  folders above.

### Migration

```bash
# in each location directory
mv index.yaml housewire.yaml
# if you used type: Site → type: House (optional; any place type may sit at root)
```

## [0.4.0] — 2026-07-30

### Changed (breaking)

- Connection `from` / `to` refs may only target the **declaring location and its
  sublocations** (child-relative paths such as `Caja 2/Regleta.1`).
- `../` (and any ref that leaves the current tree) is rejected; put the
  connection in a common ancestor instead.
- Absolute refs are still accepted only when they resolve inside the same tree.
- `via` must name a cable defined in the same location as the connection.

## [0.3.0] — 2026-07-30

### Changed (breaking)

- Renamed top-level **`self:`** to **`location:`** for per-directory place metadata.
- `location.type` is a place kind: **`Room`**, **`JunctionBox`**, **`Panel`**, **`Zone`**, **`Site`** (plus legacy **`Location`**).
- `location:` as a path **list** remains invalid; hierarchy is still the filesystem path only.
- `add location NAME` requires **`--type`**.
- Catalog place types (`Room`, `JunctionBox`, `Panel`, `Zone`, `Site`) with `wireviz_skip: true`.

### Migration

```yaml
# before
self:
  type: Location
  subtype: "100x100 IP40"

# after
location:
  type: JunctionBox   # or Room | Panel | Zone | Site
  subtype: "100x100 IP40"
```

## [0.2.2] — 2026-07-30

### Changed

- **One `index.yaml` per Location directory.** Generate/collect only `index.yaml` / `index.yml`; sibling fragment YAMLs are ignored.
- Shell `use` accepts only `index.yaml`; removed `add file` (use `add location` instead).
- Docs: no multi-file-per-directory layout.

### Added

- Confirmation that `add location` creates the directory and `index.yaml` with `self:`.

## [0.2.1] — 2026-07-30

### Changed

- Docs no longer reference any private site repository or concrete installation names.
- README treats site data as an external path (`$SITE`); local `projects/` remains gitignored only as an optional convenience.

## [0.2.0] — 2026-07-30

### Changed (breaking)

- **Locations = directories + `index.yaml`**. Hierarchy comes from the filesystem path, not a `location:` field.
- Per-directory metadata lives in a top-level **`self:`** block (`type: Location`, `subtype`, `notes`, …).
- The YAML **`location:`** field is no longer supported and raises if present.
- Shell is location-oriented: after `cd`, auto-activate **`index.yaml`** (preferred over “single yaml in cwd”).
- Bare `show` prints the Location `self:` plus a content summary for the current place.
- `ls` marks sublocations (`[loc]`) and `index.yaml` (`[index]`).
- Tab completion prefers directories and `index.yaml`.
- Existing site trees using the old stub + `location:` pattern must be migrated to directories + `index.yaml` (site repos are separate from this program).

### Added

- Shell command **`add location NAME`**: creates a folder + `index.yaml` with `self:`.
- IO helper `create_location_index`.
- Location model docs in `docs/schema-house-v1.md` and README.
- Tests for `self:`, rejection of `location:`, `index.yaml` auto-use, and `show` with `self`.

## [0.1.0] — 2026-07-30

First usable package and site shell.

### Added

- Schema **`house/v1`**: elements, cables, connections, conduits; catalog (MCB, RCD, Socket, TerminalStrip, Location, …).
- **WireViz** export (full + per zone) and **physical topology** diagrams.
- Interactive shell: `cd`, `ls`, `use`, `show`, `add`, `rm`, `generate`, `help`.
- Fast pending-cable capture: **`pend`** / `add pend` (`PEND_*` convention + pass-through conduit).
- Cable defaults (`1.5 mm2`, `BN,BU`) and auto-use when exactly one house YAML is in the cwd.
- **Tab** completion (commands, `add`/`rm` subcommands, paths).
- Documented convention for pending runs (through a box without a terminal strip splice).
- Split test modules; `dev-requirements.txt` with pytest; `make test`.

### Notes

- Before 0.2.0, some layouts used a parent `type: Location` stub plus sibling `location:`; that pattern is invalid now.

[Unreleased]: https://github.com/local/housewire/compare/v0.2.2...HEAD
[0.2.2]: https://github.com/local/housewire/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/local/housewire/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/local/housewire/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/local/housewire/releases/tag/v0.1.0
