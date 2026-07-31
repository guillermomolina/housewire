# Schema house/v1

Formato canónico de **housewire** para documentar instalación eléctrica.
`housewire` / `python -m housewire` lo traduce a WireViz y a diagramas físicos.
Un exporter QElectroTech podrá reutilizar el mismo YAML más adelante.

Edición asistida: `housewire shell <proyecto>` o subcomandos `add` / `rm` / `show` (ver README).

Los tipos viven en el paquete: `src/housewire/catalog/`.
Los YAML de una instalación viven en un **directorio/repo de obra aparte** (no en el repo del programa).

## Cabecera

```yaml
schema: house/v1
```

La **jerarquía de ubicaciones es el path de directorios**.
El bloque top-level **`location:`** es metadatos del directorio actual
(`type: Room|JunctionBox|Panel|Zone|House`, `subtype`, `notes`, …),
no una lista de path.

Sin `schema: house/v1`, el archivo se trata como WireViz legacy (como `Test/`).

## Locations = directories + housewire.yaml

Each place (room, junction box, panel, zone…) is a **directory** with a single **`housewire.yaml`**:

```text
Garage/
  housewire.yaml                 # location: + sockets, lights, …
  Junction box 1/
    housewire.yaml               # location: + terminal strips…
Ground floor/Hall/
  housewire.yaml
  Main panel/
    housewire.yaml
```

```yaml
# Garage/Junction box 1/housewire.yaml
schema: house/v1
location:
  type: JunctionBox
  subtype: "100x100 IP40"
  mount: ceiling
  opening_grid:
    NS: 2
    WE: 2
    B: 1
  openings: [B1-1, N1]
  notes: "…"
elements:
  Regleta_1:
    type: TerminalStrip
```

Place types (catalog, `wireviz_skip`):

| type | Meaning |
|------|---------|
| `Room` | Habitación / estancia |
| `JunctionBox` | Caja de derivación |
| `Panel` | Cuadro eléctrico (también puede declarar `openings`) |
| `Zone` | Zona / planta / parking |
| `House` | Casa / vivienda (no implica ser la raíz del árbol) |
| `Location` | Genérico (legacy / inline) |

La **raíz del árbol** es el directorio que pasas a `housewire` (`project_path`),
no un `location.type` concreto. Puedes apuntar a un subárbol o montar carpetas
por encima (p.ej. `Building/…/House/…`) sin cambiar tipos.

- One directory → one `housewire.yaml` (no sibling fragment YAMLs).
- Grow by adding a **subdirectory** place, not another file beside `housewire.yaml`.
- `cd` auto-activates `housewire.yaml`; `show` prints `location:` + that file’s content.
- `add location "Main panel" --type Panel` creates the folder and `housewire.yaml`.

## Elementos

```yaml
elements:
  MT_Luces:
    type: MCB                 # magnetotermico 1P+N (ingles: MCB)
    subtype: C10
    manufacturer: Merlin Gerin
    model: multi9
    serial: null
    label: LUZ
    notes: "..."
    terminals:                # opcional; sobrescribe el catalogo
      "1": { label: "" }      # Merlin Gerin: fase a menudo sin letra
```

Campos de borne: `label`, `direction` (`in` | `out` | `inout`), `role`.

En el catálogo, `wireviz_collapse` (análogo a `qet_hint`) empareja bornes para el **export WireViz**: cada par se colapsa en un solo pin visual (cables a izquierda y derecha). No son los `loops` nativos de WireViz (dibujan arcos raros) ni implican necesariamente continuidad eléctrica (p.ej. en `PowerSupply`, L↔+ es solo layout).

### Que es cada tipo (catalog/)

| type | Espanol | Que protege / hace |
|---|---|---|
| `MCB` | Magnetotermico 1P+N (PIA) | Sobrecarga/cortocircuito. Pines 1→2 (fase), 3→4 (N); labels carcasa 1/2/N/N |
| `MCB2P` | Magnetotermico bipolar | Bornes 1→2 y 3→4. En el cuadro: IGA Moeller C50/2 |
| `RCD` | Diferencial (ID) | Fugas. Pines 1→2 (fase, a menudo sin letra), 3→4 (N) |
| `Supply` | Acometida | Entrada de red |
| `PETerminal` | Bornera PE | Reparto de tierra |
| `EarthElectrode` | Jabalina | Toma de tierra |
| `PowerSupply` | Fuente AC/DC | Portero, etc. |
| `Intercom` | Portero eléctrico | Alimentación DC (+/−) |
| `TerminalStrip` | Regleta / bornes | Empalme en caja de derivación |
| `Socket` | Toma Schuko | Enchufe 2P+T |

**No es un “disyuntor”** en el sentido de diferencial: en obra a veces se dice “disyuntor” al ID; el magnetotermico es el MCB/PIA.

**IGA vs IGP:** el Moeller C50/2 del cuadro es un **magnetotermico** usado como **IGA** (automatico). Un **IGP** seria un interruptor de corte sin curva C/proteccion; no es lo que hay en la foto.

## Aberturas (JunctionBox y Panel)

Los agujeros/pasatubos **no son bornes eléctricos**. Se identifican en el
**marco local de la caja** (como el poker): mirando la tapa (`F`).

```text
        N
    W   F   E
        S
         ↓
         B   (fondo / empotrado)
```

`mount` + `facing` anclan ese marco al edificio. Al escribir bocas piensas en
la caja, no en el norte geográfico.

### Ids

| Cara | Id | Orden |
|---|---|---|
| Contorno `N`/`S`/`E`/`W` | `N1`, `W2`, … | `N`/`S`: W→E · `E`/`W`: N→S |
| Fondo `B` / tapa `F` | `B1-1`, `F2-3`, … | 1.er índice N→S, 2.º W→E |

```yaml
location:
  type: JunctionBox
  subtype: "100x100 IP40"
  mount: ceiling          # ceiling | wall | floor
  # facing: N             # wall: hacia dónde mira F (hacia el local)
  opening_grid:
    NS: 3                 # ≡ N: 3x1 y S: 3x1 (entero = 1 fila)
    WE: 2                 # ≡ W y E (orden W→E, como NS)
    B: 2                  # ≡ B: 2x1 → B1-1, B1-2
  openings: [B1-1, W1, N1]
```

- **`openings`**: lista de bocas **usadas** (sin objetos vacíos).
- **`opening_grid`**: plantilla opcional por cara. Claves: `N` `S` `E` `W` `F` `B`,
  o pares `NS` / `WE` (mismo orden que los índices: N→S, W→E). Un entero `3` = `3x1`.
  `3x2` = 3 columnas (W→E) × 2 filas (N→S). Una cara omitida = sin rejilla conocida.
  Cara explícita pisa al par.

Si `openings` está declarado, `pend` exige que entrada/salida existan en la lista.
Si además hay `opening_grid`, cada id debe caber en la rejilla de su cara.

### Montaje

| `mount` | `F` mira a… | `B` es… | Contorno local N/S/E/W |
|---|---|---|---|
| `ceiling` | suelo | empotrado en el techo | perímetro (poker al mirar F desde abajo) |
| `wall` | el local (`facing:`) | dentro de la pared | N local = borde “arriba” de la vista de F |
| `floor` | techo | empotrado en el suelo | perímetro al mirar F |

### Uso

```text
pend N1 S1
```

```yaml
conduits:
  Conducto_a_Caja_2:
    route: "abertura N1 ↔ Caja derivacion 2 abertura S1"
    contains: [Linea_a_Caja_derivacion_2]
```

### Qué no mezclar

- **Abertura** (`N1`, `B1-1`): geometría local. Va en `route` / `notes`.
- **Conducto**: tubo entre sitios (`Conducto_<A>_a_<B>`).
- **Borne** (`Regleta.1`): conexión eléctrica dentro de la caja.

Legacy: ids opacos `B1`/`B2`, cardinales compuestos (`W.N`) y `back`/`lid`/`fondo`/`tapa`
pueden aparecer en texto antiguo; el canónico es `N1` / `B1-1`.

## Cables

```yaml
cables:
  Linea_X:
    kind: power               # power | earth | dc | signal...
    section: "1.5 mm2"        # canónico (QET: conductor_section). WireViz ← gauge
    colors: [BN, BU, GNYE]
    notes: "..."
```

### Convención: línea lógica ≠ un solo cable físico

En el cuadro (y en general en este repo) una entrada de `cables` con varios colores (p.ej. `[BN, BU]`) es una **línea lógica**: el par de conductores que va de A a B. WireViz la dibuja como un bloque multipolar; eso es **intencional** (claridad del circuito), no una afirmación de que sea una manguera o un solo revestimiento.

En la práctica del cuadro suelen ser **hilos sueltos** (fase y neutro separados). Si hace falta dejar constancia de la construcción física:

- `notes`: p.ej. `"hilos sueltos"` / `"manguera RVK"` / sección estimada
- `conduits`: cuando varios cables comparten tubo/manguera de paso

No partas cada bipolar en dos `cables` solo para “ser realista”: el diagrama se vuelve ruidoso y no aporta al seguimiento L/N. Reserva el detalle físico a notas/conduits (y, más adelante, a QElectroTech si hace falta).

### Convención para tramos pendientes (documentación incremental)

Para poder cargar obra “incompleta” sin bloquearte:

- Si un cable **entra/sale por caja** pero aún no sabes destino, crea el `cable` y su `conduit`, pero **no** añadas `connections` todavía.
- Usa prefijo `PEND_` en id de cable mientras esté abierto.
- Marca estado en `notes` de cable: `estado: pendiente`.
- Describe por dónde pasa en `conduits.route` con aberturas (`N1`, `B1-1`, …) y texto `destino pendiente`.

Desde el shell (recomendado en obra):

```text
cd Parking/Caja derivacion 2
pend N1 S1            # defaults 1.5 mm2 / BN,BU
pend N1 S1 2.5        # sección distinta
pend                  # pregunta aberturas por stdin
```

Ejemplo YAML resultante:

```yaml
cables:
  PEND_Linea_01:
    kind: power
    section: "1.5 mm2"
    colors: [BN, BU]
    notes: "estado: pendiente; entra por N1 y sale por S1"

conduits:
  Conducto_paso_01:
    kind: conduit
    contains: [PEND_Linea_01]
    route: "abertura N1 ↔ abertura S1 ↔ destino pendiente"
```

Al cerrar el pendiente:

1. Renombra `PEND_*` a nombre definitivo (`Linea_<A>_a_<B>`).
2. Sustituye `estado: pendiente` por una nota final (o bórrala).
3. Añade `connections` `from/via/to` definitivas.
4. Evita dejar ids `PEND_` en circuitos cerrados.

## Conexiones

Forma compacta:

```yaml
connections:
  - from: ID_Fila_Superior.[L, N]
    via: Linea_ID_Fila_Superior_a_MT_Luces.[1, 2]
    to: MT_Luces.[L, N]
```

También se acepta la lista estilo WireViz.

### Referencias entre niveles

Las conexiones de un `housewire.yaml` **solo pueden referir elementos de esa location
y de sus sublocations** (paths relativos al directorio actual).

- Local: `MT_Luces.L`
- Sublocation: `Cuadro General/Fuente_portero.+` o `./Cuadro General/Fuente_portero.+`
- Absoluta **dentro del mismo árbol**: `/Parking/Caja 1/Regleta.1` (desde `Parking/`)

No permitido (hay que subir la conexión al ancestro común):

- `../Salon/Caja_Luces.L` (sale hacia arriba)
- `/Parking/Caja 2/Regleta.1` declarado en `Parking/Caja 1/` (hermano)

El `via` debe ser un cable **definido en la misma location** que la conexión.

## Locations anidadas (inline, escape hatch)

Lo recomendado es **siempre directorios + housewire.yaml**. Como escape hatch en un solo fichero aún se admite:

- `locations: { Nombre: { elements: … } }`
- o un elemento `type: JunctionBox` / `Room` / `Location` con `elements`/`cables` anidados

Prefiere no mezclarlo con el layout de obra real.

### Prefijos WireViz

El path de carpetas define el prefijo:

- `Parking/Caja derivacion 1/housewire.yaml` → elemento `Regleta` → `Parking__Caja_derivacion_1__Regleta`

## Conduits / mangueras

Agrupación física (no es un conductor):

```yaml
conduits:
  Manguera_Cuadro_a_Caja_Luces_1:
    kind: conduit
    type: M20
    contains: [Cable_Luces_Salon, Cable_Enchufes_Salon]
    route: "falso techo → caja"
```

Las `connections` siguen yendo a los cables. El conduit se anota en los cables contenidos al exportar a WireViz.

## Salidas al generar

`housewire` (con `--zones`, por defecto):

- `out/<proyecto>.*` — WireViz de **todo** el proyecto de obra
- `out/zones/<zona>.*` — WireViz de una zona (`Parking`, `Cuadro_general`); elementos fuera de zona aparecen como stub `External`
- `out/physical/<zona>.svg` — diagrama de **topología física** (clusters por carpeta, sin pines); `.dot` junto al SVG para depurar
