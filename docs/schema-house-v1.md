# Schema house/v1

Formato canónico de **housewire** para documentar instalación eléctrica.
`housewire` / `python -m housewire` lo traduce a WireViz y a diagramas físicos.
Un exporter QElectroTech podrá reutilizar el mismo YAML más adelante.

Edición asistida: `housewire shell <proyecto>` o subcomandos `add` / `rm` / `show` (ver README).

Los tipos viven en el paquete: `src/housewire/catalog/`.
Los YAML de una instalación viven en un **directorio/repo de obra aparte** (no en el repo del programa).

## Dos capas (no mezclar)

| Capa | Nodos | Aristas | Export |
|------|-------|---------|--------|
| **Física** | locations (cajas, DeviceBox, Panel, Floor…) | **conduits** entre aberturas (`from` / `to`) | `out/physical/` |
| **Eléctrica** | elements (Socket, Regleta, MCB…) | **connections** con cable como `via` | WireViz |

Puente único: `conduit.contains: [cable_ids]`. El cable viaja en el conducto; la connection une bornes.

```yaml
# Fisica: locations ↔ conduit
conduits:
  Conducto_a_Enchufe_1:
    type: Conduit
    subtype: tube
    from: Caja_derivacion_4.W2
    to: Enchufe_1.N1
    contains: [Linea_a_Enchufe_1]

# Electrica: elements ↔ cable
connections:
  - from: Caja_derivacion_4/Regleta_1.[1, 2, 3]
    via: Linea_a_Enchufe_1.[1, 2, 3]
    to: Enchufe_1/Socket.[L, PE, N]
```

## Cabecera

```yaml
schema: house/v1
```

La **jerarquía** es el path de directorios (o keys anidadas en un YAML).
El fichero `housewire.yaml` **es el objeto place**: mismos campos que un hijo
en `elements` (`type`, `label`, `mount`, `openings`, …), más `schema: house/v1`.

### Ids técnicos vs `label`

| Rol | Qué es el id | Display |
|---|---|---|
| Place (carpeta) | nombre del directorio | `label` opcional en la raiz |
| Place inline | clave en `elements:` | `label` en ese mapa |
| Elemento / cable | clave YAML | `label` opcional |

- **Id**: `[A-Za-z0-9_]+` (p.ej. `Caja_derivacion_4`). Sin espacios. Va en conexiones.
- **`label`**: texto humano. `add location "Caja derivacion 6"` → carpeta
  `Caja_derivacion_6/` con `label: Caja derivacion 6`.

Misma forma en carpeta o anidado:

```yaml
# Garage/Junction_box_1/housewire.yaml  (el fichero ES el place)
schema: house/v1
type: JunctionBox
label: "Junction box 1"
subtype: "100x100 IP40"
mount: ceiling
opening_grid: { NS: 2, WE: 2, B: 1 }
openings: [B1-1, N1]
elements:
  Regleta_1:
    type: TerminalStrip
    label: "Regleta 3 pares"
```

```yaml
# Inline equivalente dentro de otro place
elements:
  Junction_box_1:
    type: JunctionBox
    label: "Junction box 1"
    openings: [B1-1, N1]
    elements:
      Regleta_1:
        type: TerminalStrip
```

Legacy: bloque `location: { type: … }` aún se lee; preferir campos en la raiz.

Sin `schema: house/v1`, el archivo se trata como WireViz legacy (como `Test/`).

## Locations = árbol lógico (outline y/o inline)

**Outline** (recomendado en obra):

```text
Garage/
  housewire.yaml                 # type: Floor + sockets…
  Junction_box_1/
    housewire.yaml               # type: JunctionBox + regletas…
```

**Inline** (escape hatch / monolito): place anidado en `elements:` del YAML ancestro.

El shell (`cd` / `ls` / `pwd`) navega el **árbol de locations**, no el filesystem a ciegas:
hijos outline (carpeta + `housewire.yaml`) e hijos inline (`type` place) aparecen juntos en
`locations:`. Los devices (Socket, MCB, …) van en `elements:`.

Mezcla permitida; **prohibido** el mismo id como carpeta y como key inline a la vez.

Place types (catalog, `wireviz_skip`):

| type | Meaning |
|------|---------|
| `Room` | Habitación / estancia |
| `JunctionBox` | Caja de derivación |
| `DeviceBox` | Caja de mecanismo (enchufe/interruptor; 1-/2-/3-gang) |
| `LightPoint` | Punto de luz (agujero / salida a luminaria) |
| `Panel` | Cuadro eléctrico (también puede declarar `openings`) |
| `Floor` | Planta / nivel (planta baja, parking, …) |
| `House` | Casa / vivienda (no implica ser la raíz del árbol) |
| `Location` | Genérico / inline ocasional |

La **raíz del árbol** es el directorio que pasas a `housewire` (`project_path`),
no un `location.type` concreto. Puedes apuntar a un subárbol o montar carpetas
por encima (p.ej. `Building/…/House/…`) sin cambiar tipos.

- One outline directory → one `housewire.yaml` (no sibling fragment YAMLs).
- `cd` entra en outline o inline; `show` / `add element` actúan sobre el place actual.
- `add location NAME --type T` → outline si el place actual es outline; inline si ya estás
  inline. Fuerza con `--inline` / `--dir` (`--dir` bajo inline no está permitido).

### `install` (surface vs flush)

Opcional en places con `mount`:

| `install` | Significado |
|---|---|
| `surface` | Sobre superficie (caja vista / canaleta); tipico parking |
| `flush` | Empotrado en pared/techo/suelo |

Si se omite, no se asume. No cambia el marco local de aberturas; solo documenta la
instalacion.

### DeviceBox (mecanismos)

```yaml
type: DeviceBox
subtype: 1-gang          # 1-gang | 2-gang | 3-gang
install: surface
mount: wall
facing: S
openings: [N1]           # entrada por cara N (p.ej. parking surface)
elements:
  Socket:
    type: Socket
    subtype: Schuko
```

Varios artefactos en la misma caja (misma boca de entrada):

```yaml
type: DeviceBox
subtype: 2-gang
openings: [N1]
elements:
  Enchufe: { type: Socket, subtype: Schuko }
  Interruptor: { type: Switch, subtype: unipolar }
```

En el shell, sin editar el YAML a mano ni flags por campo:

```text
set install surface
set openings=[N1]
set opening_grid.N=1
add location Interruptor_1 --type DeviceBox --subtype 1-gang \
  --set install=surface --set mount=wall --set openings=[N1]
set --element Switch notes "…"
```

Los valores se interpretan como YAML. Claves estructurales (`elements`, `cables`,
`connections`, `conduits`, `schema`) no se pueden `set`; usa `add`/`rm`.

### Lamparas / puntos de luz

El conducto termina en un place **`LightPoint`** (agujero de techo/pared), no en
un `DeviceBox`. La boca tipica es ``B1-1`` (fondo hacia el forjado) o una cara
de contorno si el tubo llega lateralmente.

```yaml
type: LightPoint
subtype: ceiling-hole    # default de catalogo
install: surface
mount: ceiling
opening_grid:
  B: 1                   # → B1-1
openings: [B1-1]
# elements:              # mas adelante, capa electrica
#   Luminaire: { type: Luminaire, … }
```

```text
add location Lampara_1 --type LightPoint --label "Lampara 1" \
  --set install=surface --set mount=ceiling \
  --set opening_grid.B=1 --set openings=[B1-1]
add conduit Conducto_a_Lampara_1 --from Caja_derivacion_1.E2 --to Lampara_1.B1-1 \
  --contains Linea_a_Lampara_1
```

Reserva `DeviceBox` para cajas de mecanismo reales (enchufe/interruptor).

### Elementos

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
| `Switch` | Interruptor | Mecanismo; fase 1→2 (unipolar por defecto) |

**No es un “disyuntor”** en el sentido de diferencial: en obra a veces se dice “disyuntor” al ID; el magnetotermico es el MCB/PIA.

**IGA vs IGP:** el Moeller C50/2 del cuadro es un **magnetotermico** usado como **IGA** (automatico). Un **IGP** seria un interruptor de corte sin curva C/proteccion; no es lo que hay en la foto.

## Aberturas (JunctionBox, DeviceBox, LightPoint y Panel)

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
# Aberturas → conduit de paso (capa fisica)
conduits:
  Conducto_a_Caja_2:
    type: Conduit
    subtype: tube
    from: .N1
    to: Caja_derivacion_2.S1
    contains: [Linea_a_Caja_derivacion_2]
```

### Qué no mezclar

- **Abertura** (`N1`, `B1-1`): geometría local del place. Va en `from`/`to` del conduit.
- **Conducto**: tubo entre locations (`from: A.N1` → `to: B.S1`).
- **Borne** (`Regleta.1`): conexión eléctrica dentro de la caja (capa eléctrica).

Legacy: ids opacos `B1`/`B2`, cardinales compuestos (`W.N`) y `back`/`lid`/`fondo`/`tapa`
pueden aparecer en texto antiguo; el canónico es `N1` / `B1-1`.

## Cables

```yaml
cables:
  Linea_X:
    type: Cable               # catalog id (cable_type)
    subtype: power            # power | earth | dc | signal | …
    section: "1.5 mm2"        # canónico (QET: conductor_section). WireViz ← gauge
    colors: [BN, BU, GNYE]    # defaults from catalog subtype if omitted
    label: "…"                # optional human name
    notes: "..."
```

Catalog: `catalog/Cable.yaml` (`kind: cable_type`) with per-subtype defaults
(section/colors). ABM `add cable` / `pend` fill missing fields from that catalog.

Legacy: `kind: power` still loads as `subtype: power`.

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
- Describe por dónde pasa en `conduits.from` / `conduits.to` con aberturas
  (`N1`, `B1-1`, …); el destino pendiente puede ser `.S1` u otro place.

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
    type: Cable
    subtype: power
    section: "1.5 mm2"
    colors: [BN, BU]
    notes: "estado: pendiente; entra por N1 y sale por S1"

conduits:
  Conducto_paso_01:
    type: Conduit
    subtype: tube
    from: .N1
    to: .S1
    contains: [PEND_Linea_01]
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

Agrupación **física** entre locations (no es un conductor eléctrico):

```yaml
conduits:
  Conducto_Cuadro_a_Caja:
    type: Conduit             # catalog id (conduit_type)
    subtype: M20              # tube | hose | free | M16 | M20 | …
    from: Cuadro_General.S1   # LocationRef.OpeningId
    to: Caja_Luces_1.N1
    contains: [Cable_Luces_Salon, Cable_Enchufes_Salon]
    label: "…"                # optional
    notes: "..."
```

- `from` / `to` = `LocationRef.OpeningId` (p.ej. `Caja_derivacion_4.W2`,
  `Parking/Caja_derivacion_4.B2-1`, o `.N1` = place actual). Obligatorios.
- Catalog: `catalog/Conduit.yaml`.

Las `connections` (capa eléctrica) siguen yendo a los cables. El conduit se
anota en los cables contenidos al exportar a WireViz; el diagrama **físico**
dibuja aristas solo entre locations vía conduits.

## Salidas al generar

`housewire generate <path>` (o `generate` en el shell tras `cd` a un location):

- `out/<nombre>.*` — WireViz (**capa eléctrica**: elements ↔ cables); extremos fuera del alcance como stub `External`
- `out/physical/<nombre>.svg` — topología **física** (locations ↔ conduits); `.dot` junto al SVG

Para generar solo Parking: `housewire generate $SITE/Parking` o, en el shell, `cd Parking` y `generate`.
