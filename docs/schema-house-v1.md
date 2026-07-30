# Schema house/v1

Formato canónico de **housewire** para documentar instalación eléctrica.
`housewire` / `python -m housewire` lo traduce a WireViz y a diagramas físicos.
Un exporter QElectroTech podrá reutilizar el mismo YAML más adelante.

Edición asistida: `housewire shell <proyecto>` o subcomandos `add` / `rm` / `show` (ver README).

Los tipos viven en el paquete: `src/housewire/catalog/`. Las obras van en `projects/`.

## Cabecera

```yaml
schema: house/v1
location: [Planta baja, Recibidor, Cuadro general]  # opcional; si falta, se infiere del path
```

Sin `schema: house/v1`, el archivo se trata como WireViz legacy (como `Test/`).

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

## Aberturas de cajas de derivación

Los agujeros/pasatubos de una caja **no son bornes eléctricos**: se documentan en `conduits.route` y/o `cables.notes`. El cableado eléctrico va a la regleta (`TerminalStrip`) u otro elemento dentro de la caja.

### Identificador: `<cara>[.<desempate>]`

Siempre en **coordenadas del edificio** (N/S/E/W), nunca “izquierda/derecha mirando la tapa” (eso cambia según montaje).

| Código | Significado |
|---|---|
| `N` `S` `E` `W` | Cara lateral en planta |
| `U` | Arriba (hacia el cielo / borde superior en pared) |
| `D` | Abajo (hacia el suelo / borde inferior en pared) |
| `tapa` | Cara de la tapa (acceso) |
| `fondo` | Cara empotrada (opuesta a la tapa) |

**Desempate** si hay varios agujeros en la misma cara: el más cercano a otra dirección, p.ej. `W.N` = cara oeste, agujero más al norte; `W.S` = cara oeste, más al sur. Alternativa: `.1` `.2` numerados de N→S (o de E→W), aclarado en `notes` de la caja.

Ejemplos Parking: cadena C1–C4 en techo sale por `N.E` y entra por `S.E`; C3 enchufes por `E.S` y `N.W`. C5 es la unica en pared (`mount: wall`).

### Montaje (`mount`) — cambia qué es `tapa` / `fondo`

Indicar en `notes` del YAML de la caja o del conduit:

| `mount` | Tapa mira a… | `fondo` es… | Laterales N/S/E/W |
|---|---|---|---|
| `ceiling` | suelo (miras hacia arriba para abrir) | empotrado en el techo | perímetro de la caja en planta |
| `wall` | el local (indicar **hacia qué cardinal mira la tapa**, p.ej. `facing: E`) | dentro de la pared | perímetro; `U`/`D` = alto/bajo en esa pared |
| `floor` | techo (tapa en el suelo) | empotrado en el suelo | perímetro en planta |

En **pared**, sin `facing` las caras se confunden: `facing` = dirección en la que mira la tapa (hacia el local). Ejemplo: caja en pared sur con `facing: N` → `U` es hacia el techo; `E`/`W` siguen siendo este/oeste del edificio.

### Qué no mezclar

- **Abertura** (`W.N`): geometría de la caja (agujero/pasatubo). Va en `route` / `notes`, no como nombre del conducto si se puede evitar.
- **Conducto** (`Conducto_Cuadro_general_a_Caja_derivacion_1`): tubo/manguera entre sitios. Nombrar por extremos (`Conducto_<A>_a_<B>`), no Entrada/Salida ni solo el id de abertura. El sentido eléctrico lo llevan los cables (`Linea_A_a_B`).
- En `route` usar `↔` (o “entre”) y citar la abertura en cada extremo cuando se sepa (`… ↔ Caja_1 abertura W.N ↔ Enchufe_1`).
- **Contenido de caja**: lo que está *dentro* de una caja de derivación vive en el YAML de esa caja (p.ej. `Regleta_1` en `caja_derivacion_1.yaml`) y se deja explícito en `notes` (“Dentro de Caja_derivacion_1”).
- **Borne** (`Regleta_1.1`): conexión eléctrica dentro de la caja.

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
- Describe por dónde pasa en `conduits.route` con aberturas (`W.N`, `E.S`, etc.) y texto `destino pendiente`.

Ejemplo:

```yaml
cables:
  PEND_Linea_Caja_D2_01:
    kind: power
    section: "1.5 mm2"
    colors: [BN, BU]
    notes: "estado: pendiente; entra por W.N y sale por E.S"

conduits:
  Conducto_Caja_D2_paso:
    kind: conduit
    contains: [PEND_Linea_Caja_D2_01]
    route: "Caja_D2 abertura W.N ↔ Caja_D2 abertura E.S ↔ destino pendiente"
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

- Local: `MT_Luces.L`
- Absoluta: `/Planta baja/Recibidor/Cuadro general/MT_Luces.L`
- Relativa: `../Salon/Caja_Luces.L`

## Locations anidadas

Además de subdirectorios, se puede anidar en un solo YAML:

```yaml
schema: house/v1
locations:
  Planta baja:
    Recibidor:
      Cuadro general:
        elements: { ... }
        cables: { ... }
        connections: [ ... ]
```

### Cajas de derivación = carpeta

Si una regleta (u otro aparato) está *dentro* de una caja, pon el YAML en un subdirectorio de esa caja. Así el nombre WireViz lleva el sitio:

- `Parking/Caja derivacion 1/caja.yaml` → elemento `Regleta`
- Prefijo: `Parking__Caja_derivacion_1_Regleta`

Evita `Parking/Regleta_1` (no se ve la caja). Alternativa sin carpetas: id largo `Caja_derivacion_1_Regleta` (peor: duplicas el sitio en el nombre).

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
