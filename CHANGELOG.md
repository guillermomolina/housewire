# Changelog

All notable changes to **HouseWire** are documented in this file.

Format inspired by [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.94.1] — 2026-08-08

### Fixed

- Se localizan las etiquetas de color, sección, origen, destino y contenido
  en el panel de propiedades de conexiones.

## [0.94.0] — 2026-08-08

### Added

- La paleta agrupa Conduit, Cable y Conductor en Conexiones, mostrando el tipo
  inglés junto a cada etiqueta localizada.
- Los cables se pueden agrupar y desagrupar; los cables anidados se muestran
  con sus cables y conductores en capas separadas.

### Changed

- La API de conexiones usa `/api/connection/...` para Conduit, Cable y
  Conductor.
- La selección para crear un Cable usa clic, Ctrl/Cmd y rectángulo con Shift,
  igual que la selección normal.
- Se aumenta la separación visual y se limita el área de clic de cables y
  conductores a su carril.

### Fixed

- Un Conduit no puede contener otro Conduit; un Cable solo puede contener
  Cables y Conductores.

## [0.93.1] — 2026-08-08

### Fixed

- Una funda con conductores que terminan en pares de elementos distintos se
  dibuja como un único cable que envuelve todos sus conductores en el conduit.

## [0.93.0] — 2026-08-08

### Added

- `housewire serve` registra en un archivo rotativo configurable mediante
  `--log-level` y `--log-file`.

### Changed

- Los avisos y errores de la API se muestran en un diálogo, reservando la barra
  de estado para mensajes informativos.

### Fixed

- No se pueden borrar tubos o cables contenedores mientras tengan conexiones
  contenidas.

## [0.92.0] — 2026-08-08

### Added

- La creación de cables agrupa conductores con el mismo recorrido ordenado de
  conduits, los resalta con línea discontinua y permite confirmar con `Enter`,
  cancelar con `Escape` o retirar el último con `Backspace`.

### Fixed

- Las rutas B↔B prueban desvíos U compactos por sus cajas de extremo antes del
  fallback de contorno, evitando seis segmentos en Route_28.

## [0.91.1] — 2026-08-08

### Fixed

- Guardar en documentos web sin destino solicita el nombre en un diálogo propio.
  Guardar como abre el selector nativo y ambos reemplazan la pestaña actual
  sin modificar la vista, profundidad ni capa eléctrica.

## [0.91.0] — 2026-08-08

### Added

- El trazado de conductores permite recorrer conduits entre contenedores,
  confirmar varios tramos terminal-a-terminal con `Enter` y deshacer el último
  clic con `Backspace`.
- Los recorridos de conduits elegidos se conservan en los conductores y el
  diagrama los reproduce en lugar de recalcular un camino distinto.

## [0.90.0] — 2026-08-08

### Fixed

- La vista previa al colocar un contenedor del catálogo muestra el mismo dibujo
  isométrico y las aberturas (``opening_grid`` / ``openings``) que el nodo
  insertado, en lugar de un rectángulo genérico sin bocas.

## [0.89.4] — 2026-08-08

### Fixed

- Las rutas offset y los desvíos laterales ya no se aceptan si todavía
  atraviesan una caja. Esto corrige la detección y el trazado de Route_33:
  el Conducto rodea ambas cajas y llega a S1 desde abajo.

## [0.89.3] — 2026-08-08

### Fixed

- Opposing-face stub cancellation in ``orthoRoute`` now requires the mouths to
  actually face each other. N→S (and E↔W) routes that leave outward no longer
  drop their stubs, so Route_33 skirts both device boxes in five segments and
  approaches S1 from below instead of from the left.

### Added

- Live E2E ``Route_33`` locks the N→S conduit to five segments, south approach
  into S1, and no mid-run pierce of either DeviceBox.

## [0.89.2] — 2026-08-07

### Added

- Palette connection groups for tubes, cables, and conductors can be collapsed
  independently, as can containers and elements.
- Selected connections can be deleted from their properties panel, the Delete
  toolbar/menu controls, or the Delete key.

## [0.89.1] — 2026-08-07

### Fixed

- Side↔plane tubes now leave and approach their declared side faces before
  taking mark-to-mark shortcuts. Route_32 S1→B1-1 therefore exits south and
  uses the required three segments instead of an illegal westward L.

### Added

- Live E2E ``Route_32`` locks ``Conducto_OPEN_Linea_01_01`` to exactly three
  segments and asserts its first segment leaves S1 downward.

## [0.89.0] — 2026-08-07

### Changed

- Iso leaf ``view.physical`` is now the **sprite AABB**: ``x/y`` is the NW of
  everything painted (including the NW iso bevel), and ``w/h`` spans the full
  drawn extent. Front face sits at local ``(20,20)``. Mark
  ``view.physical.bounds: sprite`` after migration; legacy sites migrate once
  on load (``scripts/migrate_sprite_bounds.py`` for offline trees).

### Added

- Live E2E ``Route_31``: offset N↔N DeviceBoxes — tube must skirt the upper
  DeviceBox sprite (front + iso depth).

### Fixed

- Side-opening conduits no longer treat every iso mouth≠anchor as clearing the
  endpoint leaf obstacle; only mouths inside the **front** face do. Routing
  obstacles use the sprite AABB directly (no negative paint / re-expand hull).

## [0.88.1] — 2026-08-07

### Added

- File → **Reload from disk** (F5): re-reads the active YAML, discards the
  buffer and undo/redo; prompts when the document is dirty.

## [0.88.0] — 2026-08-07

### Added

- Desktop: **Open recent** (paths remembered in Electron userData), **Quit**
  (Ctrl+Q), and **Full screen** (F11 / View menu).
- Window title shows the active YAML filename with a leading ``*`` when dirty
  (replaces the old ``HouseWire — physical`` title).

### Changed

- Desktop chrome: hide the in-app HouseWire brand mark (title bar already
  identifies the app); show desktop-only menu items only when the Electron
  bridge is present.

## [0.87.1] — 2026-08-07

### Fixed

- Desktop: hide Electron's default menu bar so only the in-app File/Edit/View
  menus show; set the window icon from ``desktop/icon.png`` (HouseWire logo).

## [0.87.0] — 2026-08-06

### Added

- **Desktop vs web file modes**: Electron shell under ``desktop/`` with native
  Open / Save As dialogs that pass absolute paths to the server. Web
  (``housewire serve``) keeps browser pickers for testing.
- ``POST /api/workspace/save-as-file`` writes the active YAML buffer to a path
  and opens it (closes a prior browser-origin temp tab when applicable).
- ``housewire serve`` may omit the site argument (empty workspace).
- ``GET /api/about`` includes ``runtime: "server"``; About shows ``desktop``
  when the Electron bridge is present.
- UI fragment ``00-files.js``: shared web/desktop file helpers; Save uses
  ``/api/save`` for serve-opened (non-browser-origin) documents without a
  File System Access handle.

### Changed

- File → Open / Save / Save As route through the desktop bridge when
  ``window.housewireDesktop`` is available; otherwise the previous web path.

## [0.86.0] — 2026-08-05

### Fixed

- Electrical stays off unless depth is max (e.g. 3/3): depth-out turns it off,
  session restore never leaves Electrical on at 1/x, and saved views only
  persist Electrical when already at max depth. Default boot remains depth 1.
- Post-drag refine clears stale cables immediately, re-routes tubes in frame
  slices, then rebuilds cables in later slices (no single sync
  ``refreshEdges`` dump after the tube pass). Resize also uses progressive
  refine instead of a full ``render()``.

## [0.85.1] — 2026-08-05

### Fixed

- Live route E2E: foreign-mouth skim matches the plane↔plane router (B/F marks
  only), so Route_21 side↔plane lamp is not flagged for sibling side mouths.
- Distinct-pin inbox bus is limited to wide NS multi-lane runs (Route_30);
  Route_12 keeps parallel mouth fans (rule 13).
- Element-obstacle skirts apply on wide NS buses; smaller fans stay clear so
  Route_06/21 avoid hostile out-and-backs. Rule 17 pierce stays on Route_30 E2E.

## [0.85.0] — 2026-08-05

### Changed

- Split the UI ``app.js`` IIFE into domain fragments under
  ``src/housewire/ui/static/app/`` (``01-core`` … ``05-shell``). The browser
  still loads one generated ``app.js``; rebuild with ``make bundle-ui`` /
  ``python scripts/bundle_ui_app.py``.

## [0.84.0] — 2026-08-05

### Added

- Route_30 example + live E2E: nine BN conductors in one aligned S↔N tube —
  straight conduit, mouth↔pin inbox ≤3 Manhattan segments, no element pierce,
  lane separation with crossings allowed.
- Wide InOut terminal grids fill missing entry-face cell pairs (e.g. ``N5→[N5,S5]``)
  so the UI can attach on the face toward the boca.
- Route E2E helpers: inbox segment budget and strand-through-element checks.

### Fixed

- Distinct-pin multi-conductor inbox skirts element obstacles (rule 17) instead
  of routing through them; ``stripShortZJogs`` no longer collapses L-approaches
  onto protected mouth latitudes.
- ``resolveElementAttach`` for InOut NS/WE picks the cell facing the mouth
  (upper strip attaches on S when the boca is south).

## [0.83.1] — 2026-08-05

### Fixed

- Progressive first paint no longer waits on ``buildCableLayout``: places draw
  immediately, then conduits (layout + tubes), then elements/cables. Double-rAF
  between passes so each layer can appear before the next heavy pass.
- After drag/resize, the moved box paints first; conduits re-route in
  ~6ms frame slices (stale cables cleared), then cables rebuild on a later
  frame — no multi-second main-thread freeze before any update.
- Progressive paint keeps the route geometry cache open from the conduit pass
  into the electrical pass (and clears it if a newer render cancels the rAF).

## [0.83.0] — 2026-08-05

### Added

- Progressive layout paint: places first, then conduits, then elements/cables
  (``requestAnimationFrame`` passes with a generation token so a newer render
  aborts stale work). After drag/resize, tubes refresh immediately and cables
  catch up on the next frame.

### Fixed

- Multi-conductor distinct-pin inbox (Route_29): unique-depth Manhattan bus
  from pin column to highway lane so strands keep lane pitch instead of
  stacking on a shared horizontal.
- ``strands_overlap`` ignores proper segment crossings by default (U-turn
  lane flip may cross in the inbox); still rejects parallel / colinear
  stacks. Route_29 E2E documents that crossings are allowed.

## [0.82.7] — 2026-08-05

### Added

- Route_29 example + E2E: three conductors in one N↔N conduit must keep lane
  separation (``assert_no_strand_lane_overlap``).

## [0.82.6] — 2026-08-05

### Fixed

- Localize remaining UI strings that still used hard-coded English: unsaved
  close / delete dialogs, modal defaults, recipe insert forms, and status-bar
  messages (``es`` / ``en`` via ``i18n.js``).

## [0.82.5] — 2026-08-05

### Fixed

- Plane↔plane mark-to-mark routing treats other bocas on the endpoint boxes as
  obstacles so a tube cannot skim a foreign mouth mid-run (Route_28
  ``Conducto_OPEN_Linea_03_01`` vs B2-1). Side↔plane shortcuts stay unchanged
  so Route_21 lamp L/strands are preserved.

### Added

- Route quality + E2E: ``tubes_skim_foreign_mouths`` / ``assert_tube_geometry_ok``
  (colinear stack + foreign-mouth skim) on every live geometry suite.

## [0.82.4] — 2026-08-05

### Changed

- Side↔plane conduits (e.g. N→B) also try mark-to-mark L/C (≤3 segments)
  before contour+iso stubs — Route_21 ``Conducto_lampara``.

## [0.82.3] — 2026-08-05

### Added

- E2E **Route_15** at depth 1/2: room-to-room conduit must stay ≤3 segments
  (colinear case: one straight run; covers the same stub-cross gap as Route_14).

## [0.82.2] — 2026-08-05

### Fixed

- Side-face conduits: prefer clear colinear mark-to-mark straight runs, and
  skip opposing face stubs that would cross in a tight gap (Route_14 Tube2).

## [0.82.1] — 2026-08-05

### Fixed

- Plane-to-plane routing: when mark-to-mark L is blocked, try a ≤3-segment
  C/U via ``orthoRoute`` before contour+iso stubs (Route_28 Linea_03).

## [0.82.0] — 2026-08-05

### Added

- Example **Route_28** and E2E: back-face layout where mark-to-mark L paths
  would colinear-stack; live routes must clear prior tubes and use extra bends.

### Changed

- Plane-to-plane Manhattan L shortcut rejects candidates that stack on already
  occupied conduit segments (falls through to contour / ortho routing).

## [0.81.1] — 2026-08-05

### Fixed

- First-click wiring snap: larger hit radius, sticky hover target, and block
  place/element drag so nearby openings/terminals register on the first pick.

## [0.81.0] — 2026-08-05

### Added

- Example **Route_27** (offset back-face openings) and E2E asserting four
  Manhattan L conduits (exactly one corner / ≤3 path points).
- When both conduit ends are non-colinear plane bocas (B/F), prefer a clear
  mark-to-mark Manhattan L instead of contour stubs with extra bends.

## [0.80.0] — 2026-08-05

### Added

- While inserting a conduit or conductor, show a Manhattan rubber-band preview
  after the first endpoint, and snap the pointer to nearby openings/terminals
  on both the first and second click.

### Changed

- Route E2E: collapsed Route_01…Route_20 per-site modules into
  ``test_route_smoke`` (Route_01, 03, 06, 07, 12). YAML demos remain;
  targeted suites from Route_21+ are unchanged.


## [0.79.0] — 2026-08-05

### Added

- Example **Route_26** (aligned back-face openings) and E2E asserting four
  single-segment straight conduits (no intermediate vertices).
- When both conduit ends are colinear plane bocas (B/F), route mark-to-mark as
  one H/V segment instead of contour stubs.

## [0.78.1] — 2026-08-05

### Fixed

- Multi-hop cables that traverse a conduit opposite its from→to no longer
  mirror lane offsets: reversed hop centerlines negate ``laneDist`` so strands
  keep a stable side of the tube (fixes empty slots / stacked wires in mixed
  orientation bundles).

## [0.78.0] — 2026-08-05

### Changed

- Isometric side opening marks sit on the mid-depth axis between front and back
  projected edges; F/B marks stay inside the front∩back overlap and are separated
  by the same NW iso diagonal as the front/back box vertices. Side conduits route
  mark-to-mark for straight runs.

### Added

- Example **Route_25** and live E2E asserting ISO opening-mark layout invariants.

## [0.77.17] — 2026-08-05

### Fixed

- Cable hops use anchor-to-anchor conduit cores so parallel lanes no longer
  pick up iso inset jogs (strand out-and-back); painted tubes still reach
  opening marks. E2E quality checks read ``data-core-d`` for mouth matching.

## [0.77.16] — 2026-08-05

### Fixed

- Conduit tube display keeps both endpoint boxes unclipped so straight runs
  (e.g. cross layouts) paint visible ``edge-tube`` geometry instead of empty paths.

### Added

- Example site **Route_24** (four aligned DeviceBoxes, cross conduits) and live
  E2E test asserting four straight painted tubes.

## [0.77.15] — 2026-08-05

### Fixed

- Conduit routing keeps a stable core between contour anchors and adds
  face-aligned ortho links to rendered inset marks (no endpoint snap that
  creates diagonals or drops routes).


## [0.77.14] — 2026-08-05

### Fixed

- Conduit paths now pin their first/last route points to opening mouths after
  route simplification, preventing endpoints from stopping short of the target
  opening marks.

## [0.77.13] — 2026-08-05

### Fixed

- Conduit endpoints now align to the rendered opening-mark positions, removing
  visual drift between conduit mouths and opening circles in isometric view.

## [0.77.12] — 2026-08-05

### Fixed

- Isometric box wireframe lines now use neutral node-stroke gray instead of the
  global edge blue, improving depth perception in both dark and light themes.

## [0.77.11] — 2026-08-05

### Changed

- In isometric boxes, front-face outline is slightly thicker so 3D depth reads
  clearly while all wireframe edges stay neutral gray when not selected.

## [0.77.10] — 2026-08-05

### Changed

- Increased isometric depth and pushed front/back opening marks further inward
  to keep clearer separation from side openings and face borders.

## [0.77.9] — 2026-08-05

### Fixed

- The top-right front↔back diagonal is now solid (visible edge), side openings
  use a dedicated color, and front/back opening marks are pushed further inside
  their face rectangles using a 1.5x depth inset rule to avoid overlap with
  side openings.

## [0.77.8] — 2026-08-05

### Fixed

- Isometric back-wireframe lines are now painted above the front face so dashed
  hidden segments remain visible; selected places tint the wireframe in
  selection color for clearer contrast.

## [0.77.7] — 2026-08-05

### Fixed

- Isometric opening-mark placement is now easier to tune via explicit
  constants, with side marks fixed at the exact mid-depth plane and F/B marks
  slightly staggered inside their own faces to avoid colinearity.

## [0.77.6] — 2026-08-05

### Fixed

- Isometric box projection now classifies visible/hidden back edges correctly
  (top-left visible, right/bottom hidden), and opening mark offsets are
  repositioned: side marks sit midway between front/back faces; F/B marks stay
  inside their projected rectangles with border-safe spacing.

## [0.77.5] — 2026-08-05

### Changed

- Header now has a clearer visual separation between the menu area and the
  open-file tabs (divider, spacing, and subtle tab strip tint).

## [0.77.4] — 2026-08-05

### Fixed

- Leaf place isometric boxes draw a full hidden wireframe (back face and depth
  ribs) with dashed strokes, matching far opening marks.

## [0.77.3] — 2026-08-05

### Fixed

- File Save now routes to Save As when a document has no filesystem target,
  and regular Save writes back to the chosen file path.


## [0.77.2] — 2026-08-05

### Fixed

- Canvas action messages no longer repeat the document save state; only the
  left doc strip shows saved / unsaved.

## [0.77.1] — 2026-08-05

### Changed

- Logo, menu bar, and open-file tabs share one app header row (tabs scroll
  on the right).

## [0.77.0] — 2026-08-05

### Changed

- UI chrome: file tabs above the menu bar; view controls (depth, Electrical,
  fit, zoom) and canvas messages move to a status strip under the canvas.
  The active filename and save state show on that strip.

## [0.76.5] — 2026-08-05

### Changed

- Conductor wiring uses dedicated cursors for the first and second terminal
  pick; resize/move cursors no longer override terminal selection on hover.

## [0.76.4] — 2026-08-05

### Changed

- Outline breadcrumb navigation upward increases depth by one per level
  instead of resetting it, so the expanded nesting stays visible from
  shallower canvas locations.

## [0.76.3] — 2026-08-05

### Fixed

- Selecting a single place box enables element entries in the palette and
  Insert menu; starting an insert turns the electrical layer on when needed.

## [0.76.2] — 2026-08-05

### Fixed

- Nested catalog insert no longer stuck at depth 1/1: ``setDepth`` no longer
  caps against stale ``maxDepth`` before reload, and insert syncs max depth
  from the server then selects the new place.

## [0.76.1] — 2026-08-05

### Fixed

- File → New selects the site root and shows its properties by default.

## [0.76.0] — 2026-08-05

### Changed

- Outline inside a nested canvas location shows a clickable breadcrumb from
  site root to the current view, then content under that location (depth and
  Electrical rules unchanged). Path rows stay visible even when collapsed.

## [0.75.3] — 2026-08-05

### Fixed

- After inserting or reparenting a place into another, depth increases
  automatically so the new selection appears in the outline and properties.

## [0.75.2] — 2026-08-05

### Changed

- View toolbar and menu: Electrical sits next to depth (+/−); depth items
  are grouped together in the View menu (depth out/in, then Electrical).

## [0.75.1] — 2026-08-05

### Fixed

- File → New uses PascalCase YAML stems (``NuevoSitio.yaml`` / ``NewSite.yaml``)
  instead of snake_case from localized labels.

## [0.75.0] — 2026-08-05

### Changed

- Outline visibility matches canvas depth and the Electrical layer (elements
  only on leaf places when Electrical is on).
- Turning Electrical on sets depth to the maximum for the current location;
  turning it off restores the previous depth.

## [0.74.0] — 2026-08-05

### Changed

- Insert palette sorts by localized label again (easier to find types).
- Place and element boxes show icon + name on one line; type stays in the
  tooltip.

## [0.73.8] — 2026-08-05

### Fixed

- File → New: tab shows the real YAML filename (``Nuevo_sitio.yaml``) with a
  dirty bullet until Save; root Id in properties shows that technical stem
  (path remains ``.``); sticky dirty no longer clears when the temp file matches
  the buffer.

## [0.73.7] — 2026-08-05

### Fixed

- Boot no longer aborts when syncing the electrical UI: ``paletteCatalog`` is
  declared before the early ``syncElectricalUi`` call so route E2E (and the
  Electrical toolbar button) work again.

## [0.73.6] — 2026-08-05

### Fixed

- Empty new sites mark the outline root as selectable so clicking it shows
  House properties (same as the canvas locations list).

## [0.73.5] — 2026-08-05

### Changed

- With the electrical layer off, palette Element types and Insert menu entries
  for elements/cables/conductors are disabled (grayed) until Electrical is on.

## [0.73.4] — 2026-08-05

### Fixed

- Catalog insert uses ASCII technical ids (``Caja_de_derivacion``) so canvas
  navigation does not fail on Unicode NFD forms of accented ids.
- Place lookup accepts NFC-equivalent path segments for legacy accented ids.
- Nested catalog placement requests enough canvas depth so new child places
  appear immediately.

## [0.73.3] — 2026-08-05

### Fixed

- Front/back opening grid: bumping columns or rows from 0 no longer snaps
  back to empty (the unset axis defaults to 1).

## [0.73.2] — 2026-08-05

### Changed

- Insert palette lists types alphabetically by technical type id so order is
  stable across locales.

## [0.73.1] — 2026-08-05

### Fixed

- File → New uses spaced localized YAML names (``New site.yaml`` /
  ``Nuevo sitio.yaml``) and sets root ``name`` and ``label`` to match.

## [0.73.0] — 2026-08-05

### Changed

- Paste with a place clipboard nests into a selected destination place (still
  duplicates as a sibling when the Copy source stays selected).
- Dragging a place onto another place reparents it into the drop target
  (`POST /api/edit/reparent`).

## [0.72.1] — 2026-08-05

### Changed

- Default catalog ``0.17.0``: new ``DeviceBox`` places get
  ``opening_grid`` ``NS: 1``, ``WE: 1``, ``B: 1``.

## [0.72.0] — 2026-08-05

### Changed

- File → New creates a dirty tab titled ``New site`` / ``Nuevo sitio`` with
  matching root ``name``/``label`` and YAML name (``New site.yaml`` /
  ``Nuevo sitio.yaml``).

### Fixed

- Clearing or adding place openings toggles the flat vs isometric box style
  (and mouth marks) on the canvas; empty ``opening_grid`` is removed from YAML.

## [0.71.0] — 2026-08-05

### Added

- New places apply catalog type/subtype defaults (e.g. JunctionBox
  ``opening_grid`` and ``install``) when those fields are omitted.

## [0.70.2] — 2026-08-05

### Fixed

- Empty new sites list the House root as a canvas location, so Insert → Element
  Add can enter placement (previously ``locationId`` stayed unset and Add did
  nothing).

## [0.70.1] — 2026-08-05

### Fixed

- Icon sprite fetch is cache-busted with the package version so new symbols
  (e.g. File → New ``file-plus``) appear after upgrades; added missing
  ``folder-plus`` sprite used by Insert → Container.

## [0.70.0] — 2026-08-05

### Added

- File → New and toolbar New (Ctrl+N): create an empty House site as a new
  document tab (``POST /api/workspace/new``). Use Save as… to keep it on disk.

## [0.69.2] — 2026-08-05

### Fixed

- After Save, the tab title no longer keeps the dirty bullet (``•``) when the
  document is clean; view tabs refresh from workspace status again.

## [0.69.1] — 2026-08-05

### Changed

- Opening iso bevel: deeper NW extrusion, square corners on F and far edges,
  mouth marks inset into each face, far mouths use a single bold dashed stroke
  (no double ring).

## [0.69.0] — 2026-08-05

### Added

- Leaf places with openings: NW isometric bevel and circle marks for every
  ``opening_grid`` cell (used or unused). Near faces (N/W/F) are bold; far
  faces (S/E/B) are dashed or double-outline, with a per-face visual offset.
  Conduit routing mouths stay on the 2D contour.

## [0.68.6] — 2026-08-05

### Fixed

- Live route E2E: harness turns Electrical on and deepens to max depth before
  dumping the canvas (defaults are depth 1 / electrical off, which left
  strands empty). Route_19 hub uses E1–E3 so each tube has its own opening.

## [0.68.5] — 2026-08-05

### Fixed

- Insert Conduit / Conductor: openings and terminals accept clicks again while
  wiring (``pointer-events`` were always off). Link hit strokes are ignored
  during the gesture so tubes do not steal the endpoint click; side openings
  get a mouth hit circle.

## [0.68.4] — 2026-08-05

### Fixed

- Properties openings/terminals editor stays expanded after a field save
  (inspector rebuild no longer collapses the face-grid ``<details>``).

## [0.68.3] — 2026-08-05

### Fixed

- Conduit selection with Electrical layer off: ``.edge-tube`` no longer steals
  clicks from the wider ``.edge-tube-hit`` target (same pattern as cable
  strands/jackets).

## [0.68.2] — 2026-08-05

### Fixed

- Clipboard pack/copy: unpack the four-tuple from ``_expand_deletion_sets``
  (places, elements, ids, cables) so File → Copy / paste APIs work again.

## [0.68.1] — 2026-08-05

### Fixed

- Example sites Route_13 / Route_18 / Route_20 / Route_21: restored valid YAML
  indentation for `name` under Supply / EarthElectrode (broken File → Open and
  `yaml.safe_load` after a subtype cleanup).

## [0.68.0] — 2026-08-05

### Changed

- Link picking: tube, strand, and sheath hit strokes stay at least ~16px on
  screen and grow with zoom-out, so cables remain clickable on wide sites
  (e.g. Route_21 overview).
- Clicking a sheath jacket selects the Cable; clicking a colored strand
  selects that Conductor when it differs from the sheath.

### Fixed

- Conduit refresh no longer applied the painted tube width to the hit layer.

## [0.67.1] — 2026-08-04

### Changed

- Palette: containers and elements share the same row color (section headers
  still separate the two groups).
- Sidebar / Properties panel titles use the same uppercase styling when the
  panel is open and when it is collapsed to the edge tab.

## [0.67.0] — 2026-08-04

### Added

- Cable/conduit/conductor management in the UI: select tubes and strands,
  editable link properties, delete links, Insert → Conduit/Conductor wiring
  gestures (opening→opening / terminal→terminal), Cable sheath grouping, and
  open→claim→land actions for open runs.
- API: ``GET/PATCH /api/cable``, ``POST /api/cable/{conduit,conductor,sheath,open,claim,land}``,
  ``GET /api/cable/open-runs``.

## [0.66.4] — 2026-08-04

### Changed

- Drop the openings/terminals face compass diagram (face letters in each row
  are enough).
- Properties panel styling aligned with the sidebar (type size, padding,
  openings summary as a bordered control).

## [0.66.3] — 2026-08-04

### Fixed

- Toolbar button hover titles and aria-labels follow the UI language.

## [0.66.2] — 2026-08-04

### Changed

- Openings/terminals props: one summary line; expand once to edit all faces
  (F/B stay as a row×column matrix).

## [0.66.1] — 2026-08-04

### Fixed

- Openings/terminals cell hover titles and face summaries relabel when the UI
  language changes.

## [0.66.0] — 2026-08-04

### Changed

- Openings/terminals props editor: compact summary + per-face accordion;
  front/back cells render as a row×column matrix (``B{row}-{col}``).

## [0.65.0] — 2026-08-04

### Changed

- Closed internal enum **values** use PascalCase (keys stay snake_case):
  ``kind`` (``PlaceType``, …), ``direction`` (``In``/``Out``/``InOut``),
  ``role`` (``Phase``, ``PE``, …), ``install``/``mount``/``representation``.
- No legacy aliases (``place_type``, ``inout``, ``in_wall``, …).

## [0.64.0] — 2026-08-04

### Added

- Properties panel face/cell editor for place ``opening_grid`` / ``openings``
  and element ``terminal_grid`` / ``terminals`` (capacity steppers + chip
  toggles).

### Removed

- Stair ``connects`` field (API, UI, docs, site data). Stair remains a normal
  place in the tree.

## [0.63.0] — 2026-08-04

### Changed

- Catalog type YAML field is ``type:`` (not ``id:``); ``/api/catalog`` returns
  ``type`` / ``subtype`` keys. Loader still accepts legacy catalog ``id:``.
- Closed subtypes use PascalCase keys (``IP40``, ``OneGang``, ``Power``,
  ``Tube``, ``DC``, …); acronyms stay uppercase.

## [0.62.0] — 2026-08-04

### Added

- Closed catalog ``subtype`` vocabulary: when a type defines ``subtypes:``,
  values must be keys from that map (defaults apply when omitted); types
  without a map must omit ``subtype`` (prose goes in ``name`` / ``label`` /
  ``notes``).
- UI inspector subtype field is a closed combo from ``/api/catalog`` when
  the type has subtypes.

### Changed

- Documented type (PascalCase) vs subtype (kebab / technical tokens)
  convention in ``docs/schema-house-v2.md``.

## [0.61.0] — 2026-08-04

### Changed

- ``install`` values are ``surface`` | ``flush`` (recessed). Legacy
  ``in_wall`` normalizes to ``flush`` so it no longer collides with
  ``mount: wall``.
- Documented defaults for new places: ``install: flush``, ``mount: wall``
  (lamps: flush + ceiling). Recipes follow those defaults.
- UI labels: Flush / Embutido (not “In wall”).

## [0.60.1] — 2026-08-04

### Fixed

- High-contrast rims only when a stroke blends into its container or the
  canvas (e.g. BK in BK tube / dark bg); not for BK tubes on light theme or
  BK jackets in WH conduits.
- Conduit road width uses packed strand lanes, not ``contains.length`` (which
  fattened tubes after loose-conductor modeling).

## [0.60.0] — 2026-08-04

### Added

- Conduit and Cable link entries accept ``install: surface | in_wall`` (legacy
  ``flush`` normalizes to ``in_wall``), same closed set as places.

### Changed

- Docs: install values documented as ``surface`` / ``in_wall`` (not ``flush``).

## [0.59.4] — 2026-08-04

### Fixed

- Collapsed left nav expand strip uses Sidebar / Barra lateral (not Outline).

## [0.59.3] — 2026-08-04

### Fixed

- Changing UI language reloads the catalog and refreshes Palette (and open
  insert dialogs) so type labels follow the new locale.

## [0.59.2] — 2026-08-04

### Changed

- Palette list styling matches the Outline tree (flat rows, shared hover,
  icon/label treatment) instead of bordered cards.

## [0.59.1] — 2026-08-04

### Fixed

- Selecting a place/element scrolls the Outline list to the last selected row
  (and pans the canvas using live DOM bounds).

## [0.59.0] — 2026-08-04

### Changed

- Left sidebar Outline and Palette share an accordion layout (Cursor-style):
  both visible with a draggable horizontal split, each section collapsible on
  its own, plus the existing whole-panel collapse.

## [0.58.0] — 2026-08-04

### Added

- Selecting a place/element (single, additive, or marquee) pans the canvas so
  the last selected item stays in view.

## [0.57.1] — 2026-08-04

### Changed

- Place (container) properties show a Parent field; parent values for places
  and elements prefer label/name over technical ids.

## [0.57.0] — 2026-08-04

### Changed

- Catalog insert proposes localized ID / name / label from the type label
  (e.g. Spanish ``Caja_de_derivación`` / ``Caja de derivación``).
- On place, colliding siblings get paste-style suffixes (``_1``, `` 1``) for
  id and display fields.

## [0.56.1] — 2026-08-04

### Fixed

- Element properties Parent field shows the current view location name when the
  item sits on the canvas floor (was labeled ``(canvas root)``).

## [0.56.0] — 2026-08-04

### Changed

- Catalog placement preview follows the pointer with the cursor at the box
  origin (0,0) before click.
- Elements place with a single click (default size); containers still support
  click-for-default or SE drag-to-size from the click corner.
- Empty-canvas placement parents to the current view location (API ``"."``),
  recomputed from the final origin rather than a stale press hit.

## [0.55.1] — 2026-08-04

### Fixed

- Toolbar/menu Lucide icons: add ``viewBox`` on static SVGs, size ``<use>``
  explicitly, and drop toolbar ``margin-right`` so pressed/hover tool buttons
  center the glyph instead of overflowing to the right.

## [0.55.0] — 2026-08-04

### Added

- While moving or resizing a selection, the canvas auto-pans when the pointer
  approaches the viewport edge so the gesture can continue off-screen.

## [0.54.2] — 2026-08-04

### Fixed

- Lucide icons via the sprite now set ``viewBox="0 0 24 24"`` so glyphs are
  centered in their box (palette, outline, canvas type icons).

## [0.54.1] — 2026-08-04

### Fixed

- Palette list icons now use each catalog type's ``icon`` field (same as canvas
  / outline) instead of a generic folder/box glyph by kind.

## [0.54.0] — 2026-08-04

### Added

- Catalog placement now picks the parent container from the first canvas click
  (no prior selection required), supports click-for-default-size (larger for
  containers than elements), and shows a live node/element ghost while dragging
  instead of the selection marquee.

## [0.53.0] — 2026-08-04

### Added

- Outline panel palette tab listing all catalog containers/elements, with
  localized Insert → Element… / Container… type-subtype pickers and a shared
  insert-details modal (immutable ID, read-only description).
- After Add, explicit canvas click-drag placement sets initial position and size.
- Catalog API exposes localized subtype options for combo selection.

### Changed

- Document identity is shown in tabs only (filename removed from the header).
- Catalog insert no longer commits immediately on modal submit; it enters
  placement mode with localized guidance.

### Fixed

- Initial document tab renders on startup when a site is already open.
- Interior-element drag autosize expands/shrinks the host in all directions
  (including NW) and is reversible before release via drag-start snapshot
  recomputation; opposite-wall jumps from ancestor cascade during live drag
  are avoided.
- After element drags that change host geometry, container conduits are
  re-routed on drop (live re-route remains disabled for performance).
- Locked host autosize growth is anchored to persisted base size, and
  auto-absorb no longer persists grown w/h as a new lock.

## [0.52.0] — 2026-08-04

### Added

- New ``Insert → Palette…`` flow for catalog-based insertion:
  place containers and electrical elements can be selected from a searchable
  palette and inserted directly into the current place context.
- New API ``POST /api/insert/catalog-item`` for generic catalog item insertion
  (place/element), returning updated graph + inserted id for immediate
  selection in UI.

## [0.51.1] — 2026-08-04

### Fixed

- Expand tabs are anchored to the correct workspace edges when panels are
  collapsed, avoiding side confusion.
- Properties panel now visually differentiates read-only fields from editable
  and select fields while keeping aligned sizing.

## [0.51.0] — 2026-08-04

### Added

- Draggable splitters to resize the Outline and Properties side panels, with
  widths persisted in session storage.

## [0.50.10] — 2026-08-04

### Changed

- Refined properties panel visual alignment: read-only and editable fields now
  share the same field box style and sizing, with unified select/input width.
- Orientation labels shortened to ``Orientation v./h.`` (and Spanish
  ``Orientación v./h.``) to fit one line cleanly.

## [0.50.9] — 2026-08-04

### Changed

- Properties labels now show ``Vertical orientation`` / ``Horizontal orientation``
  (and Spanish equivalents) instead of axis names.

## [0.50.8] — 2026-08-04

### Fixed

- Properties panel ``select`` controls now use the same width and field styling
  as text inputs.

## [0.50.7] — 2026-08-04

### Changed

- Replaced flip checkboxes in the properties panel with localized orientation
  selects (North/South and West/East) while preserving internal
  ``flip_ns``/``flip_we`` storage.

## [0.50.6] — 2026-08-04

### Changed

- Properties labels now switch language immediately in the panel when toggling
  UI locale.
- ``install`` is now a closed select with canonical values ``surface`` and
  ``in_wall`` (localized labels in UI).
- ``mount`` is now a closed select with canonical values ``wall``,
  ``ceiling``, and ``floor`` (localized labels in UI).

## [0.50.5] — 2026-08-04

### Changed

- Properties panel UX polish: ``type`` / ``subtype`` are now read-only, key
  labels are localized, ``flip_ns`` / ``flip_we`` are shown as readable labels,
  and ``install`` / ``mount`` use localized combo suggestions while preserving
  canonical stored values.

## [0.50.4] — 2026-08-04

### Fixed

- Site outline refreshes after property panel edits (e.g. ``name`` / ``label``).

## [0.50.3] — 2026-08-04

### Fixed

- Properties panel text fields are saved on blur and before changing
  selection, so edits are not lost when clicking another box or element
  (checkbox flips already saved immediately).

## [0.50.2] — 2026-08-04

### Added

- Help **About** dialog and ``/api/about`` description follow the UI locale
  (English / Spanish labels and program description).

## [0.50.1] — 2026-08-04

### Added

- Catalog type ``description`` follows the UI locale via ``description_es``
  (``catalog_type_description`` and ``/api/catalog``).

## [0.50.0] — 2026-08-04

### Added

- UI locale **en** / **es**: browser detection, ``View → Language``,
  ``localStorage`` key ``housewire-locale``, and ``lang`` /
  ``Accept-Language`` on API requests so outline/catalog type labels and
  paste placeholders (``Unnamed`` / ``Sin nombre``, etc.) follow the
  active language.

## [0.49.5] — 2026-08-04

### Fixed

- Dragging/resizing content past the west/north edge grows the host box in that
  direction live (moves the wall), not only east/south.

## [0.49.4] — 2026-08-04

### Changed

- Paste fills empty ``name`` / ``label`` as ``Unnamed`` / ``Unlabeled`` without
  a number; ``Unnamed 1`` only when ``Unnamed`` is already taken (same for
  labels). Copy still numbers pre-existing custom names/labels.

## [0.49.3] — 2026-08-04

### Changed

- Canvas drag/resize may use transient negative ``x``/``y``; on drop, siblings
  are shifted and locked parent size grows so persisted layout stays
  ``>= 0`` (parent-local origin).

## [0.49.2] — 2026-08-04

### Changed

- Paste fills empty ``name`` / ``label`` with ``Unnamed`` / ``Unlabeled``.
  Copy paste always takes the next spaced variant (even if free in the
  destination); cut paste only bumps on collisions.

## [0.49.1] — 2026-08-04

### Changed

- Paste uniquifies ``name`` and ``label`` independently of the technical id
  (same collision rule: append `` 1`` or increment a trailing number), so a
  custom label like ``Luz cocina`` becomes ``Luz cocina 1`` when the original
  is still present. Cut→paste keeps values when free.

## [0.49.0] — 2026-08-04

### Changed

- Faster physical canvas routing: spatial occupied queries from the first
  segment, memoized empty-``occupied`` ortho routes, medium pass instead of
  full wide pass for stack-only conflicts, O(1) conduit lookup for cable hops,
  and element-only drags skip re-routing fixed tubes.

## [0.48.6] — 2026-08-04

### Changed

- Paste collision rename also updates auto-like ``name`` / ``label`` to a spaced
  form (``Interruptor 2``), not the technical id (``Interruptor_2``). Custom
  labels are preserved.

## [0.48.5] — 2026-08-04

### Changed

- Clipboard selection UX: **Copy** keeps the source selected (Paste duplicates as
  a sibling); **Cut → Paste** with no selection returns items to their original
  parent with severed cables left as open runs; after Paste the new items are
  selected.

## [0.48.4] — 2026-08-04

### Fixed

- Paste **elements** into a selected container (and back into their box when
  pasting with an empty selection on a parent canvas). Place clipboard items
  still paste as siblings.

## [0.48.3] — 2026-08-04

### Fixed

- Paste places as **siblings** of the selection (same rule as elements). With a
  place selected, paste no longer nests inside it; clear selection or open the
  target location to paste as a child of the canvas.

## [0.48.2] — 2026-08-04

### Fixed

- Outline and locations APIs read the in-memory edit buffer, so paste/cut/delete
  refresh the Outline before Save.

## [0.48.1] — 2026-08-04

### Fixed

- Paste finds a free slot when the copied position overlaps siblings, and
  enlarges a size-locked parent so the new content fits.

## [0.48.0] — 2026-08-04

### Added

- UI **Cut / Copy / Paste** (Edit menu, toolbar, ``Ctrl+X``/``C``/``V``): pack
  selected places/elements with internal links; cross-boundary conductors become
  open-run stubs; paste under the focused place with numeric id collision
  renaming. Outline uses natural sort for sibling names.

## [0.47.0] — 2026-08-04

### Added

- UI **Delete** (Edit menu, toolbar trash, `Delete`/`Backspace`): cascade-remove
  selected places/elements. Internal links go with the subtree; cross-boundary
  conductors become open runs and relocate beside the surviving end; conduits
  that lose an endpoint are dropped. One undoable edit via
  ``POST /api/edit/delete``.

## [0.46.0] — 2026-08-03

### Changed

- Local conduits may list cables declared on an **ancestor** place in
  ``contains``. Cross-location runs stay at the LCA (no ``../``); hop tubes
  stay on the floor/room so rooms remain copy-paste friendly. Prefer one
  Conduit per physical tube — do not duplicate the same openings at the root.
- Physical graph merges conduits that share the same opening pair into one
  edge (union of ``contains``), so accidental duplicates no longer double-draw.

## [0.45.1] — 2026-08-03

### Changed

- ``housewire-examples`` relicensed to **SSPL-1.0** and bumped to ``0.2.0``.

## [0.45.0] — 2026-08-03

### Changed

- License switched from MIT to **Server Side Public License v1 (SSPL-1.0)**.
  See ``LICENSE`` and the README license note (service offering obligations).

## [0.44.3] — 2026-08-03

### Fixed

- Revert conduit ``contains`` ancestor lookups. Links stay in one place’s
  ``cables:`` map; cross-location runs (cable + hop conduits) are declared on
  the common ancestor so references only go downward (no ``../``).
- Keep clearer FastAPI ``detail`` text in UI Save/API errors (from 0.44.2).

## [0.44.2] — 2026-08-03

### Fixed

- ~~Conduit ``contains`` may reference cables declared on an **ancestor** place~~
  (reverted in 0.44.3).
- UI Save/API errors show the FastAPI ``detail`` text instead of raw JSON.

## [0.44.1] — 2026-08-03

### Fixed

- Restore electrical on/off before building the Outline on reload (F5).
- Shift+marquee: a fully enclosed place (leaf or container) is selected alone;
  its elements are not also selected.
- Ctrl/Cmd+Shift+marquee adds the box to the current selection.

## [0.44.0] — 2026-08-03

### Changed

- Multi-selection is hierarchical: never keep a container and its descendants
  selected together. Selecting a parent drops children; selecting a child drops
  ancestors. Shift+marquee selects a container only when it is fully enclosed
  (contents are not also selected). Ctrl/Cmd click toggles with the same rule.
- Outline highlights every selected item. Properties stays empty when more than
  one item is selected (status shows the count).

## [0.43.4] — 2026-08-03

### Fixed

- Resize from N/W stops at the origin without jumping: the E/S edge stays fixed
  when ``x``/``y`` would go negative (previously ``Math.max(0, x)`` left ``w``/``h``
  too large and the box grew the wrong way).

## [0.43.3] — 2026-08-03

### Fixed

- Properties conduits for a place include tubes that attach to nested children
  (e.g. a stair lists conduits that end on a device box inside it), not only
  exact endpoint matches.

## [0.43.2] — 2026-08-03

### Fixed

- Alt/Space pan cursor (grab) also shows over place and element boxes, not only
  empty canvas.

## [0.43.1] — 2026-08-03

### Fixed

- Properties lists only what the canvas shows: elements when electrical view is
  on (and the place is a leaf in the current depth), and conduits that appear
  as edges in the current location view.

## [0.43.0] — 2026-08-03

### Added

- F5 / reload keeps the open document's canvas view (location, depth, electrical
  on/off, pan/zoom) via ``sessionStorage`` when the server still has the same
  file open. Dirty state already survived in the server workspace.

## [0.42.2] — 2026-08-03

### Fixed

- Element resize in the electrical view updates the box, terminal marks, and
  re-routes cables after the drag (previously only the stored size changed).

## [0.42.1] — 2026-08-03

### Changed

- ``icon:`` is a single Lucide kebab id only (``plug``, ``zap``, …). Empty or
  invalid values fall back to ``circle``.

## [0.42.0] — 2026-08-03

### Changed

- UI icons use a local Lucide SVG sprite. Catalog and instance ``icon:`` values
  are Lucide ids (``plug``, ``zap``, …).

## [0.41.2] — 2026-08-03

### Fixed

- Resize hover cursors (ns/ew/diagonal) now override the box ``move`` cursor so
  edges and corners clearly show a resize affordance.

## [0.41.1] — 2026-08-03

### Fixed

- Canvas resize under a flipped host (parent or canvas WE/NS) maps the visual
  edge/corner and drag delta into stored coordinates, matching move-drag
  mirroring so boxes no longer jump the wrong way.

## [0.41.0] — 2026-08-03

### Added

- Persist optional ``view.physical.w/h`` and ``view.electrical.w/h`` (auto-size
  when omitted). Canvas resize via edges/corners (hover cursors); sizes write
  back through the positions PATCH.

### Changed

- Session defaults: electrical diagram off, depth 1. Without electrical, place
  measure ignores elements and conduit tubes use a single-lane width.

## [0.40.0] — 2026-08-03

### Changed

- When inbox cables force a place to grow, update box sizes and re-route edges
  in place instead of a second full SVG clear and repaint of every node.

## [0.39.0] — 2026-08-03

### Changed

- Stack/cross scoring against painted tubes and strands uses a spatial grid over
  occupied segments, so each candidate path queries nearby segs instead of the
  full O(n) list as the layout fills in.

## [0.38.0] — 2026-08-03

### Changed

- Cache place/element obstacle rects, border rects, and a parent→children index
  once per render/refresh frame so each conduit and strand does not rebuild the
  same geometry.

## [0.37.0] — 2026-08-03

### Changed

- Ortho routing tries a narrow candidate set first (few lane offsets, box rails
  only) and expands to the full search only when the narrow pass still hits
  obstacles or stacks. Cuts CPU on clear routes without changing the scoring
  order for hard cases.

## [0.36.0] — 2026-08-03

### Changed

- Canvas drag no longer re-routes conduits and cables on every pointermove:
  transforms update live; full edge refresh runs once on drop. Dragging dense
  layouts stays responsive.

## [0.35.24] — 2026-08-03

### Changed

- Canvas pan vs drag: default arrow cursor; left-drag on empty canvas pans
  (click clears selection); Space or Alt+drag and middle-click pan anywhere,
  including over elements. Element/place drag still moves objects. Hint under
  View → Fit.

## [0.35.23] — 2026-08-03

### Fixed

- Inbox routing prefers short in-box runs (crossings OK) over long outside
  loops; legal lane-pitch parallels no longer count as stacks. Host places
  grow to fit inbox cable envelopes so strands do not sit outside the box.

## [0.35.22] — 2026-08-03

### Fixed

- Flip checkboxes roll back the canvas and inspector when the properties
  PATCH fails, so a stale serve cannot leave a local-only flip that Save and
  Undo cannot see. Save→reload and undo/redo of flips are covered by a
  regression test.

## [0.35.21] — 2026-08-03

### Fixed

- Same-box / free-space lane offsets no longer shove a strand through the
  from/to element: endpoint boxes keep lane clearance, parallel paths that
  still pierce are re-routed, and painted strands occupy later corridors.

## [0.35.20] — 2026-08-03

### Fixed

- Inbox corridors no longer pierce the from/to element to reach a far-side
  pin (rule 17): endpoint boxes are routing obstacles; approach stays on the
  pin face. Quality checks flag a deep pierce of an endpoint box, not only
  foreign elements.

## [0.35.19] — 2026-08-03

### Fixed

- Multi-cable terminal V no longer overshoots the inbox stub and climbs back
  toward the pin (diamond / shared trunk / out-and-back). Stub depth grows
  with the V, and tip/rail depths clamp to the lane target.

## [0.35.18] — 2026-08-03

### Fixed

- Multi-cable terminal V fans use lane pitch (not a 12px floor) so strands stay
  closer while remaining distinct; elements widen when consecutive terminal
  fans would overlap (host place grows with them).

## [0.35.17] — 2026-08-03

### Fixed

- Shift+drag marquee inside a leaf place no longer also selects that place when
  it hits hosted elements (parent box always covers the element hit-test).

## [0.35.16] — 2026-08-03

### Fixed

- View flips apply immediately on checkbox click (and undo/redo): canvas-location
  ``flip_*`` is exposed on the graph and remaps top-level places/elements;
  flipping is in-place (same footprint / content AABB). Checkbox styling no
  longer stretches under ``width: 100%``.

## [0.35.15] — 2026-08-03

### Fixed

- Free-space cables (no conduit) route pin-to-pin instead of element-center to
  element-center, so strands land on terminal cells (e.g. Supply / earth).
- Face-cell pins still on the catalog ``terminal_grid`` stay attachable when an
  instance only lists a subset of terminals (e.g. cable to ``N2`` on an MCB).

## [0.35.14] — 2026-08-03

### Fixed

- Shift+drag marquee no longer selects container places (only leaf places and
  elements), so boxing inside a room does not also select the room.

## [0.35.13] — 2026-08-03

### Added

- View-only ``flip_ns`` / ``flip_we`` on ``view.physical`` (places) and
  ``view.electrical`` (elements): mirror canvas content and openings/terminals
  without renaming YAML ids. Nested flips compose (XOR). Editable from the
  Properties panel.

## [0.35.12] — 2026-08-03

### Fixed

- Shift+drag marquee selection works inside place floors (and on elements), not
  only on empty canvas background.

## [0.35.11] — 2026-08-03

### Fixed

- Orthogonal conduit scoring treats **colinear stacks** and **perpendicular
  crossings** separately: stacks still beat bend-count, but a short crossing
  is preferred over a long C-detour around another tube (rule 15).

### Added

- Example ``Route_23`` and E2E ``test_conduit_cross`` for cross-over-detour.

## [0.35.10] — 2026-08-03

### Added

- Routing rule 17: inbox cables must skirt foreign **elements** (same idea as
  conduits around leaf locations). Live detector ``through element``, example
  ``Route_22``, and E2E ``test_element_avoidance``.

### Fixed

- Same-box corridors use element obstacles (inflated for highway lane pack)
  and obstacle-aware joins so multi-cable feeds no longer cut through
  intervening breakers.

## [0.35.9] — 2026-08-03

### Fixed

- Distinct conduits no longer colinear-stack mid-run: conflict clearance uses
  painted half-widths (``half_a + half_b + laneGap``), and avoiding stack beats
  saving a bend when scoring orthogonal candidates (routing rule 15).

### Clarified

- ``docs/routing-rules.md`` rule 15: strands on their own tube are required;
  stacking two tube strokes is not. Live detector ``tubes colinear-overlap``
  plus E2E ``test_conduit_overlap``.

## [0.35.8] — 2026-08-03

### Fixed

- Highway lanes are packed **per conduit**, not per end-to-end route key, so
  multi-hop cables that share a tube no longer all sit on lane 0 inside a
  tube sized for every wire (fat empty conduits).

### Added

- Live/unit detector for underfilled tubes (``tube underfilled``) and E2E
  coverage via ``tests/route_e2e/test_conduit_packing.py``.

## [0.35.7] — 2026-08-03

### Fixed

- Multi-cable openings stay **parallel through the boca** (routing rule 13):
  hop assembly no longer collapses every lane onto the center mouth.
  Detectors flag mouth meets; live E2E ignores duplicate GNYE green+yellow
  paints of the same geometry.

### Changed

- ``docs/routing-rules.md`` hop contract: lane crossings (parallel offsets)
  instead of converging all strands at painted bocas.

## [0.35.6] — 2026-08-02

### Added

- Parallel live route E2E via ``pytest-xdist`` (``make test`` /
  ``make test-route-e2e`` use ``-n 4 --dist loadfile``; override with
  ``E2E_WORKERS=N``). Smoke target ``make test-route-e2e-smoke``.

## [0.35.5] — 2026-08-02

### Changed

- Renamed example ``Test_01`` → ``Route_21`` (default ``site_yaml()``).
- Unified live route E2E under ``tests/route_e2e/`` (unit detectors +
  ``test_route_01``…``21``); removed ``tests/test_route_e2e_test01.py``.
- E2E harness waits for painted tubes/strands before dumping (fixes flaky
  empty-canvas failures such as Route_08).
- UI ``index.html`` cache-busts ``app.js`` / ``app.css`` with the live
  ``__version__``.

## [0.35.4] — 2026-08-02

### Added

- Optional ``housewire-catalog`` integration: ``resolve_catalog_types_dir`` falls
  back to the installed package; extras ``[catalog]`` / ``[dev]`` / ``[examples]``
  pull it from git. ``make install`` editable-installs ``catalogs/default`` when
  present.

### Removed

- Committed ``tests/data/catalog`` mirror (use ``housewire-catalog`` instead).

### Changed

- Docs/README: package install is the normal catalog path; clone remains an
  override.

## [0.35.3] — 2026-08-02

### Fixed

- Live route E2E uses a project-local Playwright browser cache
  (``.playwright-browsers/``, set by ``make install`` / ``tests/conftest.py``)
  so ``pytest`` no longer fails when ``~/.cache/ms-playwright`` is missing.
- Missing Chromium skips live E2E with an install hint instead of ERROR.

## [0.35.2] — 2026-08-02

### Added

- ``docs/routing-rules.md`` — English routing rules for tube envelope, mouths,
  inbox V, and hop assembly contract.
- Twenty public route fixtures ``Route_01``…``Route_20`` in
  ``housewire-examples``, plus Playwright E2E modules under
  ``tests/route_e2e/`` (shared harness + ``assess_live_site``).

### Fixed

- UI ``/api/locations`` and ``/api/outline`` use the active site YAML when the
  site root contains multiple documents (examples package multi-file folder).

## [0.35.1] — 2026-08-02

### Added

- Optional ``housewire-examples`` package (``packages/housewire-examples``)
  with public ``Test_01`` site; install via ``pip install -e '.[examples]'``
  or ``make prepare``. E2E resolves the site from the package,
  ``HOUSEWIRE_E2E_SITE``, or local ``sites/Tests/``.

## [0.35.0] — 2026-08-02

### Changed

- Hop routing simplified to three phases (head + tube + tail) with no
  full-chain post-passes (``preserveTerminalVLead`` / ``ensureVertexNear`` /
  strip on the merged path).

### Fixed

- Hop strands use the raw conduit centerline (``exteriorPathD`` was dropping
  border-skimming segments and truncating bocas, e.g. Test_01 lamp vertical).
- Hop mouths follow painted tube ends; mouth fans flip toward the pin so plane
  bocas (B/F) do not fan back into the tube.

### Added

- Live canvas route invariants (``assess_live_canvas``) and E2E Test_01 suite
  that asserts boca transit, tube envelope, terminal V, and no shared inbox
  trunk on the paths the UI actually paints.

## [0.34.33] — 2026-08-02

### Fixed

- ``convergeLaneToMouth`` only pops vertices already on the mouth (tol 1.5),
  not the offset lane's arrival ~laneDist away (tol 8 skipped bocas).

## [0.34.32] — 2026-08-02

### Fixed

- ``preserveTerminalVLead`` passes mouth/fan protectPts into stripOutAndBack
  (unprotected strip skipped lamp bocas after V restore).
- Hop assembly re-asserts both mouths with ``ensureVertexNear`` after merge
  and after V preserve.

## [0.34.31] — 2026-08-02

### Fixed

- ``joinLeadToFanTip`` always follows the pin-face column/row first (no
  |dx|-vs-|dy| axis pick that rebuilt the shared rail-Y trunk).
- Mouth fan tips: lateral offset plus inward depth (unique latitudes; never
  back toward the boca).

## [0.34.30] — 2026-08-02

### Fixed

- Hop inbox join: ``joinLeadToFanTip`` travels along the lead column to the
  fan-tip latitude before crossing (avoids the shared rail-Y trunk).
- Strip out-and-back only on head/tail with mouth+stub+fan protected; never
  strip the pristine tube segment across mouth converges.

### Added

- Route-quality helpers and tests for the shared rail-Y anti-pattern vs
  column-first fan-tip joins.

## [0.34.29] — 2026-08-02

### Fixed

- Hop routing crash: renamed shadowing ``let fromPin`` in the end-tail
  assembly (TDZ broke all strand painting).

## [0.34.28] — 2026-08-02

### Fixed

- Hop end tail: assemble pin→fan→stub→mouth then reverse (the previous
  mouth→stub prepend created pin↔mouth loops and duplicated V leads).

## [0.34.27] — 2026-08-02

### Fixed

- Hop cleanup: keep ``head + tube + tail`` from fan-tip joins; only strip
  out-and-back with mouths protected. Dropped full-path lift / Manhattan /
  tube-splice passes that created shared trunks and pin↔mouth loops.

## [0.34.26] — 2026-08-02

### Fixed

- Hop paths re-splice the canonical offset tube between both mouths after
  strip/merge (``spliceTubeSegment``), so lanes cannot skip a boca or paint
  a parallel outside the conduit. Removed full-path ``ensureVertexNear``
  which created pin↔mouth out-and-back loops.

## [0.34.25] — 2026-08-02

### Fixed

- Hop inbox: terminal leads join the mouth **fan tip** (not the shared stub),
  so lanes no longer collapse onto one trunk after the boca.
- ``ensureVertexNear`` re-splices any hop path that skipped an opening mouth
  after strip/merge (offset lanes continuing past the boca).
- Static cache-bust query bumped so browsers load the new ``app.js``.

### Added

- Tests for stub-join anti-pattern vs fan-tip join, and mouth splice.

## [0.34.24] — 2026-08-02

### Fixed

- Bipolar / multi-cable terminal V: ``liftOffsetSpineFromPin`` no longer runs
  ``ensureOrthoPoly`` on an existing pin→tip diagonal (that flattened both
  arms into perpendicular stubs). Hop cleaning re-applies
  ``preserveTerminalVLead`` after mouth Manhattan strips.

### Added

- Tests for bipolar V, ``ensure_ortho_poly`` anti-pattern, lift preserving V,
  and stacked inbox corridor overlap detection.

## [0.34.23] — 2026-08-02

### Changed

- Canvas defaults: open at maximum depth and with the electrical diagram on
  (toolbar + View menu). Saved per-document depth is still restored when
  switching tabs.

## [0.34.22] — 2026-08-02

### Fixed

- Hop routing no longer offsets a continuous inbox+tube centerline and then
  rewrites the whole path with ``forceThroughMouth`` (that pushed strands
  outside conduits and along place borders). Exterior gets a parallel offset
  with local mouth converge; inbox separation uses a post-boca mouth fan.
- ``strand_exits_before_mouth`` is tube-aware (in-tube then outside) so inbox
  fans are not false positives; ``assess_bundle`` scores the mouth→mouth run
  for outside-conduit checks.

### Added

- Hard tests: anti-pattern lane collapse, ``build_hop_lane`` inside-tube /
  through-mouth / no early exit, place-border hug, and assess_bundle tube
  checks. ``build_hop_lane`` / ``mouth_fan_pts`` / ``converge_lane_to_mouth``
  reference helpers mirror the canvas hop assembly.

## [0.34.21] — 2026-08-02

### Changed

- High-contrast rim is generalized to nested same-color content: a jacket or
  strand inside a conduit/jacket of the same IEC color (e.g. BK in BK) gets the
  thin outline, not only bare conduit tubes.

### Added

- ``needs_nested_contrast_rim`` helper and tests for same-color nesting.

## [0.34.20] — 2026-08-02

### Fixed

- Opening exits: after parallel offset, lanes are forced through each mouth so
  an L at the boca no longer peels through the tube wall (Foto 1 early exit).
- ``stripOutAndBack`` keeps mouth pivots (converge→leave) so the boca snap is
  not collapsed back into a side exit.

### Added

- Detectors/tests for early mouth exit, strands outside the tube envelope, and
  stacked BN/GNYE overlap on a shared run.

## [0.34.19] — 2026-08-02

### Fixed

- Multi-cable terminal V: ``stripShortZJogs`` no longer treats pin→tip→L as an
  orthogonal Z, which collapsed one arm into a vertical entry.
- Both V arms stay diagonal (wider fan + tip rail); ``mergeLeadToSpine`` prefers
  same-lateral spine joins so strands meet only at the pin, not earlier.
- ``preserveTerminalVLead`` restores a collapsed diagonal as a safety net.

### Added

- Detectors/tests for asymmetric V, premature merge before the pin, and
  strip-Z preserving terminal diagonals.

## [0.34.18] — 2026-08-02

### Fixed

- Nested-conduit elbows: hop routes use one continuous centerline offset
  (inbox → exterior → inbox) with a single ``+laneDist`` sign. The old
  ``-laneDist`` on pin→mouth tails peeled the bundle at corners and made
  strands overlap / cross at openings.
- ``mergeLeadToSpine`` picks the join index that avoids ida-y-vuelta; inbox
  L scoring penalizes reverse runs so multi-cable terminals stop painting
  out-and-back corridors.

### Added

- Route-quality helpers and tests for continuous vs flipped-inbox hop lanes,
  stacked inbox overlaps, and out-and-back above shared terminals.

## [0.34.17] — 2026-08-02

### Fixed

- Multi-cable terminal V: the diagonal touches the pin (no 90° stub first);
  tip→spine is Manhattan via ``mergeLeadToSpine`` so diagonals cannot appear
  in the next segment after spine trim.
- Stronger out-and-back stripping after lead/spine merge.

### Added

- Detectors for perpendicular pin entry, diagonals away from the pin, and
  out-and-back (ida y vuelta) on the same path.

## [0.34.16] — 2026-08-02

### Fixed

- Conduit nesting visuals: WH sheath jacket follows the BK+BU lane group
  (offset mid-span), not the tube centerline; bare PE conductors no longer
  get a fake jacket.
- Strands of the same cable keep contiguous highway lanes so a jacket can
  wrap them.
- GNYE paints as green with yellow dashes (not a flat lime peer strand).

### Added

- Tests for jacket mid-offset, contiguous cable lanes, and lamp-bundle
  nesting (BK conduit → WH(BK,BU) + bare GNYE).

## [0.34.15] — 2026-08-02

### Fixed

- Multi-cable terminal V uses exactly one short diagonal (stub→tip) then
  Manhattan to the lane; no second diagonal / spike near the pin.
- Opening Manhattan rewrite skips segments near terminal pins so it cannot
  shred a V into a jagged M.
- Spine is trimmed after the terminal lead to avoid double-back merges.

### Added

- Route-quality checks for jagged terminal leads and a clean ``terminal_v_lead``
  reference geometry.

## [0.34.14] — 2026-08-02

### Fixed

- Opening joins no longer snap the offset spine end onto the mouth (that
  painted diagonal funnels). Inbox→mouth uses a Manhattan L, with a
  near-mouth diagonal rewrite as a safety net.

### Added

- Route-quality regression for the screenshot-style opening funnel snap.

## [0.34.13] — 2026-08-02

### Changed

- Routing rule: openings are one-cable / Manhattan-only (no diagonals).
  Terminals with more than one cable enter in a V (short diagonals OK);
  single-cable terminals stay Manhattan.

### Added

- Route-quality checks for any diagonal outside multi-cable V, and for
  diagonals near openings.

## [0.34.12] — 2026-08-02

### Fixed

- Inbox lane offset no longer paints along regleta/element faces (spine is
  lifted off the attach face before pin rejoin).
- Several strands on the same terminal fan in a V (slot-based) instead of
  stacking perpendicular stubs.
- Inbox L scoring penalizes mid legs that hug the element face (fewer
  border slides / crossings).
- High-contrast conduit rim is thinner (`OUTLINE_EXTRA` 0.8px).

### Added

- Route-quality detectors for element-border hugs and perpendicular shared
  terminal entry (want V).

## [0.34.11] — 2026-08-02

### Added

- View menu Dark / Light mode toggle (persisted in `localStorage`).

## [0.34.10] — 2026-08-02

### Fixed

- Conduit `color:` from YAML is painted on the tube; dark tubes get a white
  high-contrast rim (light tubes get a dark rim).
- Cable jacket follows the continuous conduit display path (no cut-and-reappear
  gaps near mouths) and stays slightly narrower so the tube color shows.
- Inbox lane offset sign matches the exterior highway (no lane crossings at
  the boca). Terminal stubs skip when they would reverse into a C/Z; short Z
  jogs are stripped from the final polyline.
- Route-quality tests cover crossings, jacket gaps, contrast outlines, and
  conduit colors on the physical graph.

## [0.34.9] — 2026-08-02

### Fixed

- Inbox tails are Manhattan again; diagonals only within 36px of a pin (no
  boca→element diagonals). Lane offset applies to exterior and inbox spines.
- Sheath jacket paints exterior + short B/F boca stubs only (no sheath through
  a leaf to the Regleta). `WH` jacket uses high opacity so it reads white.
- Tube clipping uses inset 0 so side-opening ends do not leave a painted
  corridor into the leaf.
- Route-quality tests detect long diagonals, Z/C, overlap, and true `WH`/`BK`
  CSS.

## [0.34.8] — 2026-08-02

### Fixed

- Terminal leads use stub + diagonal only (no Manhattan Z into unique pins).
  Lane offset stays on the exterior highway; inbox tails join the offset mouth.
- Route-quality tests now encode the live Lampara failure (Manhattan rejoin
  onto a terminal strip) so that pattern cannot pass unnoticed.
- Sheath jacket follows B/F tubes to the plane boca; `BK`/`WH` are true black /
  white again. Contrast is a light rim on the conduit tube, not recolored wires.

## [0.34.7] — 2026-08-02

### Added

- Route-quality checks (`housewire.ui.route_quality` + tests): fail when
  parallel strands overlap **or** when a run has unnecessary short C/Z jogs
  (so fixing one problem cannot silently reintroduce the other).

### Fixed

- Cable sheath `color:` (e.g. `Linea_lampara` `WH`) is passed as
  `jacket_color` and painted on the translucent jacket stroke.
- `BK` canvas CSS lightened so black strands stay visible on the dark UI.
- Multi-strand hops again keep a full parallel offset along the shared
  centerline, then rejoin pins with stub+diagonal (lanes separated without
  stacking, unique terminals without forced Manhattan Z).

## [0.34.6] — 2026-08-02

### Fixed

- B/F conduits again reach the plane boca (tube into the leaf, no ghost spur
  past the cell). Contour entry stays nudged off side openings.
- B/F markers are always biased off the place center (even a lone B1-1), not
  only when a side opening overlaps.
- Terminal Z-fans only when more than one strand shares the same pin cell.
  Highway lane offset applies on the exterior only so unique terminals do not
  pick up a rejoin Z; short terminal diagonals still allowed.

## [0.34.5] — 2026-08-02

### Fixed

- B/F conduits stop at the contour entry (no tube past the mouth into the
  leaf). Cables still visit the plane cell, then join the tube.
- Terminal leads may use a short diagonal after a tiny face stub, removing
  unnecessary C-jogs without merging strand lanes on the highway.

## [0.34.4] — 2026-08-02

### Fixed

- B/F conduit legs inside a leaf no longer use outward face stubs (removed
  the dead-end “ghost” tube spur at light points).

## [0.34.3] — 2026-08-02

### Changed

- Restored OS Open / Save As file pickers. Save (Ctrl+S) still writes only
  through the server so the browser "allow edit" permission aviso does not
  appear on every save.

## [0.34.2] — 2026-08-02

### Changed

- File Open / Save As use in-app path prompts; Save writes only via the
  server. Removed browser File System Access pickers and ``createWritable``
  (no native permission windows).

## [0.34.1] — 2026-08-02

### Fixed

- Conduits to B/F openings continue to the plane boca (not stop at the box
  border). Contour entry is nudged along the face so it does not sit on a
  side opening such as N1.

## [0.34.0] — 2026-08-02

### Added

- Help → About dialog (program, version, author, repository, license).
- ``GET /api/about`` and package metadata (``LICENSE``, author, repository URLs).

## [0.33.3] — 2026-08-02

### Fixed

- Conduits to B/F openings route to the contour mouth (not the interior
  plane cell), so tubes and cables reach light points / back faces.
- Sheath strands with opposite ``from``/``to`` group into one multi-color
  cable edge (e.g. brown + black on a switch loop).

## [0.33.2] — 2026-08-02

### Fixed

- Cable pin joins stay Manhattan (no diagonal cut-ins to terminals).
- Removed the conduit centerline stroke (``edge-tube-core``).
- Strand lanes are ordered by pin geometry to reduce crossing / stacking
  near terminal strips.

## [0.33.1] — 2026-08-02

### Changed

- Catalog type display uses ``label`` (or ``name``; legacy ``title`` still
  read). Canvas type captions show that label instead of the type id.

## [0.33.0] — 2026-08-02

### Changed

- Conduit tubes and cable jackets stop at leaf place mouths (no tube
  painted inside junction boxes).
- Cable strands keep lane offset through openings and inbox tails so they
  do not funnel to one point or stack on the same centerline.

## [0.32.9] — 2026-08-02

### Fixed

- Conduit tube and cable jacket widths are applied via inline style so CSS
  no longer forces a fixed stroke; road width follows contained strand count.

## [0.32.8] — 2026-08-02

### Fixed

- Orthogonal scoring prefers fewest bends again before soft wall/entry
  costs (stops staircase detours that only shortened the last arm).

## [0.32.7] — 2026-08-02

### Fixed

- Keep C-route wall clearance near the mouth stub (~24px) instead of a
  wide detour; prefer short final approach arms into the destination face.

## [0.32.6] — 2026-08-02

### Fixed

- Orthogonal routes penalize wall-hugging so a clearance C wins over an
  L that slides along a place edge.
- Cable overlays orient exterior pieces start→end, merge tails into one
  polyline, and strip out-and-back segments on the same run.

## [0.32.5] — 2026-08-02

### Fixed

- Cable tails route through the place opening (mouth) via the interior,
  not along the wall to the exterior lane join.
- Same-parent conduit routes prefer staying inside the parent content
  bounds instead of hugging outer rails.

## [0.32.4] — 2026-08-02

### Fixed

- Clamp face stubs so they do not overshoot the lane join (pin near an
  exit opening no longer draws down-then-up on the same run).

## [0.32.3] — 2026-08-02

### Fixed

- Multi-strand sheath cable edges keep per-conductor ``from_pins`` /
  ``to_pins`` so each color lands on its own terminal (e.g. BU → ``N3``
  instead of sharing the first strand’s pin).
- Inbox attach routing picks the strip face cell and L-bend with fewer
  turns when approaching from an adjacent opening.

## [0.32.2] — 2026-08-02

### Fixed

- Count face stubs when scoring ortho bends so an exit-stub plus
  horizontal-first L (down→right→down) loses to a vertical-first L.

## [0.32.1] — 2026-08-02

### Fixed

- Orthogonal routing picks clear paths by fewest bends before soft conflict
  weights (avoids needless Z jogs).
- Parallel cable offset keeps Manhattan corners (intersect offset segments
  instead of averaging normals into a diagonal chamfer).

## [0.32.0] — 2026-08-02

### Changed

- Terminal **ids** are face-cell tokens (``N1``, ``S2``, …); ``name`` /
  ``label`` / ``role`` are display-only. Conductor refs use the id.
- Opening drawing uses ``opening_grid`` slot count (e.g. ``N: 2`` + only
  ``N2`` draws on the right).
- TerminalStrip pins are ``N1``…``Nn`` (N-side convention) with ``NS`` grid
  attaching both faces for ``inout``.

### Removed

- ``terminal_pairs`` (catalog and instance).

## [0.31.0] — 2026-08-02

### Changed

- Schema **`house/v2`**: unified ``cables`` map with typed ``Conduit`` /
  ``Cable`` (sheath) / ``Conductor`` links. Nodes stay under ``elements``.
- ``schema: house/v1`` (and unknown schemas) fail fast; no dual-read or
  in-app upgrade.
- Docs retargeted to ``docs/schema-house-v2.md``.

### Removed

- Top-level / place-level ``connections:`` and separate ``conduits:`` maps.
- Multi-color cable bags (``colors: […]``) and ``via`` wire-index pairing;
  one Conductor is one terminal pair with singular ``color``.
- Shell ``add connection`` / ``rm connection``.

## [0.30.1] — 2026-08-02

### Changed

- Program display name is **HouseWire** (CLI/UI banners, version string, docs).
  Package import path and CLI command remain ``housewire``.

## [0.30.0] — 2026-08-02

### Changed

- Rename package module ``housewire.project`` → ``housewire.site``
  (``SiteSession``, ``site_path``, ``split_site_arg``, …).
- Local convenience directory / gitignore entry ``projects/`` → ``sites/``.
- Site Makefiles use ``SITE`` instead of ``PROJECT``.

## [0.29.3] — 2026-08-02

### Changed

- Docs, shell help, and messages talk about a generic site YAML; ``housewire.yaml``
  remains only the default filename when creating a new site.
- Dev dependency ``httpx`` → ``httpx2`` (silences Starlette TestClient warning).

### Fixed

- Removed obsolete shell ``cd`` warning that assumed per-folder ``housewire.yaml``.

## [0.29.2] — 2026-08-02

### Fixed

- Place inspector wiring: cables/conduits defined on an ancestor place in the
  single site YAML are shown again (no longer looked up via legacy per-folder
  ``housewire.yaml`` paths).

## [0.29.1] — 2026-08-02

### Added

- Canonical conductor color table owned by housewire
  (``housewire.house.wire_colors``, IEC 60757 letter codes + UI CSS hex).
- ``GET /api/wire-colors`` so the canvas loads the same palette from the program.

## [0.29.0] — 2026-08-02

### Removed

- WireViz export, dependency, and `housewire generate` (CLI, shell, and Makefiles).
- Catalog fields `wireviz_collapse` and `wireviz_skip`.

### Changed

- Document validation no longer goes through a WireViz conversion; it walks the
  house/v1 tree directly (`validate_house_tree`).
- Catalog `terminal_pairs` replaces `wireviz_collapse` for canvas pin layout.
- Default catalog version **0.3.0**.

## [0.28.27] — 2026-08-02

### Fixed

- ``GET /api/place?location=.&id=.`` returns the site root (House) instead of 400.

## [0.28.26] — 2026-08-02

### Changed

- CLI ``generate``, ``serve``, ``shell``, and ABM commands accept a site YAML
  file path (not only a directory). Output still goes to ``<site_root>/out/``.

## [0.28.25] — 2026-08-01

### Changed

- Conduit highway width is derived from strand count: ``[gap][wire][gap]…``
  with gap = strand width, margins to the road walls included. Strands follow
  true parallel offsets of the conduit centerline (no stacked zig-zags).

## [0.28.24] — 2026-08-01

### Changed

- Wider lane spacing and transparent conduit “highway” so parallel strands stay
  visually separable; lane offset applies along the whole run (ends stay on
  terminals/openings).

## [0.28.23] — 2026-08-01

### Changed

- Draw terminal cell marks on elements; in-box cable tails stub out of the
  pin and route through the place interior instead of hugging box borders.

## [0.28.22] — 2026-08-01

### Changed

- Canvas ``terminal_grid`` uses only pins listed on the element instance when
  present (so a 1-way strip is not padded with unused catalog terminals).

## [0.28.21] — 2026-08-01

### Added

- Element ``terminal_grid`` (same grammar as location ``opening_grid``:
  ``NS: 2`` = 2 on N and 2 on S). Catalog defaults for MCB/MCB2P/RCD/strips;
  canvas routes connection pins to cells (``N1``, ``S2``, …).

## [0.28.20] — 2026-08-01

### Changed

- Element terminals fan out along the attach face (global slots per face) so
  strands no longer pile on one midpoint; conduit road width scales with
  ``contains`` (3 vs 15 cables stay distinct).

## [0.28.19] — 2026-08-01

### Changed

- **Reset** jumps the edit cursor to the last Save/open baseline without
  clearing history, so Redo can walk forward again from that point.

## [0.28.18] — 2026-08-01

### Changed

- Canvas cables draw as highway layers: neutral conduit road (width ∝
  ``contains``), white jacket per cable, and colored WireViz strands per
  ``via`` index that reach element attach points. No longer merges every
  conductor onto one green path.

## [0.28.17] — 2026-08-01

### Changed

- Unified edit history on the server: Undo / Redo / Reset revert layout moves,
  Properties edits, auto-layout, and Insert recipes in one stack. File → Save
  sets the new baseline. UI “Reset layout” renamed to **Reset**.

## [0.28.16] — 2026-08-01

### Fixed

- Hop cables again draw element→contour opening tails inside junction boxes
  (full L to N/E/S/W), plus exterior tube overlay — without in-box transit that
  caused the green lattice. Slightly inset exterior clipping so face exits
  (e.g. E2) are not left floating.

## [0.28.15] — 2026-08-01

### Fixed

- Properties PATCH 400 on notes with colons (e.g. ``Regleta_1: 5 bornes``):
  panel values are stored as plain text, not YAML-parsed. Also resolve canvas
  place id on save (``id=.``).

## [0.28.14] — 2026-08-01

### Fixed

- Same-box cables A→B and B→A no longer draw opposite L routes that close into
  a hollow green rectangle (e.g. Regleta ↔ relay feed + load bridges).

## [0.28.13] — 2026-08-01

### Fixed

- ``GET /api/place?location=Parking&id=Parking`` 400: the canvas place itself
  is requested as ``id=.`` (not repeating the location name). Outline click on
  the current canvas also opens its Properties.

## [0.28.12] — 2026-08-01

### Fixed

- Selecting a place/element expands the Properties side panel if it was
  collapsed. Serve ``index.html`` with ``Cache-Control: no-store`` so the UI
  does not stick on an old shell (and stale ``app.js?v=…``).

## [0.28.11] — 2026-08-01

### Changed

- Inspector panel title **Show** → **Properties**, with editable fields
  (name, label, type, subtype, notes, install/mount for places). Saves via
  ``PATCH /api/place/properties`` (session dirty until File → Save).

## [0.28.10] — 2026-08-01

### Fixed

- Cable drawing inside junction boxes: drop hop stubs and clipped tube
  fragments (they left floating green segments). In-box green is only
  same-place bridges (edge-to-edge L); hop cables overlay exterior tube
  geometry only.

## [0.28.9] — 2026-08-01

### Changed

- Menubar: after opening a menu with a click, hovering another top-level menu
  (File / Edit / View) switches to that dropdown.

## [0.28.8] — 2026-08-01

### Fixed

- Junction-box cable clutter: hop cables only draw a short in-box stub toward
  the exit opening (plus the exterior tube overlay). Full cross-box L tails for
  every outgoing cable were painting a green lattice; same-box bridges stay as
  full simple L runs.

## [0.28.7] — 2026-08-01

### Fixed

- In-box cable drawing: same-place runs and element↔opening tails use a
  simple L (no side-C / lane detours). Tube overlays on cables skip segments
  that cut through leaf boxes, so junction boxes no longer fill with a green
  lattice.

## [0.28.6] — 2026-08-01

### Changed

- Move socket/lamp/feed forms out of the inspector into **Edit → Insert**
  (flyout submenu + modal). Placeholder Insert entries for Element / Cable /
  Conduit (disabled) prepare the future atomic insert menu. UI no longer
  labels these as “Recipes”.

## [0.28.5] — 2026-08-01

### Fixed

- Tube/cable orthogonal routes no longer cut back through their own endpoint
  boxes (that drew the green lattice inside junction boxes). Endpoints count
  as obstacles and side-C rails clear each box rect, not only stub midpoints.

## [0.28.4] — 2026-08-01

### Fixed

- Orthogonal routing treats leaf places as obstacles so tubes (and cable
  overlays that follow them) prefer side-C / outer rails instead of cutting
  through junction boxes.

## [0.28.3] — 2026-08-01

### Fixed

- Stop drawing cable transit across intermediate junction boxes (green mesh
  between openings); cables only show endpoint tails and tube overlays.

## [0.28.2] — 2026-08-01

### Fixed

- View → Electrical closes the menu after toggling.

## [0.28.1] — 2026-08-01

### Added

- Status bar zoom slider (5%–300%) synced with wheel zoom and toolbar zoom.

## [0.28.0] — 2026-08-01

### Changed

- Menubar: File / Edit / View with icons and keyboard shortcuts; Edit has
  Undo/Redo/Reset/Auto-layout; View has Electrical, zoom, Fit, depth.
- Toolbar is an icon-only button strip grouped by File / Edit / View.

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
  ``GET /api/place``). Shared orchestration in ``site.recipe_actions``.
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
  clusters; site root uses the site directory name (no bare `raiz`).
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

- Shell prompt is path-only (`site/cwd`); dropped the redundant
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
- Zone diagrams group by **top-level directory** under `site_path` (no
  hard-coded site layout). Root-level YAMLs form a zone named after the site
  directory. Remap by pointing `site_path` at another subtree or wrapping
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
- README treats site data as an external path (`$SITE`); local `sites/` remains gitignored only as an optional convenience.

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
