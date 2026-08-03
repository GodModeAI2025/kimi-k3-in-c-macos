# Validierungsbericht

**Datum:** 3. August 2026  
**Bezugsstand:** `85ab2cd901aa81b70caac7711f06864d594b8ff3`

## Erfolgreich ausgeführte Prüfungen

### Transformationslogik

- Python-Syntaxprüfung für `apply_macos_port.py`, `selftest.py` und die Build-Prüfung
- vollständiger Kontext-Test aller Ersetzungen
- zweiter Durchlauf auf einem bereits portierten Baum: ausschließlich
  `already patched` beziehungsweise bestehende Neudateien
- Prüfung, dass GNU-spezifische Download-/Pack-Aufrufe entfernt werden
- Prüfung auf die erwarteten Darwin-, NEON- und CI-Marker

### C- und Architekturpfade

- ARM64-Cross-Compile der verwendeten NEON-Intrinsics mit Clang und
  `--target=aarch64-none-elf`
- Compile-Smoke-Test für `F_NOCACHE`, `F_RDADVISE`, Darwin-`ru_maxrss` und die verwendeten
  Mach-VM-Typen/APIs
- getrennte Multiply/Add-Sequenz statt FMA, damit die bestehende Reduktionsstruktur nicht
  durch implizite Kontraktion verändert wird

### Build-Systeme

- Make-Auswahl simuliert für:
  - Darwin/arm64: keine x86-Flags, kein zwingendes OpenMP
  - Darwin/x86_64: `-march=native`, keine zwingende OpenMP-Abhängigkeit
  - Linux/x86_64: bestehende `-fopenmp`-Vorgabe bleibt erhalten
- CMake-Konfiguration und Mini-Build für den simulierten arm64/macOS-Pfad
- Kontrolle, dass dort weder `-mavx2` noch `-mfma` ausgegeben werden

### Shell und Systemcheck

- `bash -n` für Installer und alle generierten Shell-Skripte
- simulierter Darwin/arm64-Lauf von `k3-doctor.sh`
- erkannte Werte im Test: Apple Silicon, NEON aktiv, 64 GiB Gesamtspeicher,
  38 GiB reclaimable, Preset `desktop`
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
doctor smoke: simulated Darwin/arm64 checks passed
validate: installer and transformer use the same upstream commit
validate: Darwin API syntax smoke passed
validate: arm64 NEON compile smoke passed (no fused multiply-add)
validate: package checks passed
```

## Nicht in dieser Umgebung ausführbar

- nativer Build auf einem realen Apple-Silicon-Mac
- nativer Build auf einem realen Intel-Mac
- vollständiger Testlauf mit dem ungefähr 1,56 TB großen Checkpoint
- Performance-Messung eines 93-Layer-Inferenzlaufs auf Apple-Hardware

Dafür ergänzt der Port GitHub-Actions-Jobs für `macos-15` und `macos-15-intel`. Diese Jobs
bauen den Port mit Make und CMake und führen die Tests ohne Modellgewichte aus, sobald die
Änderungen in einem GitHub-Branch oder Pull Request laufen.
