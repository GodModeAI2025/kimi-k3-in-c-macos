#!/usr/bin/env bash
# Clone the reviewed upstream revision, apply the macOS port, build it, and run the
# weightless correctness suite. No model weights are downloaded by this installer.
set -euo pipefail

REPO_URL="https://github.com/FareedKhan-dev/kimi-k3-in-c.git"
BASE_COMMIT="85ab2cd901aa81b70caac7711f06864d594b8ff3"
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DEST="kimi-k3-in-c-macos"
OPENMP_MODE=auto
RUN_TESTS=1
RUN_BUILD=1

usage() {
    cat <<'EOF'
usage: ./install-macos.sh [options] [destination]

options:
  --with-openmp      require Homebrew libomp and build threaded
  --without-openmp   force the stock Apple Clang build without OpenMP
  --no-test          build but skip the weightless correctness suite
  --apply-only       clone and patch, but do not build or test
  -h, --help

examples:
  ./install-macos.sh                     # auto-detect Homebrew libomp
  ./install-macos.sh --with-openmp ~/src/kimi-k3-in-c-macos
  ./install-macos.sh --without-openmp ~/src/kimi-k3-in-c-macos
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --with-openmp) OPENMP_MODE=required ;;
        --without-openmp) OPENMP_MODE=off ;;
        --no-test) RUN_TESTS=0 ;;
        --apply-only) RUN_BUILD=0; RUN_TESTS=0 ;;
        -h|--help) usage; exit 0 ;;
        --) shift; break ;;
        -*) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
        *) DEST=$1 ;;
    esac
    shift
done
if [ "$#" -gt 0 ]; then
    DEST=$1
    shift
fi
if [ "$#" -gt 0 ]; then
    echo "only one destination may be supplied" >&2
    exit 2
fi

if [ "$(uname -s)" != Darwin ]; then
    echo "install-macos.sh must be run on macOS." >&2
    echo "To apply the source transformation elsewhere, run apply_macos_port.py directly." >&2
    exit 1
fi

for tool in git python3 make cc; do
    command -v "$tool" >/dev/null 2>&1 || {
        if [ "$tool" = cc ]; then
            echo "missing C compiler; run: xcode-select --install" >&2
        else
            echo "missing required tool: $tool" >&2
        fi
        exit 1
    }
done

# `brew --prefix libomp` prints a path and exits 0 even when libomp is NOT installed, so
# a non-empty prefix is not evidence. Require the dylib, or the build fails at link.
OMP_PREFIX=""
if [ "$OPENMP_MODE" != off ] && command -v brew >/dev/null 2>&1; then
    _omp_candidate=$(brew --prefix libomp 2>/dev/null || true)
    if [ -n "$_omp_candidate" ] && [ -r "$_omp_candidate/lib/libomp.dylib" ]; then
        OMP_PREFIX=$_omp_candidate
    fi
fi
if [ "$OPENMP_MODE" = required ] && [ -z "$OMP_PREFIX" ]; then
    echo "--with-openmp requires Homebrew libomp; run: brew install libomp" >&2
    exit 1
fi

if [ -e "$DEST" ]; then
    echo "destination already exists: $DEST" >&2
    echo "Use apply_macos_port.py to patch an existing clean checkout." >&2
    exit 1
fi

mkdir -p "$(dirname -- "$DEST")"
echo "cloning $REPO_URL"
git clone "$REPO_URL" "$DEST"
git -C "$DEST" checkout --detach "$BASE_COMMIT"
ACTUAL_COMMIT=$(git -C "$DEST" rev-parse HEAD)
[ "$ACTUAL_COMMIT" = "$BASE_COMMIT" ] || {
    echo "checked-out commit $ACTUAL_COMMIT does not match reviewed commit $BASE_COMMIT" >&2
    exit 1
}
git -C "$DEST" checkout -b macos-port

python3 "$SCRIPT_DIR/apply_macos_port.py" "$DEST"
git -C "$DEST" diff --check

# Include the newly-created documentation file when exporting a conventional patch.
git -C "$DEST" add -N docs/MACOS.md
PATCH_OUT="${DEST%/}.patch"
git -C "$DEST" diff --binary > "$PATCH_OUT"
git -C "$DEST" reset -- docs/MACOS.md >/dev/null

echo "wrote reviewable patch: $PATCH_OUT"

if [ "$RUN_BUILD" -eq 1 ]; then
    JOBS=$(sysctl -n hw.logicalcpu 2>/dev/null || echo 1)
    if [ -n "$OMP_PREFIX" ]; then
        OMP_CFLAGS="-Xpreprocessor -fopenmp -I$OMP_PREFIX/include"
        OMP_LDFLAGS="-L$OMP_PREFIX/lib -Wl,-rpath,$OMP_PREFIX/lib -lomp"
        if [ "$OPENMP_MODE" = required ]; then
            make -C "$DEST" macos-openmp -j"$JOBS"
        else
            echo "Homebrew libomp detected; using the threaded macOS build"
            make -C "$DEST" all -j"$JOBS"
        fi
    else
        make -C "$DEST" macos -j"$JOBS"
        OMP_CFLAGS=""
        OMP_LDFLAGS=""
    fi

    if [ "$RUN_TESTS" -eq 1 ]; then
        make -C "$DEST" OMP_CFLAGS="$OMP_CFLAGS" OMP_LDFLAGS="$OMP_LDFLAGS" \
            test -j"$JOBS"
    fi
fi

cat <<EOF

macOS port ready:
  source : $DEST
  binary : $DEST/bin/k3
  patch  : $PATCH_OUT

Run the machine/storage check before downloading model weights:
  cd "$DEST"
  K3_DOCTOR_PROBE_MB=256 ./scripts/k3-doctor.sh
EOF
