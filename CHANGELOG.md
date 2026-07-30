# Changelog

All notable changes to **housewire** are documented in this file.

Format inspired by [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

_Changes not yet released in a tagged version._

## [0.6.4] — 2026-07-30

### Changed

- Opening faces `fondo` / `tapa` renamed to English **`back`** / **`lid`**
  (legacy tokens still recognized in physical text).

## [0.6.3] — 2026-07-30

### Added

- Shell `show` lists `openings` as their own section (`B1 face=… index=…`).

## [0.6.2] — 2026-07-30

### Changed

- `location.openings` (`B1`, `B2`, …) also applies to **`Panel`**, not only
  `JunctionBox` (docs + catalog).

## [0.6.1] — 2026-07-30

### Added

- `housewire --version` / `-V`, subcommand `housewire version`, and shell
  command `version`.

## [0.6.0] — 2026-07-30

### Changed (breaking)

- Junction box openings use **local ids** (`B1`, `B2`, …) declared in
  `location.openings` with optional `face` / `index` and `mount` / `facing`.
- `pend` validates opening ids when `openings` is declared.
- Physical diagram recognizes `abertura B*`; legacy cardinals (`W.N`, …) still
  parse from old text.
- Docs and README use `B*` instead of `W.N` / `E.S`.

## [0.5.3] — 2026-07-30

### Changed

- Shell prompt is path-only (`project/cwd`); dropped the redundant
  `[…/housewire.yaml]` suffix and the “Activo (auto)” line on `cd`.

## [0.5.2] — 2026-07-30

### Changed

- Shell `ls` lists only child directories that have **`housewire.yaml`** (real
  locations). Bare path folders are skipped; `cd` into one prints a warning.

## [0.5.1] — 2026-07-30

### Changed

- Shell `ls` lists **locations** (cd targets) and **elements** of the current
  place; dropped filesystem `[d]`/`[f]` markers and `housewire.yaml` file rows.

## [0.5.0] — 2026-07-30

### Changed (breaking)

- Per-directory file renamed from **`index.yaml`** to **`housewire.yaml`**
  (also accepts `housewire.yml`).
- Place type **`Site`** renamed to **`House`** (dwelling; not a privileged root).
- Zone diagrams group by **top-level directory** under `project_path` (no
  hard-coded site layout). Root-level YAMLs form a zone named after the project
  directory. Remap by pointing `project_path` at another subtree or wrapping
  folders above.

### Migration

```bash
# in each location directory
mv index.yaml housewire.yaml
# if you used type: Site → type: House (optional; any place type may sit at root)
```

## [0.4.0] — 2026-07-30

### Changed (breaking)

- Connection `from` / `to` refs may only target the **declaring location and its
  sublocations** (child-relative paths such as `Caja 2/Regleta.1`).
- `../` (and any ref that leaves the current tree) is rejected; put the
  connection in a common ancestor instead.
- Absolute refs are still accepted only when they resolve inside the same tree.
- `via` must name a cable defined in the same location as the connection.

## [0.3.0] — 2026-07-30

### Changed (breaking)

- Renamed top-level **`self:`** to **`location:`** for per-directory place metadata.
- `location.type` is a place kind: **`Room`**, **`JunctionBox`**, **`Panel`**, **`Zone`**, **`Site`** (plus legacy **`Location`**).
- `location:` as a path **list** remains invalid; hierarchy is still the filesystem path only.
- `add location NAME` requires **`--type`**.
- Catalog place types (`Room`, `JunctionBox`, `Panel`, `Zone`, `Site`) with `wireviz_skip: true`.

### Migration

```yaml
# before
self:
  type: Location
  subtype: "100x100 IP40"

# after
location:
  type: JunctionBox   # or Room | Panel | Zone | Site
  subtype: "100x100 IP40"
```

## [0.2.2] — 2026-07-30

### Changed

- **One `index.yaml` per Location directory.** Generate/collect only `index.yaml` / `index.yml`; sibling fragment YAMLs are ignored.
- Shell `use` accepts only `index.yaml`; removed `add file` (use `add location` instead).
- Docs: no multi-file-per-directory layout.

### Added

- Confirmation that `add location` creates the directory and `index.yaml` with `self:`.

## [0.2.1] — 2026-07-30

### Changed

- Docs no longer reference any private site repository or concrete installation names.
- README treats site data as an external path (`$SITE`); local `projects/` remains gitignored only as an optional convenience.

## [0.2.0] — 2026-07-30

### Changed (breaking)

- **Locations = directories + `index.yaml`**. Hierarchy comes from the filesystem path, not a `location:` field.
- Per-directory metadata lives in a top-level **`self:`** block (`type: Location`, `subtype`, `notes`, …).
- The YAML **`location:`** field is no longer supported and raises if present.
- Shell is location-oriented: after `cd`, auto-activate **`index.yaml`** (preferred over “single yaml in cwd”).
- Bare `show` prints the Location `self:` plus a content summary for the current place.
- `ls` marks sublocations (`[loc]`) and `index.yaml` (`[index]`).
- Tab completion prefers directories and `index.yaml`.
- Existing site trees using the old stub + `location:` pattern must be migrated to directories + `index.yaml` (site repos are separate from this program).

### Added

- Shell command **`add location NAME`**: creates a folder + `index.yaml` with `self:`.
- IO helper `create_location_index`.
- Location model docs in `docs/schema-house-v1.md` and README.
- Tests for `self:`, rejection of `location:`, `index.yaml` auto-use, and `show` with `self`.

## [0.1.0] — 2026-07-30

First usable package and site shell.

### Added

- Schema **`house/v1`**: elements, cables, connections, conduits; catalog (MCB, RCD, Socket, TerminalStrip, Location, …).
- **WireViz** export (full + per zone) and **physical topology** diagrams.
- Interactive shell: `cd`, `ls`, `use`, `show`, `add`, `rm`, `generate`, `help`.
- Fast pending-cable capture: **`pend`** / `add pend` (`PEND_*` convention + pass-through conduit).
- Cable defaults (`1.5 mm2`, `BN,BU`) and auto-use when exactly one house YAML is in the cwd.
- **Tab** completion (commands, `add`/`rm` subcommands, paths).
- Documented convention for pending runs (through a box without a terminal strip splice).
- Split test modules; `dev-requirements.txt` with pytest; `make test`.

### Notes

- Before 0.2.0, some layouts used a parent `type: Location` stub plus sibling `location:`; that pattern is invalid now.

[Unreleased]: https://github.com/local/housewire/compare/v0.2.2...HEAD
[0.2.2]: https://github.com/local/housewire/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/local/housewire/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/local/housewire/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/local/housewire/releases/tag/v0.1.0
