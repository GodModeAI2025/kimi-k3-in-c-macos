# Validierungsbericht

**Datum:** 3. August 2026
**Bezugsstand:** `85ab2cd901aa81b70caac7711f06864d594b8ff3`
**Ziel-Plattform:** macOS 27, Apple Silicon

## Erfolgreich ausgeführte Prüfungen

### Port auf echtem Upstream

- Klon des angehefteten Commits, Transformation angewendet, Diff erzeugt:
  13 Dateien, 534 Einfügungen, 126 Löschungen
- der portierte Baum baut auf Linux/x86-64 **ohne eine einzige Warnung**
  (`-Wall -Wextra -Wpointer-arith -Wshadow -Wvla`)
- die vollständige gewichtslose Testsuite läuft auf dem portierten Baum durch:
  `make test` endet mit `VERDICT: ENGINE MATCHES THE REFERENCE EXACTLY`
- CMake-Pfad mit `-DK3_ENABLE_OPENMP=OFF` (die macOS-CI-Konfiguration) baut und besteht
  alle sechs `ctest`-Tests

Damit ist belegt, dass der Port die Referenzplattform nicht beschädigt. Das ist die
stärkste Aussage, die sich ohne Apple-Hardware treffen lässt.

### Transformationslogik

- Python-Syntaxprüfung für `apply_macos_port.py`, `selftest.py` und die Prüfskripte
- vollständiger Kontext-Test aller Ersetzungen
- zweiter Durchlauf auf einem bereits portierten Baum: 34-mal `already patched`,
  null `changed`
- **Abbruchsicherheit:** wird eine Kontextstelle künstlich verändert, bricht der
  Transformer mit Exit-Code 1 ab und lässt den Arbeitsbaum **unberührt**. Alle
  Schreibvorgänge werden im Speicher gesammelt und erst nach der letzten erfolgreichen
  Ersetzung geschrieben.
- Prüfung, dass GNU-spezifische Download-/Pack-Aufrufe entfernt werden
- Prüfung auf die erwarteten Darwin-, NEON- und CI-Marker

### C- und Architekturpfade

- ARM64-Cross-Compile der verwendeten NEON-Intrinsics mit Clang und
  `--target=aarch64-none-elf`
- Compile-Smoke-Test für `F_NOCACHE`, `F_RDADVISE`, Darwin-`ru_maxrss` und die verwendeten
  Mach-VM-Typen/APIs
- **`tests/neon-parity.py`** prüft die tatsächlich injizierten Kernel, nicht eine
  Handkopie: es extrahiert die `__aarch64__`-Blöcke aus `apply_macos_port.py`, vergleicht
  ihre vollständige Intrinsic-Reihenfolge mit `tests/neon-smoke.c` und schlägt bei einer
  vertauschten Lane fehl (verifiziert: eine simulierte `vget_low`/`vget_high`-Vertauschung
  wird mit Diff gemeldet).
- gemessen, nicht angenommen: die NEON-Intrinsics werden von Clang **auch ohne**
  `-ffp-contract=off` nicht zu `FMLA` zusammengezogen. Zusammengezogen wird die
  *skalare* Reduktion (`s0 += w[i] * x[i]`) — auf aarch64 immer, weil FMA dort zur
  Basis-ISA gehört. Deshalb tragen jetzt alle Targets die Flagge.

### Build-Systeme

- Make-Auswahl simuliert für Darwin/arm64, Darwin/x86_64 und Linux/x86_64
- CMake-Konfiguration und Mini-Build für den simulierten arm64/macOS-Pfad
- Kontrolle, dass dort weder `-mavx2` noch `-mfma` ausgegeben werden
- **OpenMP-Erkennung gegen einen nachgebauten Homebrew geprüft**, in allen drei realen
  Konfigurationen: kein Homebrew, Homebrew ohne `libomp`, Homebrew mit `libomp`. Nur der
  dritte Fall setzt `-lomp`.

### Shell und Systemcheck

- `bash -n` für Installer und alle generierten Shell-Skripte
- simulierter Darwin/arm64-Lauf von `k3-doctor.sh`
- portable Shard-Zählung und Dateigrößenlogik

### Paketprüfung

Ausgeführt mit:

```bash
./validate.sh
```

Erwartete Abschlussmeldungen:

```text
selftest: all context replacements and idempotency checks passed
build-selection smoke: Make and CMake architecture logic passed
neon-parity: injected NEON blocks match tests/neon-smoke.c
neon-parity: injected NEON kernels emit no FMA at any contraction setting
neon-parity: the scalar reduction DOES fuse on aarch64 without -ffp-contract=off
doctor smoke: simulated Darwin/arm64 checks passed
validate: installer and transformer use the same upstream commit
validate: Darwin API syntax smoke passed
validate: arm64 NEON compile smoke passed (no fused multiply-add)
validate: package checks passed
```

## Nicht in dieser Umgebung ausführbar

Diese Grenze ist hart und wird hier nicht beschönigt:

- kein nativer Build auf einem realen Apple-Silicon-Mac
- kein nativer Build auf einem realen Intel-Mac
- kein vollständiger Testlauf mit dem etwa 1,56 TB großen Checkpoint
- keine Performance-Messung eines 93-Layer-Laufs auf Apple-Hardware
- die Darwin-Codepfade (`F_NOCACHE`, `F_RDADVISE`, Mach-VM-Statistiken, `ru_maxrss`)
  wurden auf Syntax und API-Verwendung geprüft, aber **nie ausgeführt**
- es gibt keinen macOS-SDK und keinen Emulator in dieser Umgebung, also kompiliert
  nirgends der *echte* `k3_ops.c` für Darwin/arm64; geprüft werden die injizierten
  NEON-Blöcke einzeln gegen ein Bare-Metal-aarch64-Target

Dafür ergänzt der Port GitHub-Actions-Jobs für `macos-26`, `macos-15` und
`macos-26-intel`. Diese Jobs bauen den Port mit Make und CMake und führen die Tests ohne
Modellgewichte aus, sobald die Änderungen in einem GitHub-Branch oder Pull Request laufen.
`macos-26` ist das neueste allgemein verfügbare Image und damit der beste verfügbare
Stellvertreter für macOS 27; sobald ein `macos-27`-Image GA ist, gehört es in die Matrix.
Für Intel gibt es keinen macOS-27-Job und wird es keinen geben, weil macOS 26 die letzte
Intel-fähige Version ist.
