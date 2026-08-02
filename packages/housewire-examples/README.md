# housewire-examples

Public, generic example sites for [HouseWire](https://github.com/guillermomolina/housewire).

This package is **not** a real installation. Private site YAML stays in a separate
repository. Use these fixtures for demos, screenshots, and CI E2E.

## Install

From the HouseWire monorepo (editable):

```bash
pip install -e packages/housewire-examples
# or with the program extras:
pip install -e '.[dev,ui,examples]'
```

When published to PyPI:

```bash
pip install housewire-examples
```

You still need a type catalog (`HOUSEWIRE_CATALOG` / `catalogs/default`).

## Use

```bash
python -c "from housewire_examples import site_yaml; print(site_yaml('Test_01'))"
housewire serve "$(python -c "from housewire_examples import site_yaml; print(site_yaml('Test_01'))")"
```

Environment override for E2E:

```bash
export HOUSEWIRE_E2E_SITE=/path/to/any-site.yaml
```

## Sites

| Name | Description |
|------|-------------|
| `Test_01` | Panel + room with junction box, switch, and lamp (routing E2E) |
