# Kimi K3 in C – macOS-Port

Dieses Paket portiert **FareedKhan-dev/kimi-k3-in-c** auf macOS. Es ist auf den geprüften
Upstream-Commit `85ab2cd901aa81b70caac7711f06864d594b8ff3` festgelegt und unterstützt:

- Apple Silicon (`arm64`) mit nativen NEON-Pfaden für BF16- und MXFP4-Dot-Products
- Intel-Macs (`x86_64`) mit dem bestehenden AVX2/FMA-Pfad
- Stock Apple Clang ohne weitere C-Bibliotheken
- optionales Multi-Threading über Homebrew `libomp`

Das Paket enthält absichtlich **keine Modellgewichte** und auch keine Kopie des gesamten
Upstream-Repositories. Der Installer klont den exakt geprüften Stand, wendet den Port
kontextgeprüft an, baut ihn und führt die Tests ohne Modellgewichte aus.

## Direkt auf dem Mac installieren

Zuerst Apples Command Line Tools installieren, sofern noch nicht vorhanden:

```bash
xcode-select --install
```

Dann das ZIP entpacken und aus diesem Verzeichnis starten:

```bash
./install-macos.sh ~/src/kimi-k3-in-c-macos
```

Der Installer erkennt ein vorhandenes Homebrew-`libomp` automatisch. Für den ausdrücklich
threaded Build:

```bash
brew install libomp
./install-macos.sh --with-openmp ~/src/kimi-k3-in-c-macos
```

Für einen Build garantiert ohne OpenMP:

```bash
./install-macos.sh --without-openmp ~/src/kimi-k3-in-c-macos
```

Das Ergebnis enthält anschließend:

```text
~/src/kimi-k3-in-c-macos/bin/k3
~/src/kimi-k3-in-c-macos.patch
```

Der Patch ist eine normale, reviewbare Git-Diff-Datei, die der Installer aus dem
geänderten Checkout erzeugt.

## Einen vorhandenen Checkout portieren

Für einen sauberen Checkout des geprüften Stands:

```bash
git checkout 85ab2cd901aa81b70caac7711f06864d594b8ff3
python3 /pfad/zu/apply_macos_port.py .
git diff --check
make macos -j"$(sysctl -n hw.logicalcpu)"
make OMP_CFLAGS= OMP_LDFLAGS= test -j"$(sysctl -n hw.logicalcpu)"
```

Das Transformationsskript verwendet keine unscharfen Ersetzungen. Jede Quelltextstelle
muss exakt passen; bei einem geänderten Upstream bricht es ab. Ein bereits portierter
Checkout wird erkannt und kann gefahrlos ein zweites Mal verarbeitet werden.

## Was technisch geändert wird

Der Port ändert nicht nur Compiler-Flags:

1. `-mavx2/-mfma` werden ausschließlich für x86-64 gesetzt. Auf arm64 werden native
   NEON-Intrinsics für die zwei zentralen Dot-Product-Kerne eingebaut.
2. Linux-`O_DIRECT` wird auf macOS durch `F_NOCACHE` ersetzt. Für den gepufferten
   Fallback wird `F_RDADVISE` statt `posix_fadvise` verwendet.
3. `ru_maxrss` wird auf Darwin korrekt als Byte-Wert behandelt; Linux bleibt bei KiB.
4. Verfügbarer Speicher wird über Mach-VM-Statistiken statt `/proc/meminfo` ermittelt.
5. OpenMP ist auf macOS optional. Stock Apple Clang baut single-threaded; Homebrew
   `libomp` aktiviert den threaded Build.
6. GNU-spezifische Shell-Aufrufe wie `find -printf`, `find -maxdepth` und `stat -c`
   werden durch portable Varianten ersetzt.
7. Die GitHub-Actions-Konfiguration erhält native Jobs für `macos-15` und
   `macos-15-intel`, jeweils mit Make- und CMake-Tests.

## Paket prüfen

Die Offline-Prüfung benötigt Python 3, Make und einen C-Compiler; Clang und CMake werden
für zusätzliche Prüfungen verwendet:

```bash
./validate.sh
```

Sie prüft unter anderem die Idempotenz der Transformation, die Make-/CMake-Auswahl,
einen simulierten Apple-Silicon-Systemcheck, Darwin-API-Syntax und die ARM64-NEON-Pfade.
Details stehen in [VALIDATION.md](VALIDATION.md).

## Modell und Speicherbedarf

Der macOS-Port verkleinert das Modell nicht. Der Upstream nennt ungefähr **1,56 TB** für
den Checkpoint und etwa **109 GB** für den gepackten Trunk. Beides sollte auf schnellem,
lokalem Speicher liegen. Vor einem Download:

```bash
cd ~/src/kimi-k3-in-c-macos
K3_DOCTOR_PROBE_MB=256 ./scripts/k3-doctor.sh /Volumes/FastSSD/k3model
```

Ein Mac mit nur 8 GB Unified Memory ist trotz des nominellen Minimal-Presets kein
realistisches Ziel, weil macOS und weitere Prozesse ebenfalls Speicher benötigen.

## Verifizierungsgrenze

In dieser Arbeitsumgebung stand kein physischer macOS-Rechner und kein 1,56-TB-Checkpoint
zur Verfügung. Deshalb wurden hier die Portierungslogik, Quellkontexte, Shell-Skripte,
Darwin-Codepfade, ARM64-Intrinsics sowie Make/CMake-Auswahl geprüft, aber kein kompletter
93-Layer-Lauf auf echter Apple-Hardware gemessen. Der angewendete Port ergänzt native
GitHub-Actions-Jobs, die genau diesen Build- und Testschritt auf ARM64- und Intel-macOS
übernehmen.
