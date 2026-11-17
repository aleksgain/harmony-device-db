# harmony-device-db

A pinned, verified snapshot of the Logitech Harmony IR device database, packaged
for [harmony-server](https://github.com/harmony-revival/harmony-server). Part of
[Harmony Revival](https://github.com/harmony-revival).

The data comes from
[pickysysadmin/logitech-harmony-ir-archive](https://github.com/pickysysadmin/logitech-harmony-ir-archive).
See [SOURCES.md](SOURCES.md) for credits and the licence position.

## How it works

Upstream publishes its data as a git tree of about 340,000 JSON files (~0.8 GB),
and tags each data release `YYYYMMDD`. Committing that tree here would make every
sync PR unreviewable, so this repo commits:

| path | contents |
|---|---|
| `archive.lock.json` | the pinned upstream tag, commit, tree hash, schema version, counts and checksums |
| `api/v1/manifest.json`, `api/v1/index.json` | upstream's top-level files at that pin, so a sync PR shows what changed |
| `api/v1/LICENSE-DATA` | upstream's CC0 text |

The rest of `api/v1/` (`devices/`, `codesets/`, `protocols/`) is gitignored. It is
fetched from the pinned commit by `scripts/sync-archive.sh fetch`, and checked
against the pinned tree hash, which is a content hash of every file in it.

## Getting the data

Download the latest release tarball:

```sh
gh release download --repo harmony-revival/harmony-device-db --pattern '*.tar.gz' --pattern SHA256SUMS.txt
sha256sum -c --ignore-missing SHA256SUMS.txt
tar xzf harmony-device-db-v*.tar.gz --strip-components=1   # creates api/v1/
```

Or build it from a clone:

```sh
scripts/sync-archive.sh fetch          # needs git, jq; downloads ~120 MB
python3 scripts/verify.py --full       # ~1 min
```

The layout under `api/v1/` is upstream's, documented in its README: start at
`manifest.json`, whose `layout` key gives the path patterns.

## Versioning

Release tags are `v<schemaVersion>.<upstreamTag>.<revision>`, for example
`v2.20261110.0`:

- **major**: upstream `schemaVersion`, which upstream bumps only on breaking field
  changes. Pin the major version to stay compatible.
- **minor**: the upstream data tag.
- **patch**: a repackaging of the same upstream snapshot.

## Automation

| workflow | trigger | what it does |
|---|---|---|
| `ci.yml` | PR, push to `main`/`develop` | shellcheck, validates committed metadata against the lock; when a PR changes the lock, fetches the full tree and verifies a 5,000-device sample |
| `sync.yml` | Monday 04:00 UTC, manual | finds the newest upstream `YYYYMMDD` tag; if it is new, pins it, fetches and fully verifies the tree, and opens a PR |
| `release.yml` | push to `main`, `v*.*.*` tag, manual | if `v<schema>.<upstream>.0` does not exist yet, fetches, verifies, builds a deterministic tarball and publishes a GitHub Release |

Merging a sync PR therefore publishes a release with no further steps. To
repackage the same snapshot, push `v<schema>.<upstream>.<N+1>` by hand.

No secrets are needed: all workflows use the built-in `GITHUB_TOKEN`.

PRs opened by `sync.yml` use `GITHUB_TOKEN`, and GitHub does not run workflows
for those, so `ci.yml` does not run on them. `sync.yml` runs the full
verification itself before opening the PR. To get CI on sync PRs as well, give
`peter-evans/create-pull-request` a fine-grained PAT or GitHub App token as
`token:` (store it as a secret named `SYNC_PR_TOKEN`).

## Scripts

- `scripts/sync-archive.sh check|update [TAG]|fetch`: see the header of the script.
  `UPSTREAM_URL` overrides the upstream git URL, for example to use a local mirror.
- `scripts/verify.py [ROOT] [--full] [--sample N]`: Python standard library only.
  It checks structure and that every count in `manifest.json` matches the files.
  Devices with `model: null` (three in `20261110`) are reported as warnings.

## Licence

Code: [Apache-2.0](LICENSE). Data: see [SOURCES.md](SOURCES.md).
