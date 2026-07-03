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

## Structure

```
mkdocs.yml          # MkDocs configuration
docs/
  index.md          # Home page
  installation.md   # Installation guide
  getting-started.md
  changelog.md      # Includes CHANGELOG.md via snippet
  tutorials/
    ecoli.md        # E. coli indexing tutorial
  commands/
    index.md        # Command reference overview
    list.md
    profile.md
    compose.md
    plan.md
    apply.md
    query.md
    compress.md
    registry.md
    pipeline.md
  contributing/
    docs.md         # This file
```

## Adding or editing pages

1. Edit or create a `.md` file under `docs/`.
2. If it's a new page, add it to the `nav:` section in `mkdocs.yml`.
3. Run `mkdocs serve` to preview.

## Deploying to GitHub/GitLab Pages

```bash
mkdocs gh-deploy
```

This builds the site and pushes it to the `gh-pages` branch of the configured `repo_url`.