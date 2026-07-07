# Contributing to kmhelpers

## Dev environment setup

```bash
git clone https://github.com/sebllns/kmhelpers
cd kmhelpers
pip install -e ".[dev]"
```

`kmindex` and `kmtricks` must also be available — see [Installation](../installation.md) for the `scripts/setup.sh` build.

## Project structure

```
pykmhelpers/
  cli/          # Click commands (one file per command)
  core/         # Low-level building blocks (index, bloom_filter, kmindex_wrapper, …)
  operations/   # Higher-level operations (builder, fof_validation, …)
  tests/        # Test suite
  pipeline/     # Pipeline execution engine
```

Each CLI command in `cli/` is a thin layer that delegates to `operations/` or `core/`.

## Running tests

```bash
pytest
```

Coverage is reported automatically (configured in `pyproject.toml`). HTML report is written to `htmlcov/`.

## Code style

| Tool | Purpose |
|------|---------|
| `black` | Formatting (line length 88) |
| `flake8` | Linting |
| `mypy` | Type checking |

```bash
black pykmhelpers/
flake8 pykmhelpers/
mypy pykmhelpers/
```

## Branching

| Branch pattern | Purpose |
|----------------|---------|
| `main` | Stable, released code |
| `develop` | Integration branch for ongoing work |
| `dev/vX.Y.Z` | Version-scoped development (e.g. `dev/v0.6.3`) |
| `dev/<topic>` | Topic-scoped development (e.g. `dev/spans_to_groups`) |
| `feature/<name>` | Self-contained feature work |
| `doc/<name>` | Documentation-only changes |
| `release/vX.Y.Z` | Release stabilisation branch |
| `gh-pages` | Auto-managed by `mkdocs gh-deploy` — do not push manually |

Open pull requests against `main` for releases, or against `develop` for work in progress.

## Releasing

!!! abstract
    A release consolidates current development work from `develop` into a dedicated `release/vX.Y.Z` branch, then squash-merges it into `main` as a single versioned commit. This keeps `main` history clean and readable while `develop` retains the full commit history.

1. Work on a `dev/vX.Y.Z` branch:
   ```bash
   git checkout -b dev/vX.Y.Z
   ```
2. Bump the version in `pyproject.toml` and `CHANGELOG.md`.
3. Merge into `develop` and delete `dev/vX.Y.Z`:
   ```bash
   git checkout develop
   git merge dev/vX.Y.Z
   git push origin develop
   git branch -d dev/vX.Y.Z
   git push origin --delete dev/vX.Y.Z
   ```
4. Create a `release/vX.Y.Z` branch from `develop`:
   ```bash
   git checkout -b release/vX.Y.Z
   git push origin release/vX.Y.Z
   ```
5. Open a pull request from `release/vX.Y.Z` into `main` — use **Squash and merge** with commit message `Release vX.Y.Z`. This keeps `main` history clean with one commit per release.
6. After merge, tag the release on `main`:
   ```bash
   git checkout main
   git pull
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```
7. Sync `develop` with a regular merge (preserves full commit history):
   ```bash
   git checkout develop
   git merge main
   git push origin develop
   ```
8. Deploy the updated docs:
   ```bash
   mkdocs gh-deploy
   ```