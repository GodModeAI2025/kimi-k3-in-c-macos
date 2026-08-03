#!/usr/bin/env bash
# Offline validation for the macOS port package itself.
set -euo pipefail
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TMP=${TMPDIR:-/tmp}/kimi-k3-macos-port-validate.$$
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
mkdir -p "$TMP"

# `\b` above is deliberately NOT used: it is a GNU regex extension, and BSD grep -- which
# is what /usr/bin/grep is on macOS -- treats the escape as a literal `b`, so the pattern
# would stop matching and this NEGATIVE assertion would pass silently on the one platform
# the package exists to support. POSIX bracket expressions behave the same everywhere.

python3 -m py_compile "$HERE/apply_macos_port.py" "$HERE/selftest.py"
"$HERE/selftest.py"
"$HERE/tests/build-selection-smoke.py"
"$HERE/tests/neon-parity.py"
"$HERE/tests/doctor-macos-smoke.sh"
bash -n "$HERE/install-macos.sh"
BASE=$(python3 "$HERE/apply_macos_port.py" --print-base-commit)
grep -q "BASE_COMMIT=\"$BASE\"" "$HERE/install-macos.sh"
echo "validate: installer and transformer use the same upstream commit"

CC_BIN=$(command -v cc || true)
if [ -n "$CC_BIN" ]; then
    "$CC_BIN" -std=c99 -Wall -Wextra -Werror \
        -c "$HERE/tests/darwin-platform-smoke.c" -o "$TMP/darwin-platform-smoke.o"
    echo "validate: Darwin API syntax smoke passed"
else
    echo "validate: no C compiler; skipped Darwin API syntax smoke"
fi

if command -v clang >/dev/null 2>&1; then
    if clang --target=aarch64-none-elf -ffreestanding -std=c99 -O2 \
        -ffp-contract=off -Wall -Wextra -Werror \
        -S "$HERE/tests/neon-smoke.c" -o "$TMP/neon-smoke.s" >/dev/null 2>&1 && \
       ! grep -Eq '[[:space:]](fmla|fmadd)[[:space:]]' "$TMP/neon-smoke.s"; then
        echo "validate: arm64 NEON compile smoke passed (no fused multiply-add)"
    else
        echo "validate: clang is present but lacks a usable aarch64 bare-metal target" >&2
        exit 1
    fi
else
    echo "validate: clang absent; skipped optional arm64 NEON cross-compile"
fi

# A manifest is worthless if nothing notices it going stale, and it went stale twice
# during review. Verify it here so an out-of-date SHA256SUMS fails the suite.
if command -v sha256sum >/dev/null 2>&1; then
    (cd "$HERE" && sha256sum -c SHA256SUMS --quiet) || {
        echo "validate: SHA256SUMS does not match the shipped files; regenerate it" >&2
        exit 1
    }
    echo "validate: SHA256SUMS matches every listed file"
elif command -v shasum >/dev/null 2>&1; then     # macOS ships shasum, not sha256sum
    (cd "$HERE" && shasum -a 256 -c SHA256SUMS >/dev/null) || {
        echo "validate: SHA256SUMS does not match the shipped files; regenerate it" >&2
        exit 1
    }
    echo "validate: SHA256SUMS matches every listed file"
else
    echo "validate: no sha256 tool; skipped manifest check"
fi

echo "validate: package checks passed"
