# housewire

Document electrical installations in YAML (`schema: house/v1`) and generate diagrams:

- **WireViz** (terminals / cables)
- **Physical topology** (boxes, conduits, openings)
- Future: QElectroTech or other exporters

This repository is the **program only**. Site/installation YAML lives in a **separate** (often private) repository or directory. Do not commit private site data into this repo.

## Requirements

- Python 3.10+
- Graphviz (`dot` on `PATH`)

```bash
sudo pacman -S graphviz   # Arch
```

## Install

```bash
python -m venv .venv --prompt housewire
source .venv/bin/activate
python -m pip install -e '.[dev,ui]'
# or: make prepare
```

Point the CLI at any site directory (outside this repo):

```bash
export SITE="$HOME/electrical-sites/my-site"
```

## Interactive physical UI

```bash
housewire serve "$SITE"
# → http://127.0.0.1:8765/
```

Drag places on a location canvas (any place with child locations), auto-layout,
toggle conduit `line`/`tube`, then **Save**. Canvas zoom (`+`/`−`/wheel) is
separate from **depth zoom** (`depth −`/`+` or Alt+wheel), which nests more
children inside parent boxes. **Elements** / **Cables** toggles show the
electrical LOD on the same canvas (element symbols inside places; connection
edges). Click a box or element for the side panel (inspector + socket/lamp/feed
recipes). Place positions go to `view.physical`; element positions to
`view.electrical`; page settings to `views.physical` on the canvas root.
Requires the `ui` optional dependency (included in `.[dev,ui]` / `make prepare`).

## Shell and ABM

Interactive REPL (no TUI menus):

```bash
housewire shell "$SITE"
```

Commands: `cd`, `ls`, `pwd`, `use`, `show`, `pend`, `add` (incl. `add location`, recipes), `rm`, `generate`, `help`, `exit`.
Tab completes commands, subcommands, and paths. **One nested `housewire.yaml`** at the site root holds the whole place tree under `elements:`. `add location NAME --type JunctionBox` inserts a place under the current location (in memory → `save`).

```bash
housewire shell "$SITE"
cd "Ground floor/Hall"     # logical path inside the site YAML
show
cd "Main panel"
show
```

Recipes (run from the **parent** floor/room where cables live):

```bash
cd Garage
add socket Outlet_5 --from Junction_2.N1 --strip Regleta
add lamp Lamp_3 --from Junction_3.S1 --strip Regleta --pins 6,5,2
add feed Linea_A_a_B --from Junction_4.E1 --to Junction_3.N1 \
  --from-pin Regleta_2.1 --to-pin Regleta.1 --colors BK
```

Unknown far end (leave a panel, claim at the next box later):

```bash
cd "Ground floor/Hall/Main panel"
open S2 1.5 --colors BN,BU          # OPEN_Linea_01
cd ../Junction_1
claim OPEN_Linea_01 --enter N1 --exit E2
land OPEN_Linea_01 --from Main_panel/MT.2 --to Junction_1/Regleta.1 \
  --as Linea_panel_a_J1
opens                               # list still-open runs
```

Fast capture at a junction box (pending cable, destination unknown):

```bash
housewire shell "$SITE"
cd "Garage/Junction box 2"   # logical path in the site YAML
pend N1 S1                 # creates PEND_Linea_01 + Conducto_paso_01
pend N1 S1 2.5
```

`add cable` defaults to `1.5 mm2` / `BN,BU` when `--section` / `--colors` are omitted.

Non-interactive subcommands:

```bash
housewire generate -f "$SITE"
housewire ls "$SITE" "Garage"
housewire show "$SITE" housewire.yaml
housewire add element "$SITE" housewire.yaml MT_New --type MCB --subtype C10
housewire add location "$SITE" Junction_9 --type JunctionBox --under Garage
housewire rm element "$SITE" housewire.yaml MT_New
```

## Generate diagrams

```bash
housewire generate -f "$SITE"
# or
python -m housewire -f "$SITE"
```

Output under `$SITE/out/`:

| Path | Content |
|---|---|
| `out/<name>.svg` | WireViz (electrical: elements ↔ cables) |
| `out/physical/<name>.svg` | Physical topology (locations ↔ conduits) |

Scope is the path argument (or the shell current location’s directory). Example:
`housewire generate "$SITE/Parking"` or `cd Parking` then `generate` in the shell.

```bash
make prepare          # venv + pip install -e '.[dev,ui]'
make test
```

## Repository layout (this repo)

```
src/housewire/          # package
  cli.py
  catalog/              # types (MCB, RCD, Socket, …)
  house/                # house/v1 schema + exporters
docs/                   # schema-house-v1.md
tests/
```

Site trees (private) are **not** part of this repository. A local `projects/` path is gitignored if present for convenience; prefer a separate clone/checkout for real work.

## house/v1

See [docs/schema-house-v1.md](docs/schema-house-v1.md) (IEC **cable color codes**, openings, conduits, connections).

```yaml
schema: house/v1
# Electrical
elements:
  MT_Lights:
    type: MCB
    subtype: C10
cables:
  Line_X:
    type: Cable
    subtype: power
    section: "1.5 mm2"
    colors: [BN, BU]
connections:
  - from: A.[1, 3]
    via: Line_X.[1, 2]
    to: B.[1, 3]
# Physical
conduits:
  Tube_A_to_B:
    type: Conduit
    subtype: tube
    from: Box_A.N1
    to: Box_B.S1
    contains: [Line_X]
```

## Version

Package version: `pyproject.toml` / `housewire.__version__` (currently **0.16.9**).
History: [CHANGELOG.md](CHANGELOG.md).
