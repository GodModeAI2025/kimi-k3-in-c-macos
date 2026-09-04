# Kimi K3 in C – macOS-Port

[![CI](https://github.com/GodModeAI2025/kimi-k3-in-c-macos/actions/workflows/ci.yml/badge.svg)](https://github.com/GodModeAI2025/kimi-k3-in-c-macos/actions/workflows/ci.yml)

Dieses Paket portiert **FareedKhan-dev/kimi-k3-in-c** auf macOS. Es ist auf den geprüften
Upstream-Commit `85ab2cd901aa81b70caac7711f06864d594b8ff3` festgelegt und unterstützt:

- Apple Silicon (`arm64`) mit nativen NEON-Pfaden für BF16- und MXFP4-Dot-Products
- Intel-Macs (`x86_64`) mit dem bestehenden AVX2/FMA-Pfad
- Stock Apple Clang ohne weitere C-Bibliotheken
- optionales Multi-Threading über Homebrew `libomp`

Zielplattform ist **macOS 27 auf Apple Silicon**. macOS 26 (Tahoe) ist die letzte
Intel-fähige Version, deshalb ist der `x86_64`-Pfad nur noch für ältere Macs da und wird
auf macOS 27 nie ausgeführt.

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
   `libomp` aktiviert den threaded Build. Erkannt wird `libomp` über die Datei
   `$(brew --prefix libomp)/lib/libomp.dylib` — `brew --prefix` allein taugt nicht als
   Nachweis, weil es auch für nicht installierte Formeln einen Pfad druckt und 0 zurückgibt.
6. GNU-spezifische Shell-Aufrufe wie `find -printf`, `find -maxdepth` und `stat -c`
   werden durch portable Varianten ersetzt.
7. Alle Build-Targets — auch `debug`, `asan` und `ubsan` — setzen `-ffp-contract=off`.
   Auf aarch64 gehört FMA zur Basis-ISA, deshalb würde Clang die skalare Reduktion sonst
   verschmelzen und das Ergebnis wiche von der Referenz ab.
8. `k3_run.c` schaltet auf `_DARWIN_C_SOURCE` um. Unter `_POSIX_C_SOURCE` ersetzt Darwin
   die benannten Felder von `struct rusage` durch `ru_opaque[14]`; ohne diese Änderung
   übersetzt die Datei auf macOS überhaupt nicht.
9. Lesevorgänge werden auf 1 GiB pro Aufruf begrenzt. Darwin lehnt jede Anforderung über
   `INT_MAX` mit `EINVAL` ab, während Linux kappt und eine kurze positive Länge liefert;
   `embed_tokens`, `lm_head` (je 2,35 GB) und Trunk-Layer 0 (2,34 GB) liegen darüber.
10. Verfügbarer Speicher zählt `free + inactive`. Die spekulativen Seiten stecken in XNU
   bereits in `free_count`. Auf macOS entscheidet die **installierte** Speichermenge über
   die harte Untergrenze, damit ein ausgelasteter 64-GiB-Mac nicht abgewiesen wird.
11. Die GitHub-Actions-Konfiguration erhält native Jobs für `macos-26`, `macos-15` und
   `macos-26-intel`, jeweils mit Make- und CMake-Tests.

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

Was **tatsächlich ausgeführt** wurde: der Port wird auf einen echten Klon des angehefteten
Commits angewendet, und der portierte Baum baut auf Linux/x86-64 warnungsfrei und besteht
die vollständige gewichtslose Testsuite (`make test` und `ctest`, letzteres mit
`-DK3_ENABLE_OPENMP=OFF` wie in der macOS-CI). Damit ist belegt, dass der Port die
Referenzplattform nicht beschädigt — mehr lässt sich ohne Apple-Hardware nicht behaupten.
Die Darwin-spezifischen Zweige selbst wurden nie ausgeführt, nur übersetzt und gelesen.
Was dieser Prüfstand abdeckt und was nicht, steht Punkt für Punkt in
[VALIDATION.md](VALIDATION.md).
