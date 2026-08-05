# Cable routing rules (canvas)

These rules define what **correct** physical/electrical canvas routing looks
like for HouseWire. Detectors live in
[`housewire.ui.route_quality`](../src/housewire/ui/route_quality.py); the hop
assembler (`cableBaseSubpaths`) lives in
[`app/03-routing.js`](../src/housewire/ui/static/app/03-routing.js)
(bundled into [`app.js`](../src/housewire/ui/static/app.js); run ``make bundle-ui``).
End-to-end checks paint a site and call
`assess_live_canvas` on the SVG paths.

English only in this document (program/docs language). Site YAML labels may
use any language.

## Geometry model

A cable hop is three phases:

1. **Head (inbox)** — element pin → mouth fan → opening mouth  
2. **Tube (exterior)** — parallel lane along the conduit centerline, mouth to mouth  
3. **Tail (inbox)** — mouth → mouth fan → element pin  

Phases are concatenated. Full-path rewrite passes (strip / preserve / splice
on the whole chain) must not undo mouth transit or collapse lanes.

## Rules

### Conduit / tube

1. **Envelope** — Mid-tube strand vertices stay inside the conduit stroke
   (distance to centerline ≤ half tube width + small margin).
2. **Mouth transit** — Every strand that uses a tube must pass within a few
   pixels of **both** painted tube endpoints (the bocas).
3. **No early side exit** — Do not leave the tube corridor before the mouth
   (no peeling through the tube wall).
4. **Parallel lanes** — Multiple strands in one conduit use separated
   offsets (`laneDist`); they must not stack on the same mid-run centerline.
   When a hop runs **opposite** the conduit edge direction, reverse the
   centerline for routing but **negate** `laneDist` so `offsetOrthoPts`
   normals stay on the same world side of the tube (otherwise some strands
   stack and others leave empty slots).
5. **Raw centerline** — Hop exterior follows the conduit path; do not drop
   tube segments that skim place borders (`exteriorPathD` must not truncate
   bocas).

### Inbox (inside a place)

6. **Fan after the mouth** — Lane separation in free space happens **after**
   exiting the boca (mouth → stub → lateral/depth fan), never by offsetting
   through the tube wall.
7. **Fan toward the pin** — Mouth fans point into the place (toward the
   attach/pin). Plane openings (B/F) must not fan back into the tube.
8. **No shared collapsed trunk** — After bipolar V rails, do not join every
   lane onto one shared horizontal/vertical at rail latitude (column/row-first
   join to the fan tip).
9. **No border hugging** — Strands should not run along place or element
   rectangle borders for long mid-run stretches.
10. **No out-and-back** — No collinear reverse (back and forth) on the same
    axis mid-path, except protected mouth zigzags.

### Terminals and openings

Terminals (element pins) and openings (location mouths / bocas) are **not**
the same endpoint kind. Multi-cable geometry differs:

| Endpoint | One cable | Several cables |
|----------|-----------|----------------|
| **Terminal** | Manhattan (12) | Short **V** at the pin (11); meet **only** at the pin (14) |
| **Opening** | Manhattan (12) | Stay **parallel**, never touch; enter the location side by side (13) |

**Who enters the location.** Only leaf runs that end on a terminal
(typically `Conductor`, or any cable whose endpoints are element pins) draw
an inbox path from the boca to the pin. Intermediate `Cable` sheaths
(cables-of-cables / jackets with `contains`) are drawn in the conduit and
**stop at the mouth** — they do not cross into the place interior.

11. **Multi-cable terminal → V** *(terminals only)* — When several
    conductors share one pin, the segment that **touches** the pin is a
    short diagonal. Both arms of a bipolar pair are diagonal; they meet
    **only** at the pin. Lateral pitch between V tips matches lane pitch
    (strand width + gap) so fans stay compact but strands stay distinct.
    If fans of consecutive terminals on the same face would overlap, the
    element (and thus its host place) widens so slot spacing clears both
    envelopes. The V must not overshoot the inbox corridor stub (no climb
    back toward the pin / hollow diamond).
12. **Single cable → Manhattan** *(terminals and openings)* — One conductor
    on a pin, or one cable at a mouth: orthogonal only (optional short stub
    + L). No decorative diagonal at either endpoint kind.
13. **Multi-cable opening → parallel** *(openings only)* — When several
    cables share an opening, they keep lane separation through the mouth
    and into the location. They **never** merge or touch at the boca (unlike
    a shared terminal). Entry is side-by-side / parallel, still Manhattan
    near the mouth (no V, no long boca→element diagonal).
14. **Meet only at the pin** *(terminals only)* — Multi-cable leads must
    not merge before the pin (no premature shared stub at the terminal).
    Does not apply to openings — see (13).

### Obstacles (places and elements)

17. **Route around foreign bodies** — Same idea for tubes and strands:
    - **Conduits** go around leaf **locations** (not through place interiors).
    - **Inbox cables** go around **elements** in the place: mid-run segments
      must not pierce an element’s box. That includes the from/to element —
      enter only from the pin face (outward stub / V); never cut through the
      body to reach a far-side pin. Lane-parallel offsets of a clear centerline
      must keep the same clearance (do not shove one bipolar strand into the
      box). Quality checks still exempt short pin-edge landings on the
      endpoint rect; a deep pierce of that same box is not OK.

### Overlaps and diagonals

15. **No illegal mid-run overlaps**
    - **Strands in the same conduit** — Keep minimum lane separation except
      where they legally meet at shared **pins** (14). Multi-cable openings
      must not meet at the boca (13). Riding along the host tube centerline
      (inside the stroke) is required (1), not an illegal overlap. Parallel
      strands may run close (lane pitch); they must not share a centerline.
    - **Distinct conduits** — Two tubes must not **colinear-stack** for a
      long mid-run: centerlines stay at least
      ``halfWidth_a + halfWidth_b + laneGap`` apart. Perpendicular crossings
      are allowed and **preferred** over a long C-detour around the other
      tube. Strands of conduit A sitting on conduit B’s stroke is wrong;
      strands of A on A’s own tube is correct. Mark-to-mark Manhattan
      shortcuts (L, then ≤3-segment C/U) apply for plane↔plane and
      side↔plane bocas when clear of obstacles/stacks; only then fall
      through to contour stubs (see Route_21, Route_28). A tube mid-run must
      not skim a **foreign opening mouth** on the endpoint boxes
      (plane↔plane mark-to-mark; pad ≈ mark radius + half-width).
    - **Inbox** — Same-box cables stay inside the host place content box;
      the place grows to fit the cable envelope when needed. Prefer short
      runs (including crossings) over long outside loops.
16. **No long diagonals** — Diagonals longer than the terminal-V budget are
    forbidden (especially boca→element shortcuts). Short diagonals are
    allowed only for multi-cable terminal V (11).

## Hop assembly contract

```text
head (ends at start lane crossing)
  + tube (start crossing → end crossing, parallel offset lanes)
  + tail (starts at end lane crossing)
```

- Single-cable: crossings coincide with the painted boca.
- Multi-cable: crossings stay on parallel offsets through the mouth — do
  **not** converge every lane onto the center boca.
- Strip out-and-back only on **head** / **tail**, with crossings and fan tips
  protected.
- Tube stays pristine; painted tube endpoints are the centerline bocas
  (strands pass within the tube half-width).
- Do not run `preserveTerminalVLead` / `ensureVertexNear` / unprotected
  `stripOutAndBack` on the merged chain.

## Live E2E

Example sites live in the `housewire-examples` package. Playwright loads each
site, dumps `path.edge-tube` and colored strands, then runs
`assess_live_site` / `assess_live_canvas` (see `tests/route_e2e/`).

| Check | Failure string (typical) |
|-------|---------------------------|
| Mouth | `misses tube[i] … mouth` |
| Envelope | `outside tube[i] envelope` |
| Shared trunk | `shared inbox trunk at y≈…` |
| Terminal V | `missing terminal V diagonal` |
| Opening parallel | `multi-cable strands meet` / `meet at mouth` |
| Tube packing | `tube underfilled` |
| Conduit stack | `tubes colinear-overlap` — asserted in every live geometry E2E via
  ``assert_tube_geometry_ok`` / ``assert_site_routes_ok`` |
| Foreign mouth | `skims foreign mouth` — tube mid-run must not hit another boca |
| Through element | `through element` |
| Out-and-back | `out-and-back` |

Sites without conduits (same-box only, e.g. `Route_01`) skip tube
mouth/envelope checks and still flag out-and-back / empty canvas problems.

Live E2E coverage:

| Site / suite | Focus |
|------|--------|
| `test_route_smoke` | Compact early fixtures: `Route_01`, `03`, `06`, `07`, `12` |
| `Route_01`…`Route_20` YAML | Example demos (not each one a separate E2E module) |
| `Route_14` | Mid→End side tube is one straight segment |
| `Route_15` | Room↔room tube ≤3 segments at depth 1/2 |
| `Route_21` | Panel + room; lamp N→B conduit ≤3 segments |
| `Route_22` | Same-box cable must skirt foreign elements |
| `Route_23` | Prefer conduit × over long C-detour |
| `Route_24` | Straight side-face cross conduits |
| `Route_25` | ISO opening-mark layout |
| `Route_26` | Straight back-face conduits (no vertices) |
| `Route_27` | L-shaped back-face conduits (one corner) |
| `Route_28` | Back-face L would stack — use C/U instead |
| `Route_29` | Three conductors in one N↔N tube — no strand lane stack |
| `Route_30` | Nine BN in one aligned S↔N tube — straight core, inbox ≤3, skirt elements |
