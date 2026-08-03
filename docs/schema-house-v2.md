# Schema house/v2

Canonical format for **HouseWire**: document a home electrical installation in YAML
and edit it with the interactive UI / shell (physical canvas + electrical wiring).

Editing: `housewire shell <site>` or non-interactive `add` / `rm` / `show` (see README).

Element and place types live in an **external catalog** (YAML library),
installable as [`housewire-catalog`](https://github.com/guillermomolina/housewire-catalog)
(`pip install 'housewire[catalog]'`). A git clone under `catalogs/default` or
`HOUSEWIRE_CATALOG` still works as an override. Installation YAML lives in a
**separate site directory/repo** (not in the program repo).

### Catalog icons (UI)

Each catalog type may declare a Lucide icon id (kebab-case):

```yaml
# types/Socket.yaml (in housewire-catalog)
kind: element_type
id: Socket
icon: plug
```

Resolution order for the outline / UI:

1. Instance field ``icon:`` on the place or element YAML (optional override).
2. Site overlay ``$SITE/catalog/<Type>.yaml`` (shallow merge over the base type).
3. Base catalog ``icon:`` (from ``housewire-catalog``, ``HOUSEWIRE_CATALOG``, or
   ``catalogs/default``).
4. Fallback ``circle``.

Site overlay example (only customize the icon):

```yaml
# $SITE/catalog/Socket.yaml
id: Socket
icon: plug-zap
```

Values are Lucide icon ids shipped in the UI sprite (``plug``, ``zap``,
``house``, …).

## Nodes vs links

| Kind | Where | Role |
|------|-------|------|
| **Places / devices** | `elements:` tree | Locations and equipment (unchanged) |
| **Links** | top-level / place-level `cables:` map | Typed `Conduit` / `Cable` / `Conductor` — **not** elements |

```yaml
cables:
  Conducto_a_Enchufe_1:
    type: Conduit
    subtype: tube
    from: Caja_derivacion_4.W2
    to: Enchufe_1.N1
    contains: [Funda_a_Enchufe_1]
  Funda_a_Enchufe_1:
    type: Cable
    color: BK
    contains: [L, PE, N]
  L:
    type: Conductor
    color: GY
    section: "2.5 mm2"
    from: Caja_derivacion_4/Regleta_1.N3
    to: Enchufe_1/Socket.N1
  PE:
    type: Conductor
    color: GNYE
    from: Caja_derivacion_4/Regleta_1.N2
    to: Enchufe_1/Socket.N2
  N:
    type: Conductor
    color: BU
    from: Caja_derivacion_4/Regleta_1.N1
    to: Enchufe_1/Socket.N3
```

`house/v1` documents (`connections:`, separate `conduits:`, multi-color cable bags)
are **rejected** with a clear error. There is no dual-read or auto-upgrade.

## Document header

Every editable site YAML must declare:

```yaml
schema: house/v2
```

The site root document **is** the top place (`type: House` / `Floor` / …): the same
fields as a nested place (`type`, `label`, `mount`, `openings`, …), plus
`schema: house/v2`. Hierarchy is **only** nested places under `elements:` (map key = place id).
There is one site YAML per site directory (any ``.yaml`` / ``.yml`` name; new sites
default to ``housewire.yaml``); no per-place subdirectories.

### Place id, name, and label

| Field | What | Where | Used for |
|-------|------|-------|----------|
| **id** | Technical key `[A-Za-z0-9_]+` | Map key under `elements:` | Refs, paths, `cd`, conduits |
| **name** | Short working name (optional) | YAML `name:` on the place | Canvas, selectors, lists |
| **label** | Human text (optional) | YAML `label:` on the place | Inspector, docs, long tooltips |

Fallbacks:

- Canvas / selectors → `name` → **id**
- Inspector / human display → `label` → `name` → **id**
- Graphviz physical node title → `name` → **id**; `label` may appear in the subtitle if different

Elements use their YAML map key as **id**, optional ``name:`` (short display),
and optional ``label:`` (longer human text) — same pattern as places / cables /
conduits. Canvas and outline prefer ``name`` → id; inspector shows all three.

- **Id**: e.g. `Caja_derivacion_4`. No spaces. Used in refs.
- **`name`**: e.g. `CD4` (canvas).
- **`label`**: e.g. `Caja derivacion 4`. `add location "Caja derivacion 6"` → key
  `Caja_derivacion_6` with `label: Caja derivacion 6` (no automatic `name`).

Nested place example (under the site YAML):

```yaml
schema: house/v2
type: House
elements:
  Garage:
    type: Floor
    label: Garage
    elements:
      Junction_box_1:
        type: JunctionBox
        name: JB1
        label: "Junction box 1"
        subtype: "100x100 IP40"
        mount: ceiling
        opening_grid: { NS: 2, WE: 2, B: 1 }
        openings: [B1-1, N1]
        elements:
          Regleta_1:
            type: TerminalStrip
            label: "3-pair strip"
```

## Locations = nested place tree

The shell (`cd` / `ls` / `pwd`) walks place-typed children under `elements:`.
Devices (`Socket`, `MCB`, …) stay under `elements:` of the current place (non-place types).

Place types (catalog; see `PLACE_TYPES` in code):

| type | Meaning |
|------|---------|
| `Room` | Room / space |
| `Stair` | Stair / vertical circulation linking two places (`connects`) |
| `JunctionBox` | Junction / derivation box |
| `DeviceBox` | Device box (socket / switch; 1-/2-/3-gang) |
| `LightPoint` | Light point (ceiling/wall hole to a luminaire) |
| `Panel` | Distribution board (may declare `openings`) |
| `Floor` | Floor / level |
| `House` | Dwelling (need not be the tree root) |
| `Location` | Generic place (rare; prefer a specific type) |

### Stair (`connects`)

A stair is a place in the tree (sibling of the floors it links). Use ``connects``
to name the two ends:

```yaml
type: Stair
label: Escalera Parking — Planta baja
connects: [Parking, Planta_baja]
```

- ``connects``: list of two location refs (usually sibling ``Floor`` ids).
- Optional; used by docs/UI to show what the stair joins.
- Children (junction boxes, switches, light points) nest under the stair’s `elements:`.

The **site root** is the directory (or site YAML file) you pass to `housewire`
(`site_path`). Logical paths (`Garage/Junction_1`) are keys under nested
`elements:`, not filesystem folders.

- One site directory → one site YAML (nested places under `elements:`).
- `cd` / `ls` navigate place keys; `show` / `add element` act on the current place.
- `add location NAME --type T` nests under the current place (memory → `save`).
- Dirty YAML stay in memory across `cd`; `save` writes dirty buffers; `exit`
  prompts per dirty file.

### `install` (surface vs flush)

Optional on places with `mount`:

| `install` | Meaning |
|-----------|---------|
| `surface` | Surface-mounted (visible box / trunking) |
| `flush` | Recessed in wall / ceiling / floor |

If omitted, nothing is assumed. It does not change the local opening frame.

### DeviceBox

```yaml
type: DeviceBox
subtype: 1-gang          # 1-gang | 2-gang | 3-gang
install: surface
mount: wall
facing: S
openings: [N1]
elements:
  Socket:
    type: Socket
    subtype: Schuko
```

Several mechanisms in one box (same entry opening):

```yaml
type: DeviceBox
subtype: 2-gang
openings: [N1]
elements:
  Socket: { type: Socket, subtype: Schuko }
  Switch: { type: Switch, subtype: unipolar }
```

Shell (no hand-editing required):

```text
set install surface
set openings=[N1]
set opening_grid.N=1
add location Interruptor_1 --type DeviceBox --subtype 1-gang \
  --set install=surface --set mount=wall --set openings=[N1]
set --element Switch notes "…"
```

Values parse as YAML. Structural keys (`elements`, `cables`, `schema`) cannot be `set`; use `add` / `rm`.

### Light points

A conduit ends on a **`LightPoint`** place (ceiling/wall hole), not on a `DeviceBox`.
Typical opening: `B1-1` (back toward the slab) or a contour face if the tube arrives sideways.

```yaml
type: LightPoint
subtype: ceiling-hole
install: surface
mount: ceiling
opening_grid:
  B: 1
openings: [B1-1]
elements:
  Luminaire:
    type: Luminaire
```

```text
add location Lampara_1 --type LightPoint --label "Lampara 1" \
  --set install=surface --set mount=ceiling \
  --set opening_grid.B=1 --set openings=[B1-1]
add conduit Conducto_a_Lampara_1 --from Caja_derivacion_1.E2 --to Lampara_1.B1-1 \
  --contains Linea_a_Lampara_1
```

Reserve `DeviceBox` for real mechanism boxes (socket / switch).

### Elements

```yaml
elements:
  MT_Luces:
    type: MCB
    subtype: C10
    manufacturer: Merlin Gerin
    model: multi9
    serial: null
    label: LUZ
    notes: "..."
    terminals:                # optional; merges over catalog
      N1: { label: "1" }
```

Terminal **id** = face-cell token (`N1`, `S2`, …) — same grammar as openings.
Optional `name` / `label` / `role` are display metadata; conductor `from`/`to`
store the id. The UI shows `label`/`name` when present.

### Terminal grid (canvas layout)

Same face-grid grammar as location `opening_grid`. Declared on the catalog
type (and optionally overridden on the instance):

```yaml
# catalog MCB2P — N1/S1 and N2/S2
terminal_grid:
  NS: 2
terminals:
  N1: { label: "1", direction: in, role: neutral }
  S1: { label: "2", direction: out, role: neutral }
  N2: { label: "3", direction: in, role: phase }
  S2: { label: "4", direction: out, role: phase }

# instance: 6-way strip (N-side pins; NS grid draws both faces)
Regleta_1:
  type: TerminalStrip
  terminal_grid: { NS: 6 }
  terminals:
    N1: { direction: inout }
    # …
    N6: { direction: inout }
```

- `NS: 2` ≡ `N: 2` **and** `S: 2` (not “2 total”).
- `N: 2` ≡ only the north face.
- Pin id **is** the cell id; `inout` + NS also attaches the opposite face
  (`N1` → cells `[N1, S1]`). There is no `terminal_pairs`.

### Catalog element types

| type | Role |
|------|------|
| `MCB` | 1P+N MCB. `N1`→`S1` (phase), `N2`→`S2` (N); labels on casing |
| `MCB2P` | 2-pole MCB (e.g. main breaker) |
| `RCD` | RCD. `N1`→`S1` (phase), `N2`→`S2` (N) |
| `Supply` | Incoming supply (`S1`/`S2`, labels L/N) |
| `PETerminal` | PE bar (`N1`, label PE) |
| `EarthElectrode` | Earth electrode (`S1`, label PE) |
| `PowerSupply` | AC/DC supply (e.g. intercom) |
| `Intercom` | Door phone / video door phone (`N1`/`N2`, labels +/−) |
| `TerminalStrip` | Strip; pins `N1`…`Nn` with `NS` grid |
| `Socket` | Schuko (`N1`/`N2`/`N3`, labels L/PE/N) |
| `Switch` | Switch mechanism; subtypes `unipolar`, `crossover`, `intermediate` |
| `Luminaire` | Lamp / pendant (default `N1`–`N3`) |
| `Relay` | Smart relay; face-cell pins (see catalog subtypes) |

**Switch subtypes**

| subtype | Terminals |
|---------|-----------|
| `unipolar` (default) | `N1`, `S1` (labels 1, 2) |
| `crossover` (3-way) | `N1`/`N2`/`N3` (labels C, 1, 2) |
| `intermediate` | `N1`/`S1`/`N2`/`S2` |

## Openings (`JunctionBox`, `DeviceBox`, `LightPoint`, `Panel`)

Openings are **not** electrical terminals. They use the **local box frame**
(poker face): looking at the front face `F`.

```text
        N
    W   F   E
        S
         ↓
         B   (back / embedded)
```

`mount` + `facing` align that frame to the building. When naming openings, think
in the box frame, not geographic north.

### Ids

| Face | Id | Index order |
|------|----|-------------|
| Contour `N`/`S`/`E`/`W` | `N1`, `W2`, … | `N`/`S`: W→E · `E`/`W`: N→S |
| Back `B` / front `F` | `B1-1`, `F2-3`, … | 1st index N→S, 2nd W→E |

```yaml
type: JunctionBox
subtype: "100x100 IP40"
mount: ceiling          # ceiling | wall | floor
# facing: N             # wall: direction F faces (into the room)
opening_grid:
  NS: 3                 # ≡ N: 3x1 and S: 3x1 (integer = one row)
  WE: 2
  B: 2                  # ≡ B: 2x1 → B1-1, B1-2
openings: [B1-1, W1, N1]
```

- **`openings`**: list of **used** opening ids (plain strings).
- **`opening_grid`**: optional template per face. Keys: `N` `S` `E` `W` `F` `B`,
  or pairs `NS` / `WE`. Integer `3` = `3x1`. `3x2` = 3 columns (W→E) × 2 rows (N→S).
  An omitted face has no known grid. An explicit face overrides the pair.

If `openings` is set, `pend` requires enter/exit ids to be in that list.
If `opening_grid` is also set, each id must fit the grid for its face.

### Canvas layout (`view` / `views`)

Optional UI positions for the interactive editor (`housewire serve`):

```yaml
# On any place drawn as a node (JunctionBox, DeviceBox, …)
view:
  physical:
    x: 120
    y: 80
    rotation: 0    # optional: 0 | 90 | 180 | 270
    flip_ns: false # optional view-only N↔S mirror (content + openings)
    flip_we: false # optional view-only W↔E mirror

# On an element inside a place (electrical LOD layer)
elements:
  Socket:
    type: Socket
    view:
      electrical:
        x: 24
        y: 40
        rotation: 0    # optional: 0 | 90 | 180 | 270
        flip_ns: false # optional view-only N↔S mirror
        flip_we: false # optional view-only W↔E mirror

# On the canvas root place (any location that has child places)
views:
  physical:
    width: 2000
    height: 1400
    representation: line   # line | tube
```

- **`view.physical`**: canvas coordinates for that place under its parent canvas.
  ``x`` and ``y`` must be ``>= 0`` (parent-local origin at the content top-left).
  Optional ``w`` / ``h`` (``> 0``) lock the place box size on the canvas; when
  omitted, the UI auto-sizes from nested places and (when the electrical layer
  is on) elements. Optional ``flip_ns`` / ``flip_we`` mirror the place and its
  nested content on the canvas only (opening ids in YAML stay the same; mouths
  move with the flip). Nested flips compose (XOR) with ancestors.
- **`view.electrical`**: coordinates of an **element** inside its hosting place
  box (parent-local, ``>= 0``). Used when the UI **Elements** layer is on.
  Optional ``w`` / ``h`` lock the element box; when omitted, size follows the
  terminal grid. Same optional ``flip_ns`` / ``flip_we`` for the element box
  and terminals.
- **`views.physical`**: page size and preferred conduit drawing mode for the
  canvas root location (often a `Floor` or `Room`, but any place type works).
- Canvas zoom (pan/wheel) is independent of `representation` (legacy YAML;
  the UI always draws conduits as tubes).
- **Depth zoom** (`depth` query / toolbar) controls how many nested place
  levels are drawn inside parent boxes; it does not change representation.
- **Electrical** toolbar toggle (session UI state; not persisted) shows or hides
  elements and cables on the physical canvas. Default session start is **off**
  (places and conduits only) at **depth 1**. Element boxes enlarge their host
  place (like nested locations) only while the electrical layer is on; elements
  draw only when the place is a leaf in the current depth view. Cables ride on
  conduit paths when visible. With electrical off, conduit tube width ignores
  cable packing (thin tubes).
- Back openings (`B…`) are drawn at the symbol center, not as a fourth side.
- Omitted when unused; the UI does not require these fields.

### Mounting

| `mount` | `F` faces… | `B` is… | Local N/S/E/W |
|---------|------------|---------|---------------|
| `ceiling` | floor | into the ceiling | perimeter (poker looking at F from below) |
| `wall` | the room (`facing:`) | into the wall | local N = “up” edge of the F view |
| `floor` | ceiling | into the floor | perimeter looking at F |

### Usage

```text
pend N1 S1
```

```yaml
cables:
  Conducto_a_Caja_2:
    type: Conduit
    subtype: tube
    from: .N1
    to: Caja_derivacion_2.S1
    contains: [Linea_a_Caja_derivacion_2]
```

### Do not confuse

- **Opening** (`N1`, `B1-1`): local geometry. Used in conduit `from` / `to`.
- **Conduit**: tube between locations (`from: A.N1` → `to: B.S1`).
- **Terminal** (`Regleta.N1`): electrical connection inside the box.

## Cables map (`cables:`)

One dictionary. Kind is distinguished by `type`:

| `type` | Endpoints | `contains` | Role |
|--------|-----------|------------|------|
| `Conduit` | `from`/`to` = `PlaceRef.Opening` | ids of Cable and/or Conductor | Physical tube/hose between openings |
| `Cable` | none (sheath / bundle) | ids of Cable and/or Conductor | Jacket grouping; drawn inside conduits |
| `Conductor` | `from`/`to` = `ElementRef.Terminal` (one each) | forbidden | Leaf wire = the electrical connection |

Shared fields: `name`, `label`, `notes`, optional `section`, `color` (singular).
Catalog subtypes remain (`tube`, `power`, …).

```yaml
cables:
  Conducto_1:
    type: Conduit
    subtype: tube
    from: Caja_A.E1
    to: Caja_B.N1
    contains: [Funda_BK, PE]
  Funda_BK:
    type: Cable
    color: BK
    contains: [L, N]
  L:
    type: Conductor
    color: BN
    section: "1.5 mm2"
    from: Caja_A/Regleta.N1
    to: Caja_B/Socket.N1
  N:
    type: Conductor
    color: BU
    section: "1.5 mm2"
    from: Caja_A/Regleta.N2
    to: Caja_B/Socket.N3
  PE:
    type: Conductor
    color: GNYE
    from: Caja_A/Regleta.N3
    to: Caja_B/Socket.N2
```

**Ownership:** a place node owns the `cables` entries it declares. Conductor
`from`/`to` must resolve under that place’s subtree (connection-scope rules).

ABM shortcuts: `add cable NAME --colors BN,BU` creates a `Cable` sheath plus
child `Conductor`s; `add conductor` / `add conduit` write typed entries directly.
There is no separate `connections:` list and no multi-terminal `via:` sugar —
one Conductor = one terminal pair.

### Color codes (`color:`)

HouseWire owns the conductor color table (`housewire.house.wire_colors`). Letter
codes follow **IEC 60757**; CSS hex values are the HouseWire UI palette. Use
uppercase in YAML (`BN`, not `bn`). The UI loads the same table from
`GET /api/wire-colors`.

A Cable sheath’s own `color:` (e.g. `WH`) is the **jacket** tint on the canvas
(`jacket_color` on the physical cable edge). A Conduit’s own `color:` (e.g.
`BK`) is painted on the **tube**. Conductor `color:` values are the individual
strand strokes. Dark tubes get a thin light high-contrast rim (and light tubes
a dark rim). The sheath jacket follows the continuous tube path, slightly
narrower, so the conduit color remains visible.

| Code | Color | Typical use |
|------|-------|-------------|
| `BK` | black | Phase from panel / permanent lights phase |
| `BN` | brown | Switched phase, lamp feeds, some socket L |
| `RD` | red | Catalog `dc` default (with `BK`) |
| `OG` | orange | Available; uncommon in domestic work |
| `YE` | yellow | Available; do not use for PE |
| `GN` | green | Available; prefer `GNYE` for PE |
| `BU` | blue | Neutral (N) |
| `VT` | violet | Available |
| `GY` | grey | Phase (light grey), travellers, some feeds |
| `WH` | white | Sheath jacket / catalog `signal` default |
| `PK` | pink | Available |
| `TQ` | turquoise | Available |
| `GNYE` | green-yellow | Protective earth (PE) |
| `SR` | silver | Available |

- **PE** → `GNYE` (not bare `GN` / `YE`).
- **Neutral** → `BU` (IEC / EU practice).
- **Phase** may be `BK`, `BN`, or `GY`; note mixed phases in the same box.

### Sheath vs loose conductors

A multiwire run is a `Cable` sheath (`contains: […]`) plus leaf `Conductor`s —
not a single bag with `colors: […]`. Loose singles can be Conductors listed
directly in a Conduit’s `contains` without a sheath.

### Capture recipes

Run from the **parent** place (floor/room) that owns `cables:`. Recipes create
the destination place plus typed links in the current place node.

```text
cd Garage
add socket Outlet_5 --from Junction_2.N1 --strip Regleta
# → DeviceBox Outlet_5 + Socket; Cable/Conductors; Conduit; terminals set on Conductors

add lamp Lamp_3 --from Junction_3.S1 --strip Regleta --pins 6,5,2
add feed Linea_A_a_B --from Junction_4.E1 --to Junction_3.N1 \
  --from-pin Regleta_2.1 --to-pin Regleta.N1 --colors BK
```

### Pending runs (incremental capture)

When a cable enters/leaves a box but the far end is unknown:

- Create Cable/Conductor(+Conduit) entries; leave Conductor `from`/`to` unset.
- Prefix ids with `PEND_` while open; status in `notes` (e.g. `status: pending`).

```text
cd Parking/Caja_derivacion_2
pend N1 S1            # defaults 1.5 mm2 / BN,BU
```

When closing: rename off `PEND_`, set Conductor terminals, clear pending notes.

### Open → claim → land (unknown far end)

```text
cd Planta_baja/Recibidor/Cuadro_General
open S2 1.5 --colors BN,BU
claim OPEN_Linea_01 --enter N1 --exit E2
land OPEN_Linea_01 --from 'Cuadro_General/MT.[2, 3]' \
  --to 'Caja_derivacion_1/Regleta.[N1, N2]' --as Linea_CG_a_CD1
```

Status lives on the open Cable/Conductor notes (`OPEN_` ids). No separate
`connections` row.

## Drawing (UI)

- In conduit segments: show the Conduit path; nest Cable sheaths and Conductors
  from `contains`.
- Inside a place canvas: draw Conductors that terminate on an element in that
  place; hide pure sheaths unless pass-through (enters and leaves with no
  terminal landing in that place).

## Cross-location references

Conductor endpoints declared on a place may only refer to elements in **that
place and its nested sublocations** (paths relative to the current place).

- Local: `MT_Luces.1`
- Sublocation: `Cuadro_General/Fuente_portero.S1`
- Absolute **within the same tree**: `/Parking/Caja_derivacion_1/Regleta.N1`

Not allowed (lift the link to the common ancestor):

- `../Salon/Caja_Luces.N1` (walks upward)
- sibling paths declared inside the wrong place

Contained Cable/Conductor ids referenced by a Conduit must be defined in the
**same** place node’s `cables:` map.

## Qualified name prefixes

Internal qualified names join location segments with `__`:

- Place `Parking/Caja_derivacion_1` → element `Regleta` →
  `Parking__Caja_derivacion_1__Regleta`

## Conduit endpoints

- `from` / `to` = `LocationRef.OpeningId` (e.g. `Caja_derivacion_4.W2`,
  `Parking/Caja_derivacion_4.B2-1`, or `.N1` = current place). Required on
  `type: Conduit`.
- Catalog: `catalog/Conduit.yaml` (`kind: conduit_type`).
