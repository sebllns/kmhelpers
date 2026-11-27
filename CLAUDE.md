# CLAUDE.md - kmhelpers

## Branches

- Work branches start from `new_param_tuning`. Never commit to `main`, `develop` or `new_param_tuning` directly; merges go through a PR reviewed by the maintainer.
- `feature/<topic>`: generic changes, useful to any dataset or cluster (sizing, chunk and shard state, partial apply, query on chunk, status output).
- `logan-tacc/<topic>`: Logan 1.2 or TACC Vista specific changes, only when they cannot be expressed as config, CLI options or hooks. State the reason in the PR. Everything else Logan/TACC specific lives in the project repo `omicfinder/claude_logan_1.3`.
- No force-push, no rewriting pushed history, no deleting remote branches.

## Tests

```bash
source /path/to/env/bin/activate            # conda/environment.yml + pip install -e ".[dev]"
python -m pytest pykmhelpers/tests --no-cov --ignore=pykmhelpers/tests/test_pipeline_e2e.py   # unit tests, about 30 s
python -m pytest pykmhelpers/tests/test_pipeline_e2e.py   # needs kmindex and ntcard on PATH
python -m pytest pykmhelpers/tests/test_merging.py -k <name>   # one area
```

When the editable install points at another clone (git worktrees), run from the worktree root so `pykmhelpers` imports from it (`python -c "import pykmhelpers; print(pykmhelpers.__file__)"`). New behavior needs tests under `pykmhelpers/tests/`.

## Code conventions

- black (line length 88), isort (black profile), flake8, mypy (`python_version = 3.10`): `black pykmhelpers && flake8 pykmhelpers && mypy pykmhelpers`.
- Type hints on public APIs, `pathlib`, `logging` (no prints in library code), minimal diffs.
- Commit messages: imperative mood, subject under 72 characters; notable changes in `CHANGELOG.md`.

## Sizing code

- `pykmhelpers/pipeline/index_ops/sizing.py`: chunk and shard sizing, partitions, threads.
- `pykmhelpers/pipeline/index_ops/merging.py`: `kmindex merge` planning and its RAM model.
- `pykmhelpers/pipeline/index_ops/executor.py`, `runner.py`, `status.py`, `layout.py`: apply, state, status.
- `pykmhelpers/pipeline/index_ops/sources.py`: input sources.
- `pykmhelpers/core/build_params.py`, `core/resources.py`, `core/constants.py`: build parameters, node resources, constants (budgets).
- `pykmhelpers/vendor/kmparams.py`: vendored Bloom filter parameter formulas.
