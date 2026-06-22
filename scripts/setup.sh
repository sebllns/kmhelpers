#!/usr/bin/env bash

set -euo pipefail

for cmd in git conda; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "Error: '$cmd' is not available. Please install it before running this script." >&2
    exit 1
  fi
done

KMINDEX_REPO="https://github.com/tlemane/kmindex"
KMINDEX_BRANCH="next-dev"
BUILD_DIR="$(mktemp -d)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_PATH="${SCRIPT_DIR}/../.env"

trap 'rm -rf "$BUILD_DIR"' EXIT

echo "==> Creating base environment at ${ENV_PATH} (without kmindex)"
TMP_YML="$(mktemp --suffix=.yml)"
grep -v "^  - kmindex$" "$SCRIPT_DIR/../conda/environment.yml" > "$TMP_YML"
if [[ -d "$ENV_PATH" ]]; then
  conda env update --prefix "$ENV_PATH" -f "$TMP_YML" --prune
else
  conda env create --prefix "$ENV_PATH" -f "$TMP_YML"
fi
rm "$TMP_YML"

echo "==> Cloning kmindex ${KMINDEX_BRANCH}"
git clone --depth 1 --branch "$KMINDEX_BRANCH" "$KMINDEX_REPO" "$BUILD_DIR/kmindex"

echo "==> Building kmindex conda package"
RECIPE_DIR="$BUILD_DIR/kmindex/conda/kmindex"
RECIPE_FILE="$RECIPE_DIR/meta.local.yaml"
COMMIT=$(git -C "$BUILD_DIR/kmindex" rev-parse --short HEAD 2>/dev/null || echo "unknown")

sed \
  -e 's|\({% set version = "[^"]*\)"\s*%}|\1.dev0" %}|' \
  -e "s|{% set version.*|&\n{% set commit = \"${COMMIT}\" %}|" \
  -e 's|git_url:.*|path: ../..|' \
  -e '/git_rev:/d' \
  -e 's|^source:|build:\n  string: {{ commit }}\n\nsource:|' \
  "$RECIPE_DIR/meta.yaml" > "$RECIPE_FILE"

echo "Generated meta.local.yaml (commit: ${COMMIT})"
conda run --prefix "$ENV_PATH" conda build "$RECIPE_DIR" --recipe-file "$RECIPE_FILE" --no-test

echo "==> Installing kmindex into ${ENV_PATH}"
conda install --prefix "$ENV_PATH" -y --use-local kmindex

echo "==> Done. Activate with: conda activate ${ENV_PATH}"