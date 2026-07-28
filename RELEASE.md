# Release Process

How to cut a `nanobot-bio` release. Current version lives in [`pyproject.toml`](pyproject.toml) and the `release` badge in [`README.md`](README.md); history in [`CHANGELOG.md`](CHANGELOG.md).

---

## 1. Versioning

- **Scheme:** [Semantic Versioning](https://semver.org/) `MAJOR.MINOR.PATCH`.
  - `PATCH`: bug fixes, doc tweaks, no behavior change for collaborators.
  - `MINOR`: new tools/commands/axes, backward-compatible.
  - `MAJOR`: breaking skill/verdict-schema or env-var changes.
- **Single source of truth:** `pyproject.toml` `version`. The README badge and `nanobot-bio --version` derive from it.
- **Pre-release:** suffix `-rc.N` / `-beta.N` in `pyproject.toml`; do **not** tag pre-releases as `latest`.

## 2. CHANGELOG

- Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
- Maintain an `## [Unreleased]` section during development.
- At release time, rename `[Unreleased]` → `[X.Y.Z] — YYYY-MM-DD` and add a fresh empty `[Unreleased]` above it.
- Group entries under `Added` / `Changed` / `Fixed` / `Removed`. Reference file paths and command names.

## 3. Cutting a release

```bash
# 0. On main, up to date
git checkout main && git pull

# 1. Bump version in pyproject.toml (single SoT)
#    Also update the README badge: release-vX.Y.Z
$EDITOR pyproject.toml README.md README.zh.md

# 2. Finalize CHANGELOG: [Unreleased] -> [X.Y.Z] — date
$EDITOR CHANGELOG.md

# 3. Local gate must pass
rbp-agent gate
# Optional, if delivery bundle + GPU available:
rbp-agent accept-golden

# 4. Commit + tag
git add pyproject.toml README.md README.zh.md CHANGELOG.md
git commit -m "release: vX.Y.Z"
git tag -a vX.Y.Z -m "vX.Y.Z"

# 5. Push
git push origin main
git push origin vX.Y.Z
```

Slim-vendor / honesty / session-memory checks before tagging: see
[`ARCHITECTURE.md`](ARCHITECTURE.md) §3 / §6.4 (single checklist).

## 4. GitHub Release

- Use the `vX.Y.Z` tag; title `vX.Y.Z`.
- Paste the `## [X.Y.Z]` block from `CHANGELOG.md` as the body.
- Attach `artifacts/reports/gate_report.json` (and `accept-golden` / LOO reports if generated) as evidence.
- Mark as **latest** for stable releases; leave pre-releases unmarked.

## 5. Docker image (optional, after P0-A)

```bash
# Agent-only (default)
docker build -t ghcr.io/joesun-421/nanobot-bio:X.Y.Z .
docker build -t ghcr.io/joesun-421/nanobot-bio:X.Y.Z-agent .
docker tag ghcr.io/joesun-421/nanobot-bio:X.Y.Z ghcr.io/joesun-421/nanobot-bio:latest

# Full science stack (GPU host recommended)
docker build --build-arg PROFILE=full \
  -t ghcr.io/joesun-421/nanobot-bio:X.Y.Z-full .

docker push --all-tags ghcr.io/joesun-421/nanobot-bio
```

## 6. Delivery bundle sync

`rhobind_agent_delivery/` is treated as a read-only data bundle (no version tag in that tree). When a release depends on a new delivery snapshot:

1. Coordinate the bundle update with the delivery owner.
2. Note the bundle commit / snapshot id in the `CHANGELOG` entry under `Changed`.
3. Update `INSTALL.md` §3 if the bundle layout or env vars changed.

## 7. Post-release

- Bump to next `-dev` (leave `[Unreleased]` empty, ready for new entries).
- If a hotfix is needed on a past release: branch `release/X.Y`, cherry-pick, tag `X.Y.Z+1`, merge the tag back to `main` so `CHANGELOG` stays linear.

## 8. Secrets check before tagging

```bash
bash scripts/check_secrets.sh
# Confirm ~/.nanobot/config.json is NOT in the tree and has no committed key.
git log -p --all -S 'sk-' -- . | head     # should be empty
```

## 9. Evolved-config promote flow (C6)

The evolved weights/thresholds live in two files under `config/`:

| file | tracked? | role |
| --- | --- | --- |
| `evolved.yaml` | **yes** | live promoted config, loaded by the agent at runtime |
| `evolved.candidate.yaml` | **no** (gitignored) | proposed config produced by `rbp-agent evolve` |
| `evolved.candidate.yaml.example` | **yes** | tracked seed so a fresh clone can bootstrap a candidate |

Promote link (offline compile → gate → deploy):

```bash
# 1. produce a candidate (offline self-evolution; writes evolved.candidate.yaml)
rbp-agent evolve

# 2. gate: light eval reports must exist and pass asserts
rbp-agent gate

# 3. promote candidate → evolved.yaml (flips evolved:true / candidate:false)
rbp-agent promote-evolved

# fresh-clone shortcut: bootstrap the candidate from the tracked seed, then promote
rbp-agent promote-evolved --seed
```

`promote-evolved` asserts that `reports/eval_loo_report.json` and
`reports/evaluation_plan_report.json` exist and pass (use `--force` only for
offline fixtures). The candidate is gitignored so collaborators never commit
in-progress tuning; the tracked `.example` seed keeps the link reproducible.
