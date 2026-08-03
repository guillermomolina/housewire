<p align="center">
  <img src="src/housewire/ui/static/logo.svg" alt="HouseWire" width="96" height="96">
</p>

# HouseWire

Document electrical installations in YAML (`schema: house/v2`) and edit them
with the interactive UI and shell (physical canvas + electrical wiring).

This repository is the **program only**. Site/installation YAML lives in a **separate** (often private) repository or directory. Do not commit private site data into this repo.

## License

**Server Side Public License v1 (SSPL-1.0)** — see [LICENSE](LICENSE).
Copyright (c) 2026 Guillermo Adrián Molina.

You may use, modify, and self-host HouseWire under the SSPL. If you offer
HouseWire (or a modified version) to third parties **as a service**, the SSPL
requires you to make the complete Service Source Code available under the SSPL
(not only the HouseWire program itself). Site/installation YAML you author
remains your data; this license covers the HouseWire software in this
repository. The bundled ``housewire-examples`` package uses the same license.

## Requirements

- Python 3.10+

## Install

```bash
python -m venv .venv --prompt HouseWire
source .venv/bin/activate
python -m pip install -e '.[dev,ui,examples,catalog]'
# or: make prepare
```

`examples` installs [`packages/housewire-examples`](packages/housewire-examples)
(public demo sites). `catalog` / `dev` / `examples` pull
[`housewire-catalog`](https://github.com/guillermomolina/housewire-catalog)
so type YAML is available without a manual clone. Private installation YAML
still lives outside this repo.

### Type catalog

Element / place / cable types live in the **`housewire-catalog`** package
(separate repo and SemVer). Normal path:

```bash
pip install 'housewire[catalog]'
# or with a local clone for overrides:
pip install -e catalogs/default
```

Optional path overrides (still supported):

```bash
mkdir -p catalogs
git clone https://github.com/guillermomolina/housewire-catalog.git catalogs/default
export HOUSEWIRE_CATALOG=/path/to/housewire-catalog
# or: housewire serve --catalog /path/to/housewire-catalog "$SITE"
```

Site-specific overlays: `$SITE/catalog/*.yaml` (shallow merge by `id`). Optional
site field `catalog: default` (or a path) in the site YAML.

Point the CLI at a site YAML file (or its directory) outside this repo:

```bash
export SITE="$HOME/electrical-sites/my-site/my-site.yaml"
```

## Interactive physical UI

```bash
housewire serve "$SITE"
# → http://127.0.0.1:8765/
```

Public demo (after `pip install -e packages/housewire-examples` or `.[examples]`):

```bash
housewire serve "$(python -c 'from housewire_examples import site_yaml; print(site_yaml())')"
```

Drag places on a location canvas (any place with child locations), auto-layout,
then **Save**. Conduits always draw as tubes. Canvas zoom (`+`/`−`/wheel) is
separate from **depth zoom** (`depth −`/`+` or Alt+wheel), which nests more
children inside parent boxes. **Electrical** (View menu / toolbar bolt) toggles elements and cables on
the same canvas (off by default). Edit/View menus and an icon toolbar cover
open/save, undo/redo, zoom, and depth. **Edit → Insert** opens a modal for
socket / lamp / feed (Element / Cable / Conduit placeholders for later).
Click a box or element for the **Properties** inspector (editable name, label,
type, notes, …). Place positions go to
`view.physical`; element positions to `view.electrical`; page settings to
`views.physical` on the canvas root.
Requires the `ui` optional dependency (included in `.[dev,ui]` / `make prepare`).
Document vs view model: [docs/ui-workspace.md](docs/ui-workspace.md).

## Shell and ABM

Interactive REPL (no TUI menus):

```bash
housewire shell "$SITE"
```

Commands: `cd`, `ls`, `pwd`, `use`, `show`, `pend`, `add` (incl. `add location`, recipes), `rm`, `save`, `help`, `exit`.
Tab completes commands, subcommands, and paths. **One site YAML** at the site root
holds the whole place tree under `elements:` (any ``.yaml`` / ``.yml`` name).
`add location NAME --type JunctionBox` inserts a place under the current location
(in memory → `save`).

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
  --from-pin Regleta_2.N1 --to-pin Regleta.N1 --colors BK
```

Unknown far end (leave a panel, claim at the next box later):

```bash
cd "Ground floor/Hall/Main panel"
open S2 1.5 --colors BN,BU          # OPEN_Linea_01
cd ../Junction_1
claim OPEN_Linea_01 --enter N1 --exit E2
land OPEN_Linea_01 --from 'Main_panel/MT.[N2, N3]' --to 'Junction_1/Regleta.[N1, N2]' \
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
housewire ls "$SITE" "Garage"
housewire show "$SITE" my-site.yaml
housewire add element "$SITE" my-site.yaml MT_New --type MCB --subtype C10
housewire add location "$SITE" Junction_9 --type JunctionBox --under Garage
housewire rm element "$SITE" my-site.yaml MT_New
```

```bash
make prepare          # venv + catalog + examples + pip install -e '.[dev,ui,examples,catalog]'
make test             # unit tests, then route E2E in parallel (xdist)
make test-route-e2e-smoke   # optional cheap subset
```

## Repository layout (this repo)

```
src/housewire/          # package
  cli.py
  house/                # house/v2 schema + validation
  ui/                   # interactive canvas
docs/                   # schema-house-v2.md
tests/
```

Site trees (private) are **not** part of this repository. A local `sites/` path is gitignored if present for convenience; prefer a separate clone/checkout for real work.

## house/v2

See [docs/schema-house-v2.md](docs/schema-house-v2.md) (unified `cables` map, IEC color codes, openings).
Documents with `schema: house/v1` are rejected; there is no dual-read.

```yaml
schema: house/v2
elements:
  MT_Lights:
    type: MCB
    subtype: C10
cables:
  Tube_A_to_B:
    type: Conduit
    subtype: tube
    from: Box_A.N1
    to: Box_B.S1
    contains: [Line_X]
  Line_X:
    type: Cable
    subtype: power
    color: BK
    contains: [Line_X_1, Line_X_2]
  Line_X_1:
    type: Conductor
    color: BN
    section: "1.5 mm2"
    from: A.N1
    to: B.N1
  Line_X_2:
    type: Conductor
    color: BU
    section: "1.5 mm2"
    from: A.N3
    to: B.N3
```

## Version

Package version: `pyproject.toml` / `housewire.__version__`.
History: [CHANGELOG.md](CHANGELOG.md).
