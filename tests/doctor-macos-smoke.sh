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
cat > "$TMP/bin/sysctl" <<'SH'
#!/bin/sh
case "$*" in *hw.logicalcpu*) echo 12;; *hw.memsize*) echo 68719476736;; *) exit 1;; esac
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
grep -q 'recommended memory preset: --preset desktop' "$TMP/output"
grep -q 'this machine can run the macOS-compatible Kimi K3 engine' "$TMP/output"
echo "doctor smoke: simulated Darwin/arm64 checks passed"
