# housewire-examples

Public, generic example sites for [HouseWire](https://github.com/guillermomolina/housewire).

This package is **not** a real installation. Private site YAML stays in a separate
repository. Use these fixtures for demos, screenshots, and CI E2E.

## License

**Server Side Public License v1 (SSPL-1.0)** — see [LICENSE](LICENSE).
Copyright (c) 2026 Guillermo Adrián Molina.

Same terms as the HouseWire program: self-hosting and modification are fine;
offering these examples (or a modified version) to third parties **as a service**
triggers the SSPL Service Source Code obligations.

## Install

From the HouseWire monorepo (editable):

```bash
pip install -e packages/housewire-examples
# or with the program extras:
pip install -e '.[dev,ui,examples,catalog]'
```

When published to PyPI:

```bash
pip install housewire-examples
```

Type catalog: install `housewire-catalog` (pulled by `.[catalog]` / `.[examples]`),
or set `HOUSEWIRE_CATALOG` / clone `catalogs/default`.

## Use

```bash
python -c "from housewire_examples import site_yaml; print(site_yaml('Route_21'))"
housewire serve "$(python -c "from housewire_examples import site_yaml; print(site_yaml('Route_21'))")"
```

Environment override for E2E:

```bash
export HOUSEWIRE_E2E_SITE=/path/to/any-site.yaml
```

## Sites

| Name | Description |
|------|-------------|
| `Route_01` | Same-box conductor (no conduit) |
| `Route_02` | Two boxes, one tube, one conductor |
| `Route_03` | Twin BN+BU in one tube |
| `Route_04` | L-shaped two-hop path |
| `Route_05` | Switch drop |
| `Route_06` | Lamp via plane boca |
| `Route_07` | Bipolar terminal V |
| `Route_08` | Strip two pairs |
| `Route_09` | Strip four-pair feed |
| `Route_10` | Feed plus earth |
| `Route_11` | Two parallel tubes |
| `Route_12` | Switch and lamp |
| `Route_13` | Route_21 twin (full panel + room) |
| `Route_14` | Three-hop chain |
| `Route_15` | Two rooms |
| `Route_16` | Dense strip exits |
| `Route_17` | Parallel east tubes (fan-out stand-in) |
| `Route_18` | Multi-cable twin of Route_21 |
| `Route_19` | Staggered heights |
| `Route_20` | Full-stress twin of Route_21 |
| `Route_21` | Reference panel + room (routing E2E) |
| `Route_22`… | Targeted regressions (see `docs/routing-rules.md`) |
| `Route_30` | Nine BN in one aligned S↔N tube (inbox ≤3, straight core) |

Regenerate Route_01…Route_20 fixtures (not Route_21+):

```bash
python packages/housewire-examples/scripts/gen_route_sites.py
```

Live E2E: smoke for early fixtures in `tests/route_e2e/test_route_smoke.py`
(Route_01, 03, 06, 07, 12); targeted sites from Route_21+ have their own
modules (plus `test_conduit_*`, `test_element_avoidance`). Requires Chromium
(`make install` or `make test-route-e2e`).
Routing rules: [`docs/routing-rules.md`](../../docs/routing-rules.md).
