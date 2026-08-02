# Cable routing rules (canvas)

These rules define what **correct** physical/electrical canvas routing looks
like for HouseWire. Detectors live in
[`housewire.ui.route_quality`](../src/housewire/ui/route_quality.py); the hop
assembler is in [`app.js`](../src/housewire/ui/static/app.js)
(`cableBaseSubpaths`). End-to-end checks paint a site and call
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
10. **No out-and-back** — No collinear reverse (ida y vuelta) on the same
    axis mid-path, except protected mouth zigzags.

### Terminals and openings

11. **Multi-cable terminal → V** — When several conductors share one pin, the
    segment that **touches** the pin is a short diagonal. Both arms of a
    bipolar pair are diagonal; they meet **only** at the pin.
12. **Single-cable terminal → Manhattan** — One conductor on a pin: orthogonal
    only (optional short stub + L). No decorative diagonal.
13. **Openings → Manhattan** — Approach to an opening/mouth is Manhattan; no
    long boca→element diagonal.
14. **Meet only at the pin** — Multi-cable leads must not merge before the
    pin (no premature shared stub at the terminal).

### Overlaps and diagonals

15. **No illegal mid-run overlaps** — Parallel strands keep minimum lane
    separation except where they legally meet (mouth converge, pin).
16. **No long diagonals** — Diagonals longer than the terminal-V budget are
    forbidden (especially boca→element shortcuts).

## Hop assembly contract

```text
head (ends at start mouth)
  + tube (start mouth → end mouth, offset lanes, converge at ends)
  + tail (starts at end mouth)
```

- Strip out-and-back only on **head** / **tail**, with mouths and fan tips
  protected.
- Tube stays pristine; mouths are the painted tube endpoints.
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
| Out-and-back | `out-and-back` |

Sites without conduits (same-box only, e.g. `Route_01`) skip tube
mouth/envelope checks and still flag out-and-back / empty canvas problems.

| Site | Focus |
|------|--------|
| `Test_01` | Panel + room (reference regression) |
| `Route_01` | Same-box link, no conduit |
| `Route_02`–`Route_04` | Single / twin conductors, L-path |
| `Route_05`–`Route_07` | Switch drop, lamp plane boca, bipolar V |
| `Route_08`–`Route_12` | Strip feeds, earth, parallel tubes |
| `Route_13` | Full Test_01 twin |
| `Route_14`–`Route_17` | Chains, rooms, dense strip, parallel fan-out |
| `Route_18`–`Route_20` | Multi-cable / Test_01-class stress |
