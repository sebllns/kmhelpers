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

echo "==> Creating conda environment at ${ENV_PATH}"
if [[ -d "$ENV_PATH" ]]; then
  conda env update --prefix "$ENV_PATH" -f "$SCRIPT_DIR/../conda/environment.yml" --prune
else
  conda env create --prefix "$ENV_PATH" -f "$SCRIPT_DIR/../conda/environment.yml"
fi

echo "==> Cloning kmindex ${KMINDEX_BRANCH}"
git clone --depth 1 --branch "$KMINDEX_BRANCH" --recurse-submodules "$KMINDEX_REPO" "$BUILD_DIR/kmindex"

echo "==> Building and installing kmindex into ${ENV_PATH}"
export CC="$ENV_PATH/bin/x86_64-conda-linux-gnu-gcc"
export CXX="$ENV_PATH/bin/x86_64-conda-linux-gnu-g++"
conda run --prefix "$ENV_PATH" \
  bash -c "
    rm -rf '$BUILD_DIR/kmindex/kmbuild' && mkdir -p '$BUILD_DIR/kmindex/kmbuild' && cd '$BUILD_DIR/kmindex/kmbuild' && \
    $CC --version && $CXX --version && \
    cmake .. \
      -DCMAKE_C_COMPILER='$CC' \
      -DCMAKE_CXX_COMPILER='$CXX' \
      -DCMAKE_BUILD_TYPE=Release \
      -DWITH_TESTS=OFF \
      -DWITH_SERVER=OFF \
      -DPORTABLE_BUILD=OFF \
      -DCMAKE_CXX_STANDARD=17 \
      -DMAX_KMER_SIZE=256 \
      -DSPDLOG_HEADER_ONLY=ON \
      -DCMAKE_INSTALL_PREFIX='$ENV_PATH' \
      -DCMAKE_PREFIX_PATH='$ENV_PATH' && \
    make -j$(nproc) && make install
  "

echo "==> Done. Activate with: conda activate ${ENV_PATH}"
