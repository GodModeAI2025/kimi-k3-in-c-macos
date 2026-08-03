#!/usr/bin/env bash
# Run the generated machine doctor against a deterministic fake Apple Silicon host.
set -euo pipefail
HERE=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=${TMPDIR:-/tmp}/k3-doctor-smoke.$$
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
mkdir -p "$TMP/bin" "$TMP/model"

python3 - "$HERE/apply_macos_port.py" "$TMP/doctor.sh" <<'PY'
import importlib.util
import sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("port", sys.argv[1])
assert spec and spec.loader
port = importlib.util.module_from_spec(spec)
spec.loader.exec_module(port)
Path(sys.argv[2]).write_text(port.DOCTOR, encoding="utf-8")
PY
chmod +x "$TMP/doctor.sh"

cat > "$TMP/bin/uname" <<'SH'
#!/bin/sh
case "$1" in -s) echo Darwin;; -m) echo arm64;; *) echo Darwin;; esac
SH
# hw.memsize is deliberately 256 GiB while vm_stat reports ~38 GiB reclaimable, so the
# two land in DIFFERENT preset buckets (server vs desktop). With both in one bucket the
# preset assertion below would also hold when the vm_stat parse fails completely and the
# script falls back to AVAIL_GB=$MEM_GB -- i.e. the test could not see the bug it exists
# to catch.
cat > "$TMP/bin/sysctl" <<'SH'
#!/bin/sh
case "$*" in *hw.logicalcpu*) echo 12;; *hw.memsize*) echo 274877906944;; *) exit 1;; esac
SH
cat > "$TMP/bin/vm_stat" <<'SH'
#!/bin/sh
cat <<'OUT'
Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                               1000000.
Pages inactive:                           1500000.
Pages speculative:                         50000.
OUT
SH
cat > "$TMP/bin/df" <<'SH'
#!/bin/sh
cat <<'OUT'
Filesystem 1024-blocks Used Available Capacity Mounted on
/dev/diskX 3000000000 1 2500000000 1% /tmp
OUT
SH
cat > "$TMP/bin/cc" <<'SH'
#!/bin/sh
echo 'Apple clang version 18.0.0'
SH
cat > "$TMP/bin/make" <<'SH'
#!/bin/sh
echo 'GNU Make 4.4'
SH
cat > "$TMP/bin/python3" <<'SH'
#!/bin/sh
echo 'Python 3.13.0'
SH
cat > "$TMP/bin/brew" <<'SH'
#!/bin/sh
exit 1
SH
chmod +x "$TMP/bin"/*

PATH="$TMP/bin:/usr/bin:/bin" K3_DOCTOR_PROBE_MB=0 \
    "$TMP/doctor.sh" "$TMP/model" > "$TMP/output"
grep -q 'Kimi K3, environment check (Darwin/arm64)' "$TMP/output"
grep -q 'NEON: native bf16 and MXFP4 dot-product paths enabled' "$TMP/output"
grep -q 'total: 256 GiB, reclaimable now: 38 GiB' "$TMP/output" || {
    echo "doctor smoke: vm_stat parse produced the wrong reclaimable figure" >&2
    sed -n '/^memory/,/^storage/p' "$TMP/output" >&2
    exit 1
}
# desktop, not server: proves the number came from vm_stat and not from the hw.memsize
# fallback. Speculative pages are excluded on purpose (they are already inside free_count
# in the raw Mach struct), so the expected figure is free + inactive only.
grep -q 'recommended memory preset: --preset desktop' "$TMP/output"
grep -q 'this machine can run the macOS-compatible Kimi K3 engine' "$TMP/output"
grep -q 'OpenMP not detected' "$TMP/output"

# `brew --prefix libomp` answers with a path and exit 0 even when the formula is NOT
# installed, so a doctor that trusts it reports OpenMP on almost every Mac with Homebrew
# and then recommends a `make` that dies at the link step. Both halves are pinned here.
mkdir -p "$TMP/brew-prefix/lib"
cat > "$TMP/bin/brew" <<SH
#!/bin/sh
[ "\$1" = "--prefix" ] && { echo "$TMP/brew-prefix"; exit 0; }
exit 1
SH
chmod +x "$TMP/bin/brew"

PATH="$TMP/bin:/usr/bin:/bin" K3_DOCTOR_PROBE_MB=0 \
    "$TMP/doctor.sh" "$TMP/model" > "$TMP/output-nolibomp"
grep -q 'OpenMP not detected' "$TMP/output-nolibomp" || {
    echo "doctor smoke: reported libomp present although only the prefix exists" >&2
    exit 1
}

: > "$TMP/brew-prefix/lib/libomp.dylib"
PATH="$TMP/bin:/usr/bin:/bin" K3_DOCTOR_PROBE_MB=0 \
    "$TMP/doctor.sh" "$TMP/model" > "$TMP/output-libomp"
grep -q 'Homebrew libomp detected' "$TMP/output-libomp" || {
    echo "doctor smoke: failed to detect an installed libomp" >&2
    exit 1
}

# The storage probe is skipped above (PROBE_MB=0). Run it once for real so the dd,
# timing and awk rate arithmetic are executed rather than assumed. macOS always ships
# /usr/bin/time; a Linux CI box may not, and the probe is required to degrade to a
# warning there rather than abort or print a garbage rate.
rm -f "$TMP/bin/df"
PATH="$TMP/bin:/usr/bin:/bin" K3_DOCTOR_PROBE_MB=1 \
    "$TMP/doctor.sh" "$TMP/model" > "$TMP/output-probe"
grep -q 'measuring sequential read (1 MB temporary file)' "$TMP/output-probe" || {
    echo "doctor smoke: the storage probe block never ran" >&2
    exit 1
}
if [ -x /usr/bin/time ]; then
    grep -qE 'sequential read probe: [0-9]+ MB/s' "$TMP/output-probe" || {
        echo "doctor smoke: the storage probe produced no parseable rate" >&2
        sed -n '/storage/,/model/p' "$TMP/output-probe" >&2
        exit 1
    }
else
    grep -q 'duration could not be parsed' "$TMP/output-probe" || {
        echo "doctor smoke: probe did not degrade cleanly without /usr/bin/time" >&2
        exit 1
    }
fi
# The probe file is written into the model directory and must never be left behind.
if find "$TMP/model" -name '.k3_doctor_probe*' | grep -q .; then
    echo "doctor smoke: the storage probe left its temporary file behind" >&2
    exit 1
fi

# A busy 64 GiB Mac showing only ~5 GiB free+inactive must NOT be refused. free+inactive
# omits reclaimable file-backed pages, so the instantaneous figure routinely dips below
# the engine's floor on a machine that runs it perfectly well once macOS evicts caches.
cat > "$TMP/bin/sysctl" <<'SH'
#!/bin/sh
case "$*" in *hw.logicalcpu*) echo 12;; *hw.memsize*) echo 68719476736;; *) exit 1;; esac
SH
cat > "$TMP/bin/vm_stat" <<'SH'
#!/bin/sh
cat <<'OUT'
Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                                100000.
Pages inactive:                            230000.
Pages speculative:                          50000.
OUT
SH
chmod +x "$TMP/bin/sysctl" "$TMP/bin/vm_stat"
set +e
PATH="$TMP/bin:/usr/bin:/bin" K3_DOCTOR_PROBE_MB=0 \
    "$TMP/doctor.sh" "$TMP/model" > "$TMP/output-busy"
busy_status=$?
set -e
[ "$busy_status" -eq 0 ] || {
    echo "doctor smoke: refused a 64 GiB Mac that was merely busy (exit $busy_status)" >&2
    sed -n '/^memory/,/^storage/p' "$TMP/output-busy" >&2
    exit 1
}
grep -q 'close applications' "$TMP/output-busy" || {
    echo "doctor smoke: no warning about low free memory on a busy Mac" >&2
    exit 1
}

# A genuinely too-small Mac must still be refused, or the check above would have turned
# the floor into a no-op.
cat > "$TMP/bin/sysctl" <<'SH'
#!/bin/sh
case "$*" in *hw.logicalcpu*) echo 8;; *hw.memsize*) echo 8589934592;; *) exit 1;; esac
SH
chmod +x "$TMP/bin/sysctl"
set +e
PATH="$TMP/bin:/usr/bin:/bin" K3_DOCTOR_PROBE_MB=0 \
    "$TMP/doctor.sh" "$TMP/model" > "$TMP/output-small"
small_status=$?
set -e
[ "$small_status" -ne 0 ] || {
    echo "doctor smoke: an 8 GiB Mac was cleared to run the model" >&2
    exit 1
}

echo "doctor smoke: simulated Darwin/arm64 checks passed"
