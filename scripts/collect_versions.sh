#!/usr/bin/env bash
# Collect versions of kmhelpers and its companion tools for bug reports.
# Usage: bash scripts/collect_versions.sh
# Paste the output into the "versions" fields of a GitHub bug report.

set -u

# Print "<label>: <version>" or "<label>: not found".
# Tools may print their version on stdout or stderr, so we merge both.
report() {
    local label="$1"
    shift
    local cmd="$1"
    shift

    if ! command -v "$cmd" >/dev/null 2>&1; then
        printf '%-10s: not found\n' "$label"
        return
    fi

    local out
    out="$("$cmd" "$@" 2>&1 | head -n 1 | tr -d '\r')"
    printf '%-10s: %s\n' "$label" "${out:-unknown}"
}

echo "=== kmhelpers version report ==="
report "kmhelpers" kmhelpers --version
report "kmindex"   kmindex --version
report "kmtricks"  kmtricks --version
report "ntcard"    ntcard --version

# OS name: prefer the distro (os-release), fall back to sw_vers (macOS) or uname.
os_name() {
    if [ -r /etc/os-release ]; then
        . /etc/os-release
        echo "${PRETTY_NAME:-$NAME}"
    elif command -v sw_vers >/dev/null 2>&1; then
        echo "$(sw_vers -productName) $(sw_vers -productVersion)"
    else
        uname -s
    fi
}
printf '%-10s: %s\n' "OS" "$(os_name)"
printf '%-10s: %s\n' "Kernel" "$(uname -srm)"