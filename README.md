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
python -m pip install -e .
# or: make prepare
```

Point the CLI at any site directory (outside this repo):

```bash
export SITE="$HOME/electrical-sites/my-site"
```

## Shell and ABM

Interactive REPL (no TUI menus):

```bash
housewire shell "$SITE"
```

Commands: `cd`, `ls`, `pwd`, `use`, `show`, `pend`, `add` (incl. `add location`), `rm`, `generate`, `help`, `exit`.
Tab completes commands, subcommands, and paths. **Places are directories** with a single `housewire.yaml` (root `type:` place). `add location NAME --type JunctionBox` creates that directory and file.

```bash
housewire shell "$SITE"
cd "Ground floor/Hall"     # auto-use housewire.yaml
show
cd "Main panel"
show
```

Fast capture at a junction box (pending cable, destination unknown):

```bash
housewire shell "$SITE"
cd "Garage/Junction box 2"   # auto-activates housewire.yaml
pend N1 S1                 # creates PEND_Linea_01 + Conducto_paso_01
pend N1 S1 2.5
```

`add cable` defaults to `1.5 mm2` / `BN,BU` when `--section` / `--colors` are omitted.

Non-interactive subcommands:

```bash
housewire generate -f "$SITE"
housewire ls "$SITE" "Garage"
housewire show "$SITE" "Ground floor/Hall/housewire.yaml"
housewire add element "$SITE" "…/housewire.yaml" MT_New --type MCB --subtype C10
housewire add pend "$SITE" "…/housewire.yaml" N1 S1
housewire rm element "$SITE" "…/housewire.yaml" MT_New
```

Legacy shortcut `housewire <site> -f` still maps to `generate`.

## Generate diagrams

```bash
housewire generate -f "$SITE"
# or
python -m housewire -f "$SITE"
```

Output under `$SITE/out/` (or under the directory you pass / shell `cd` into):

| Path | Content |
|---|---|
| `out/<name>.svg` | WireViz (electrical: elements ↔ cables) |
| `out/physical/<name>.svg` | Physical topology (locations ↔ conduits) |

Scope is the path argument (or the shell current location’s directory). Example:
`housewire generate "$SITE/Parking"` or `cd Parking` then `generate` in the shell.

```bash
make prepare          # venv + editable install + pytest (dev-requirements.txt)
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

See [docs/schema-house-v1.md](docs/schema-house-v1.md).

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

Package version: `pyproject.toml` / `housewire.__version__` (currently **0.16.0**).
History: [CHANGELOG.md](CHANGELOG.md).
