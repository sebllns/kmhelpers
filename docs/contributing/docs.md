# Building the Documentation

The docs are built with [MkDocs](https://www.mkdocs.org/) using the [Material theme](https://squidfunk.github.io/mkdocs-material/).

## Install dependencies

For development:

```bash
pip install -e ".[dev]"
```

For docs only:

```bash
pip install -e ".[docs]"
```

## Live preview

Starts a local server with hot-reload on file changes:

```bash
mkdocs serve --dirtyreload --livereload
```

Then open <http://127.0.0.1:8000> in your browser.


## Build static site

Outputs the static HTML to `site/`:

```bash
mkdocs build
```

The `site/` directory is git-ignored and should not be committed.

## Adding or editing pages

1. Edit or create a `.md` file under `docs/`.
2. If it's a new page, add it to the `nav:` section in `mkdocs.yml`.
3. Run `mkdocs serve` to preview.

## Deploying to GitHub Pages

Docs are versioned with [mike](https://github.com/jimporter/mike). Do **not** use `mkdocs gh-deploy` — it overwrites the entire `gh-pages` branch and destroys version history.

### Deploy a new version

```bash
mike deploy --push --update-aliases <version> latest
```

Example for a release:

```bash
mike deploy --push --update-aliases 0.6.3 latest
```

This builds the docs, pushes them to `gh-pages` under `/<version>/`, and updates the `latest` alias to point to it.

### List deployed versions

```bash
mike list
```

### Preview versioned docs locally

```bash
mike serve
```