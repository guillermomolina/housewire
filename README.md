# housewire

Documenta instalaciones eléctricas en YAML (`schema: house/v1`) y genera diagramas:

- **WireViz** (detalle de bornes / cables)
- **Topología física** (cajas, conductos, aberturas)
- Futuro: QElectroTech u otros exporters

El código vive en el paquete Python `housewire`. Los datos de obra van en `projects/` (no mezclados con el programa).

## Requisitos

- Python 3.10+
- Graphviz (`dot` en el `PATH`)

```bash
sudo pacman -S graphviz   # Arch
```

## Instalación

```bash
python -m venv .venv --prompt housewire
source .venv/bin/activate
python -m pip install -e .
```


## Shell y ABM

Modo interactivo (REPL, sin menús TUI):

```bash
housewire shell "projects/Margalló 4A"
```

Comandos: `cd`, `ls`, `pwd`, `use <archivo.yaml>`, `show`, `pend`, `add`, `rm`, `generate`, `help`, `exit`.

Captura rápida delante de una caja (cable pendiente sin destino):

```bash
housewire shell "projects/Margalló 4A"
cd Parking/Caja\ derivacion\ 2   # auto-activa el YAML si solo hay uno
pend W.N E.S                     # crea PEND_Linea_01 + Conducto_paso_01
pend N.E S.W 2.5                 # misma cosa con sección 2.5 mm2
```

`add cable` usa defaults (`1.5 mm2`, `BN,BU`) si no pasas `--section` / `--colors`.

Subcomandos (scripts / Makefile):

```bash
housewire generate -f "projects/Margalló 4A"
housewire ls "projects/Margalló 4A" "Parking"
housewire show "projects/Margalló 4A" "Planta baja/Recibidor/Cuadro general/cuadro_general.yaml"
housewire add element "projects/Margalló 4A" "…/cuadro_general.yaml" MT_Nuevo --type MCB --subtype C10
housewire add pend "projects/Margalló 4A" "…/caja.yaml" W.N E.S
housewire rm element "projects/Margalló 4A" "…/cuadro_general.yaml" MT_Nuevo
```

La ruta `housewire <proyecto> -f` sigue funcionando como atajo de `generate`.

## Generar un proyecto de obra

```bash
housewire -f "projects/Margalló 4A"
# o
python -m housewire -f "projects/Margalló 4A"
```

Salida dentro de `projects/Margalló 4A/out/`:

| Ruta | Contenido |
|---|---|
| `out/<proyecto>.svg` | WireViz **total** |
| `out/zones/<zona>.svg` | WireViz **por zona** (Parking, Cuadro_general, …) |
| `out/physical/<zona>.svg` | Topología **física** (sin tablas de pines) |

Por defecto se generan zonas + físico (`--zones`). Solo el total: `--no-zones`.

Makefile:

```bash
make prepare          # venv + install editable + pytest (dev-requirements.txt)
```

## Estructura del repo

```
src/housewire/          # paquete
  cli.py                # CLI
  catalog/              # tipos (MCB, RCD, Socket, …)
  house/                # schema house/v1 + exporters
projects/               # obras (YAML de instalación)
  Margalló 4A/
docs/                   # schema-house-v1.md
```

## house/v1

Ver [docs/schema-house-v1.md](docs/schema-house-v1.md).

```yaml
schema: house/v1
elements:
  MT_Luces:
    type: MCB
    subtype: C10
cables:
  Linea_X:
    kind: power
    section: "1.5 mm2"
    colors: [BN, BU]
connections:
  - from: A.[1, 3]
    via: Linea_X.[1, 2]
    to: B.[1, 3]
```

## Version

La versión del paquete está en `pyproject.toml` / `housewire.__version__` (ahora **0.1.0**).
