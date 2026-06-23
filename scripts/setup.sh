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

BUILD_DIR="/tmp/tmp.jgOCQs1fFS"

## trap 'rm -rf "$BUILD_DIR"' EXIT

echo "==> Creating conda environment at ${ENV_PATH}"
if [[ -d "$ENV_PATH" ]]; then
  conda env update --prefix "$ENV_PATH" -f "$SCRIPT_DIR/../conda/environment.yml" --prune
else
  conda env create --prefix "$ENV_PATH" -f "$SCRIPT_DIR/../conda/environment.yml"
fi

echo "==> Activating conda environment"
set +u
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "$ENV_PATH"
set -u

echo "==> Switching kmtricks submodule to static_repart branch"
git -C "$BUILD_DIR/kmindex/thirdparty/kmtricks" fetch --depth 1 origin static_repart
git -C "$BUILD_DIR/kmindex/thirdparty/kmtricks" checkout FETCH_HEAD

echo "==> Patching TURBOP build command (CMake quoting bug with OPT=... in BUILD_COMMAND)"
python3 - "$BUILD_DIR/kmindex/thirdparty/kmtricks/thirdparty/CMakeLists.txt" <<'PYEOF'
import sys
path = sys.argv[1]
with open(path) as f:
    content = f.read()
old = '  BUILD_COMMAND ${CMAKE_COMMAND} -E env\n  make OPT="-fstrict-aliasing -fPIC -Wno-incompatible-pointer-types" libic.a'
new = "  BUILD_COMMAND sh -c \"make OPT='-fstrict-aliasing -fPIC -Wno-incompatible-pointer-types' libic.a\""
content = content.replace(old, new)
with open(path, 'w') as f:
    f.write(content)
PYEOF

export CC="$(command -v x86_64-conda-linux-gnu-gcc)"
export CXX="$(command -v x86_64-conda-linux-gnu-g++)"

echo "==> Print environment infos"
echo "  OS:    $(uname -sr) / $(grep PRETTY_NAME /etc/os-release 2>/dev/null | cut -d= -f2 | tr -d '"')"
echo "  CPU:   $(uname -m) / $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2 | xargs)"
echo "  gcc:   $CC — $($CC --version | head -1)"
echo "  g++:   $CXX — $($CXX --version | head -1)"
echo "  cmake: $(command -v cmake) — $(cmake --version | head -1)"
echo "  git:   $(command -v git) — $(git --version)"

echo "==> Building and installing kmtricks into ${ENV_PATH}"
rm -rf "$BUILD_DIR/kmindex/thirdparty/kmtricks/kmbuild"
mkdir -p "$BUILD_DIR/kmindex/thirdparty/kmtricks/kmbuild"
cd "$BUILD_DIR/kmindex/thirdparty/kmtricks/kmbuild"
cmake .. \
  -DCMAKE_C_COMPILER="$CC" \
  -DCMAKE_CXX_COMPILER="$CXX" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$ENV_PATH" \
  -DCMAKE_PREFIX_PATH="$ENV_PATH" \
  -DWITH_MODULES=OFF \
  -DWITH_SOCKS=OFF \
  -DWITH_HOWDE=OFF \
  -DCOMPILE_TESTS=ON \
  -DSTATIC=OFF \
  "-DKMER_LIST=32 64 96 128" \
  -DMAX_C=4294967295 \
  -DNATIVE=ON \
  -DWITH_PLUGIN=OFF
make -j"$(nproc)"
make install

echo "==> Building and installing kmindex into ${ENV_PATH}"
rm -rf "$BUILD_DIR/kmindex/kmbuild"
mkdir -p "$BUILD_DIR/kmindex/kmbuild"
cd "$BUILD_DIR/kmindex/kmbuild"
cmake .. \
  -DCMAKE_C_COMPILER="$CC" \
  -DCMAKE_CXX_COMPILER="$CXX" \
  -DCMAKE_BUILD_TYPE=Release \
  -DWITH_TESTS=OFF \
  -DWITH_SERVER=OFF \
  -DPORTABLE_BUILD=OFF \
  -DCMAKE_CXX_STANDARD=17 \
  -DMAX_KMER_SIZE=256 \
  -DSPDLOG_HEADER_ONLY=ON \
  -DCMAKE_INSTALL_PREFIX="$ENV_PATH" \
  -DCMAKE_PREFIX_PATH="$ENV_PATH"
make -j"$(nproc)"
make install

echo "==> Done. Activate with: conda activate ${ENV_PATH}"