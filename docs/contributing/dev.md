# Contributing to kmhelpers

## Dev environment setup

```bash
git clone https://github.com/sebllns/kmhelpers
cd kmhelpers
pip install -e ".[dev]"
```

`kmindex` and `kmtricks` must also be available — see [Installation](../getting-started/installation.md).

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
    A release consolidates current development work from `develop` into a dedicated `release/vX.Y.Z` branch, then merges it into `main` with a **merge commit** (`--no-ff`). This keeps `main` readable, one merge commit per release when viewed with `--first-parent`, while preserving full history and correct ancestry, so subsequent releases keep merging cleanly.


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
5. Merge `release/vX.Y.Z` into `main` with a merge commit (never fast-forward, never squash):
   ```bash
   git checkout main
   git pull origin main
   git merge --no-ff release/vX.Y.Z -m "Merge branch 'release/vX.Y.Z' into 'main'"
   git push origin main
   ```
   `--no-ff` forces a merge commit even though `main` is an ancestor of the release branch; without it Git would fast-forward and you would lose the per-release merge marker. If you release via a GitLab MR / GitHub PR instead, choose **Create a merge commit** (not squash, not fast-forward).
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

### Viewing `main` history

Because releases land as `--no-ff` merge commits, `main` reads as one entry per release with `--first-parent`:

```bash
git log --first-parent --oneline main
```

```
xxxxxxx Merge branch 'release/v0.6.3' into 'main'
0be81302 Merge branch 'release/v0.6.2' into 'main'
bc287506 Merge branch 'release/v0.6.1' into 'main'
```

The individual release commits are still fully reachable (blame and `git bisect` work); `--first-parent` just hides them from the top-level view. Optionally alias it:

```bash
git config alias.mainlog "log --first-parent --oneline main"
```