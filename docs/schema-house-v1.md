# Schema house/v1

Canonical format for **housewire**: document a home electrical installation in YAML,
then export WireViz (electrical) and physical topology diagrams.
A future QElectroTech exporter can reuse the same YAML.

Editing: `housewire shell <site>` or non-interactive `add` / `rm` / `show` (see README).

Element and place types live in the package: `src/housewire/catalog/`.
Installation YAML lives in a **separate site directory/repo** (not in the program repo).

## Two layers (do not mix)

| Layer | Nodes | Edges | Export |
|-------|-------|-------|--------|
| **Physical** | locations (`JunctionBox`, `DeviceBox`, `Panel`, `Floor`, …) | **conduits** between openings (`from` / `to`) | `out/physical/` |
| **Electrical** | elements (`Socket`, `TerminalStrip`, `MCB`, …) | **connections** with a cable as `via` | WireViz |

Bridge: `conduit.contains: [cable_ids]`. The cable rides in the conduit; the connection joins terminals.

```yaml
# Physical: locations ↔ conduit
conduits:
  Conducto_a_Enchufe_1:
    type: Conduit
    subtype: tube
    from: Caja_derivacion_4.W2
    to: Enchufe_1.N1
    contains: [Linea_a_Enchufe_1]

# Electrical: elements ↔ cable
connections:
  - from: Caja_derivacion_4/Regleta_1.[1, 2, 3]
    via: Linea_a_Enchufe_1.[1, 2, 3]
    to: Enchufe_1/Socket.[L, PE, N]
```

## Document header

Every editable `housewire.yaml` must declare:

```yaml
schema: house/v1
```

The file **is** the place object: the same fields as a nested place (`type`, `label`,
`mount`, `openings`, …), plus `schema: house/v1`. Hierarchy is the directory tree
(and/or inline places under `elements:`).

### Place id, name, and label

| Field | What | Where | Used for |
|-------|------|-------|----------|
| **id** | Technical key `[A-Za-z0-9_]+` | Directory name / inline key under `elements:` | Refs, paths, `cd`, conduits |
| **name** | Short working name (optional) | YAML `name:` on the place | Canvas, selectors, lists |
| **label** | Human text (optional) | YAML `label:` on the place | Inspector, docs, long tooltips |

Fallbacks:

- Canvas / selectors → `name` → **id**
- Inspector / human display → `label` → `name` → **id**
- Graphviz physical node title → `name` → **id**; `label` may appear in the subtitle if different

Elements / cables / terminals still use their YAML key as id and optional `label` only
(not covered by place `name`).

- **Id**: e.g. `Caja_derivacion_4`. No spaces. Used in refs.
- **`name`**: e.g. `CD4` (canvas).
- **`label`**: e.g. `Caja derivacion 4`. `add location "Caja derivacion 6"` → folder
  `Caja_derivacion_6/` with `label: Caja derivacion 6` (no automatic `name`).

Outline place example:

```yaml
# Garage/Junction_box_1/housewire.yaml
schema: house/v1
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

Equivalent inline place (under a parent `housewire.yaml`):

```yaml
elements:
  Junction_box_1:
    type: JunctionBox
    label: "Junction box 1"
    openings: [B1-1, N1]
    elements:
      Regleta_1:
        type: TerminalStrip
```

## Locations = logical tree (outline and/or inline)

**Outline** (recommended on site):

```text
Garage/
  housewire.yaml                 # type: Floor + …
  Junction_box_1/
    housewire.yaml               # type: JunctionBox + …
```

**Inline**: a place nested under the ancestor’s `elements:` (shell: `add location … --inline`).

The shell (`cd` / `ls` / `pwd`) walks the **location tree**: outline children
(folder + `housewire.yaml`) and inline place-typed children appear together.
Devices (`Socket`, `MCB`, …) stay under `elements:` of the current place.

Mixing outline and inline is allowed; the **same id** must not exist both as a
sibling folder and as an inline key.

Place types (catalog, `wireviz_skip`):

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

A stair is a place in the tree (sibling of the floors it links — the filesystem
has a single parent). Use ``connects`` to name the two ends:

```yaml
type: Stair
label: Escalera Parking — Planta baja
connects: [Parking, Planta_baja]
```

- ``connects``: list of two location refs (usually sibling ``Floor`` ids).
- Optional for generate today; used by docs/UI to show what the stair joins.
- Children (junction boxes, switches, light points) live under the stair folder.

The **tree root** is the directory you pass to `housewire` (`project_path`), not a
particular `type`. You can point at a subtree or insert folders above
(e.g. `Building/…/House/…`) without changing types.

- One outline directory → one `housewire.yaml` (no sibling fragment YAMLs).
- `cd` enters outline or inline; `show` / `add element` act on the current place.
- `add location NAME --type T` → outline when the current place is outline; inline
  when already inline. Force with `--inline` / `--dir` (`--dir` under inline is forbidden).
- Dirty YAML stay in memory across `cd`; `save` writes all dirty buffers; `exit`
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

Values parse as YAML. Structural keys (`elements`, `cables`, `connections`,
`conduits`, `schema`) cannot be `set`; use `add` / `rm`.

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
      "1": { label: "" }
```

Terminal fields: `label`, `direction` (`in` | `out` | `inout`), `role`.

Catalog `wireviz_collapse` pairs terminals for the **WireViz export**: each pair
becomes one visual pin (cables left and right). That is layout only, not WireViz
`loops`, and not necessarily electrical continuity.

### Catalog element types

| type | Role |
|------|------|
| `MCB` | 1P+N miniature circuit breaker. Pins 1→2 (phase), 3→4 (N) |
| `MCB2P` | 2-pole MCB (e.g. main breaker) |
| `RCD` | Residual-current device. Pins 1→2 (phase), 3→4 (N) |
| `Supply` | Incoming supply (L + N) |
| `PETerminal` | PE bar / earth terminal strip |
| `EarthElectrode` | Earth electrode |
| `PowerSupply` | AC/DC supply (e.g. intercom) |
| `Intercom` | Door phone / video door phone (DC +/−) |
| `TerminalStrip` | Terminal strip in a junction box |
| `Socket` | Schuko / 2P+E outlet |
| `Switch` | Switch mechanism; subtypes `unipolar`, `crossover`, `intermediate` |
| `Luminaire` | Lamp / pendant (default terminals 1–3) |
| `Relay` | Smart relay / Zigbee switch (`N`, `LIn`, `LOut`, `S1`, `S2`; subtypes `zbmini_r2`, `mini_zbd`) |

**Switch subtypes**

| subtype | Terminals |
|---------|-----------|
| `unipolar` (default) | `1`, `2` |
| `crossover` (3-way) | `C` (common), `1`, `2` (travellers) |
| `intermediate` | `1`–`4` |

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

Optional UI positions for the interactive physical editor (`housewire serve`):

```yaml
# On any place drawn as a node (JunctionBox, DeviceBox, …)
view:
  physical:
    x: 120
    y: 80
    rotation: 0    # optional: 0 | 90 | 180 | 270

# On the canvas root place (any location that has child places)
views:
  physical:
    width: 2000
    height: 1400
    representation: line   # line | tube
```

- **`view.physical`**: canvas coordinates for that place under its parent canvas.
  ``x`` and ``y`` must be ``>= 0`` (parent-local origin at the content top-left).
- **`views.physical`**: page size and preferred conduit drawing mode for the
  canvas root location (often a `Floor` or `Room`, but any place type works).
- Canvas zoom (pan/wheel) is independent of `representation` (line vs tube).
- **Depth zoom** (`depth` query / toolbar) controls how many nested outline
  levels are drawn inside parent boxes; it does not change representation.
- Back openings (`B…`) are drawn at the symbol center, not as a fourth side.
- Omitted when unused; Graphviz/WireViz generate does not require these fields.

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
conduits:
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
- **Terminal** (`Regleta.1`): electrical connection inside the box.

## Cables

```yaml
cables:
  Linea_X:
    type: Cable
    subtype: power            # power | earth | dc | signal | …
    section: "1.5 mm2"
    colors: [BN, BU, GNYE]
    label: "…"
    notes: "..."
```

Catalog: `catalog/Cable.yaml` (`kind: cable_type`) with per-subtype defaults for
`section` / `colors`. ABM `add cable` / `pend` fill omitted fields from that catalog.

### Color codes (`colors:`)

Codes are **IEC 60757** letter abbreviations (WireViz vocabulary). Use uppercase
in YAML (`BN`, not `bn`).

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
| `WH` | white | Catalog `signal` default (with `BU`) |
| `PK` | pink | Available |
| `TQ` | turquoise | Available |
| `GNYE` | green-yellow | Protective earth (PE) |

- **PE** → `GNYE` (not bare `GN` / `YE`).
- **Neutral** → `BU` (IEC / EU practice).
- **Phase** may be `BK`, `BN`, or `GY`; note mixed phases in the same box.
- Order in `colors: […]` is the wire index for `via: Cable.[1, 2, …]` (1-based).

```yaml
colors: [BN, BU, GNYE]   # wire 1 brown, 2 blue, 3 PE
```

### Logical line ≠ one physical sheath

A `cables` entry with several colors (e.g. `[BN, BU]`) is a **logical line**: the
set of conductors from A to B. WireViz draws it as one multipolar block on purpose
(circuit clarity), not as a claim that it is one jacketed multicore.

In panels these are often **loose singles**. Record construction in:

- `notes` (e.g. loose wires / multicore type / estimated section)
- `conduits` when several cables share a tube

Do not split every bipolar into two `cables` only to look “physical”: diagrams get
noisy without helping L/N tracing.

### Capture recipes

Run from the **parent** place (floor/room) that owns `cables` / `conduits` /
`connections`. Recipes create the destination place (outline by default) plus
wiring in the current YAML.

```text
cd Garage
add socket Outlet_5 --from Junction_2.N1 --strip Regleta
# → DeviceBox Outlet_5 + Socket; Linea_a_Outlet_5 (GY,GNYE,BU);
#   Conducto_a_Outlet_5; Junction_2/Regleta.[3,2,1] → Outlet_5/Socket.[L,PE,N]

add lamp Lamp_3 --from Junction_3.S1 --strip Regleta --pins 6,5,2
# → LightPoint + Luminaire; BN,GNYE,BU → Luminaire.[1,2,3]

add feed Linea_A_a_B --from Junction_4.E1 --to Junction_3.N1 \
  --from-pin Regleta_2.1 --to-pin Regleta.1 --colors BK
```

Overrides: `--pins`, `--colors`, `--section`, `--to-opening`, `--inline` /
`--dir`, `--label`, `--notes`. Socket strip default pins are `3,2,1` (L, PE, N).

### Pending runs (incremental capture)

When a cable enters/leaves a box but the far end is unknown:

- Create the `cable` and its `conduit`, but **omit** `connections` for now.
- Prefix the cable id with `PEND_` while open.
- Put status in cable `notes` (e.g. `status: pending`).
- Set `conduits.from` / `to` with openings (`N1`, `B1-1`, …).

```text
cd Parking/Caja_derivacion_2
pend N1 S1            # defaults 1.5 mm2 / BN,BU
pend N1 S1 2.5
pend                  # prompts for openings
```

```yaml
cables:
  PEND_Linea_01:
    type: Cable
    subtype: power
    section: "1.5 mm2"
    colors: [BN, BU]
    notes: "status: pending; enters N1, leaves S1"

conduits:
  Conducto_paso_01:
    type: Conduit
    subtype: tube
    from: .N1
    to: .S1
    contains: [PEND_Linea_01]
```

When closing:

1. Rename `PEND_*` to the final id (`Linea_<A>_a_<B>`).
2. Replace pending notes with a final note (or remove them).
3. Add definitive `connections` `from` / `via` / `to`.
4. Do not leave `PEND_` ids on closed circuits.

### Open → claim → land (unknown far end)

For a cable that **leaves** a known opening toward a destination you have not
opened yet (distinct from local `pend` pass-through):

```text
cd Planta_baja/Recibidor/Cuadro_General
open S2 1.5 --colors BN,BU
# → OPEN_Linea_01  notes: status: open; leaves …/Cuadro_General.S2
#   (no conduit yet)

cd ../Caja_derivacion_1
claim OPEN_Linea_01 --enter N1 --exit E2
# → conduit leaves → CD1.N1; notes: status: claimed; enters …; exits …

# later, when terminals are known (still finds the cable in the origin YAML):
land OPEN_Linea_01 --from Cuadro_General/MT.2 --to Caja_derivacion_1/Regleta.1 \
  --as Linea_CG_a_CD1
```

- `opens` lists open/claimed runs across the site tree.
- A second `claim` on the same `OPEN_*` continues from the previous `--exit`.
- Prefer opening from the box (or parent) that should own the cable YAML.

## Connections

Canonical form (what the shell writes):

```yaml
connections:
  - from: ID_Fila_Superior.[2, 4]
    via: Linea_ID_Fila_Superior_a_MT_Luces.[1, 2]
    to: MT_Luces.[1, 3]
```

### Cross-location references

Connections in a `housewire.yaml` may only refer to elements in **that location and
its sublocations** (paths relative to the current directory).

- Local: `MT_Luces.1`
- Sublocation: `Cuadro_General/Fuente_portero.+`
- Absolute **within the same tree**: `/Parking/Caja_derivacion_1/Regleta.1` (from under `Parking/`)

Not allowed (lift the connection to the common ancestor):

- `../Salon/Caja_Luces.L` (walks upward)
- `/Parking/Caja_2/Regleta.1` declared inside `Parking/Caja_1/` (sibling)

The `via` cable must be defined in the **same** location document as the connection.

## WireViz name prefixes

The folder path defines the export prefix:

- `Parking/Caja_derivacion_1/housewire.yaml` → element `Regleta` →
  `Parking__Caja_derivacion_1__Regleta`

## Conduits

Physical grouping between locations (not an electrical conductor):

```yaml
conduits:
  Conducto_Cuadro_a_Caja:
    type: Conduit
    subtype: tube             # tube | hose | free | M16 | M20 | M25 | M32 | …
    from: Cuadro_General.S1
    to: Caja_Luces_1.N1
    contains: [Cable_Luces_Salon, Cable_Enchufes_Salon]
    label: "…"
    notes: "..."
```

- `from` / `to` = `LocationRef.OpeningId` (e.g. `Caja_derivacion_4.W2`,
  `Parking/Caja_derivacion_4.B2-1`, or `.N1` = current place). Required.
- Catalog: `catalog/Conduit.yaml`.

Electrical `connections` still target cables. Contained cables are annotated for
WireViz; the **physical** diagram draws edges only between locations via conduits.

## Generate outputs

`housewire generate <path>` (or shell `generate` after `cd`):

- `out/<name>.*` — WireViz (**electrical**: elements ↔ cables); out-of-scope ends as `External` stubs
- `out/physical/<name>.svg` — **physical** topology (locations ↔ conduits); `.dot` beside the SVG

Generate only a subtree: `housewire generate $SITE/Parking` or `cd Parking` then `generate`.
