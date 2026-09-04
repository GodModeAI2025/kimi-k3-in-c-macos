# Kimi K3 in C, macOS-Port

[![CI](https://github.com/GodModeAI2025/kimi-k3-in-c-macos/actions/workflows/ci.yml/badge.svg)](https://github.com/GodModeAI2025/kimi-k3-in-c-macos/actions/workflows/ci.yml)

Dieses Paket portiert **FareedKhan-dev/kimi-k3-in-c** auf macOS: ein kontextgeprüfter
Patch, ein Installer und eine netzfreie Prüfsuite.

## Was du bekommst

- `apply_macos_port.py`, einen Transformer, der den Port auf den geprüften Upstream-Commit
  `85ab2cd901aa81b70caac7711f06864d594b8ff3` anwendet und bei jeder Abweichung abbricht
- `install-macos.sh`, der genau diesen Commit klont, portiert, baut und testet
- native NEON-Pfade für die BF16- und MXFP4-Dot-Products auf Apple Silicon
- `validate.sh` und `tests/`, eine Offline-Prüfsuite für dieses Paket selbst

## Was du nicht bekommst

- **keine Modellgewichte.** Der Checkpoint liegt bei etwa 1,56 TB, der gepackte Trunk bei
  etwa 109 GB. Der Download ist deine Sache.
- keine Kopie des Upstream-Repositories, der Installer holt sie beim Lauf
- kein Release, kein Tag, kein ZIP. Es gibt nur den Git-Klon dieses Repos.
- keine Messung auf echter Apple-Hardware, siehe
  [Verifizierungsgrenze](#verifizierungsgrenze)

## Für wen

Für Leute mit einem Mac und viel schnellem lokalem Speicher, die Kimi K3 von der Platte
streamen wollen und Sekunden pro Token als Größenordnung akzeptieren. Wer ein interaktiv
nutzbares Modell auf dem Mac sucht, liest zuerst
[CPU-Streaming oder MLX-Quants](#cpu-streaming-oder-mlx-quants).

## Zielplattform und was die CI davon abdeckt

Zielplattform ist **macOS 27 auf Apple Silicon**. macOS 26 (Tahoe) ist die letzte
Intel-fähige Version, deshalb ist der `x86_64`-Pfad nur noch für ältere Macs da und wird
auf macOS 27 nie ausgeführt.

Automatisch geprüft wird auf macOS 27 allerdings nichts. GitHub bietet kein
`macos-27`-Image an. Der macOS-Job dieses Repos läuft auf `macos-latest`, und die Matrix,
die der Port in die Upstream-CI einsetzt, nennt `macos-26`, `macos-15` und
`macos-26-intel`. Die Zielplattform ist eine Absicht, keine Messung.

Zwei verschiedene CI-Konfigurationen sind im Spiel. Das Badge oben gehört zur ersten:

| Konfiguration | läuft wo | prüft |
| --- | --- | --- |
| `.github/workflows/ci.yml`, das Badge oben | in diesem Repo | das Paket: Transformer, Prüfskripte, Manifest, Konsistenz von Code und Dokumentation. Kein Upstream-Quelltext, kein Build der Engine. |
| die Jobs, die der Port einsetzt | in einem portierten Upstream-Checkout | Make- und CMake-Build der Engine auf `macos-26`, `macos-15` und `macos-26-intel`, ohne Modellgewichte |

Das Badge sagt also nicht, dass die Engine auf Apple Silicon baut. Diese Aussage kann in
diesem Repo gar nicht entstehen, weil hier kein Upstream-Quelltext liegt.

## Direkt auf dem Mac installieren

Zuerst Apples Command Line Tools installieren, sofern noch nicht vorhanden:

```bash
xcode-select --install
```

Dann dieses Repo klonen und den Installer aus dem Klon starten:

```bash
git clone https://github.com/GodModeAI2025/kimi-k3-in-c-macos.git
cd kimi-k3-in-c-macos
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
   `$(brew --prefix libomp)/lib/libomp.dylib`, denn `brew --prefix` allein taugt nicht als
   Nachweis: es druckt auch für nicht installierte Formeln einen Pfad und gibt 0 zurück.
6. GNU-spezifische Shell-Aufrufe wie `find -printf`, `find -maxdepth` und `stat -c`
   werden durch portable Varianten ersetzt.
7. Alle Build-Targets, auch `debug`, `asan` und `ubsan`, setzen `-ffp-contract=off`.
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
11. Die GitHub-Actions-Konfiguration des Upstream-Checkouts erhält native Jobs für
   `macos-26`, `macos-15` und `macos-26-intel`, jeweils mit Make- und CMake-Tests.

## Paket prüfen

Die Offline-Prüfung benötigt Python 3, Make und einen C-Compiler; Clang und CMake werden
für zusätzliche Prüfungen verwendet:

```bash
./validate.sh
```

Sie prüft unter anderem die Idempotenz der Transformation, die Make-/CMake-Auswahl,
einen simulierten Apple-Silicon-Systemcheck, Darwin-API-Syntax und die ARM64-NEON-Pfade.
Details stehen in [VALIDATION.md](VALIDATION.md).

Nach jeder Änderung an einer versionierten Datei gehört das Manifest neu erzeugt, sonst
schlägt `validate.sh` und mit ihm die CI fehl:

```bash
./make-sha256sums.sh
```

## Modell und Speicherbedarf

Der macOS-Port verkleinert das Modell nicht. Der Upstream nennt ungefähr **1,56 TB** für
den Checkpoint und etwa **109 GB** für den gepackten Trunk. Beides sollte auf schnellem,
lokalem Speicher liegen. Vor einem Download:

```bash
cd ~/src/kimi-k3-in-c-macos
K3_DOCTOR_PROBE_MB=256 ./scripts/k3-doctor.sh /Volumes/FastSSD/k3model
```

Ein Mac mit nur 8 GB Unified Memory ist trotz des nominellen Minimal-Presets kein
realistisches Ziel, weil macOS und weitere Prozesse ebenfalls Speicher benötigen. Der
Doctor weist alles unter 10 GiB installiertem Speicher ab.

## CPU-Streaming oder MLX-Quants

Die Frage kommt oft, und für Kimi K3 fällt die Antwort kurz aus: eine MLX-Variante dieses
Modells passt auf keinen Mac. Das ist Arithmetik, keine Messung. Kimi K3 hat 2,78
Billionen Parameter. Bei 4 Bit pro Parameter liegen allein die Gewichte bei rund 1,4 TB,
der größte lieferbare Mac hat 512 GB Unified Memory. MLX hält die Gewichte im Unified
Memory, also fehlt selbst nach einer aggressiven Quantisierung fast der Faktor drei.

Die Entscheidung, die sich wirklich stellt, ist deshalb eine andere:

| | Kimi K3 von der Platte gestreamt (dieses Paket) | ein kleineres Modell als MLX-Quant |
| --- | --- | --- |
| Gewichte im RAM | nein, es wird pro Layer nachgeladen | ja, vollständig |
| Speicher | ab 10 GiB RAM, dafür rund 1,56 TB schneller lokaler Speicher | so viel RAM, wie der Quant groß ist |
| Größenordnung | Sekunden pro Token | Token pro Sekunde |
| brauchbar für | Batch, Offline-Auswertung, ein Modell dieser Größe überhaupt laufen sehen | interaktive Nutzung |
| Lizenz | Apache 2.0 für den Code des Upstream und dieses Ports, die Gewichte haben ihre eigene | hängt am jeweiligen Modell |

**Zahlen für macOS gibt es hier nicht.** Der Doctor nennt in seiner Preset-Leiter
veröffentlichte Linux-Werte von etwa 19 bis 32 Sekunden pro Token, je nach Speicherbudget,
und weist darauf hin, dass die Engine bei den kleinsten Budgets rund 135 GB pro Token von
der Platte liest. Auf Apple-Hardware ist dieser Port nie gemessen worden, weder Durchsatz
noch Latenz. Wer eine Zahl für den Vergleich braucht, muss sie selbst messen. Geschätzte
Werte stünden hier nur, um eine Tabelle zu füllen.

## Roadmap

Der Stand ist ein Schnappschuss. Was ansteht, in dieser Reihenfolge:

1. **Über den Upstream-Drift entscheiden.** Der Port hängt an `85ab2cd9` vom 1. August
   2026, festgezogen am 3. August 2026. Nachgeprüft am 4. September 2026: Upstream-`main` steht bei `117e9d29` vom
   26. August 2026 und ist 36 Commits voraus, mit einem eigenen Job
   `build-and-test-macos` auf `macos-14`. Zwei Wege stehen offen, und nur einer wird
   gegangen: Rebase auf den neuen Stand samt Zusammenführung der beiden macOS-Jobs, oder
   das Paket bleibt ausdrücklich ein eingefrorener Schnappschuss auf `85ab2cd9`. Bis zur
   Entscheidung gilt der Schnappschuss.
2. **Doctor-Pin nachziehen.** `apply_macos_port.py` nagelt `scripts/k3-doctor.sh` per
   SHA-256 auf `66b13087…` fest, der aktuelle Upstream-Doctor hasht auf `91b5e903…`.
   Gegen Upstream-`main` bricht der Transformer also ab, wie vorgesehen. Der Pin gehört
   zu Punkt 1 und wird nicht einzeln nachgezogen.
3. **Release oder keins.** `VERSION` steht auf 1.5.0, es gibt weder Tag noch Release.
   Ein Release friert Punkt 1 ein, kommt also erst danach.
4. **Auf echter Hardware messen.** Für diesen Port existiert kein einziger Durchsatzwert
   auf Apple Silicon. Solange das so bleibt, steht im Abschnitt oben keine Zahl.

Nicht geplant ist eine vorgebaute, signierte `k3`-Binary. Sie verlangt Developer-ID,
Notarisierung und die Weiterverbreitung von Upstream-Code, und ihr Nutzen gegenüber dem
Klon ist gering.

## Verifizierungsgrenze

In dieser Arbeitsumgebung stand kein physischer macOS-Rechner und kein 1,56-TB-Checkpoint
zur Verfügung. Deshalb wurden hier die Portierungslogik, Quellkontexte, Shell-Skripte,
Darwin-Codepfade, ARM64-Intrinsics sowie Make/CMake-Auswahl geprüft, aber kein kompletter
93-Layer-Lauf auf echter Apple-Hardware gemessen. Der angewendete Port ergänzt native
GitHub-Actions-Jobs, die genau diesen Build- und Testschritt auf ARM64- und Intel-macOS
übernehmen, sobald sie in einem Repository mit dem Upstream-Quelltext laufen. In diesem
Repository laufen sie nicht.

Was **tatsächlich ausgeführt** wurde: der Port wird auf einen echten Klon des angehefteten
Commits angewendet, und der portierte Baum baut auf Linux/x86-64 warnungsfrei und besteht
die vollständige gewichtslose Testsuite (`make test` und `ctest`, letzteres mit
`-DK3_ENABLE_OPENMP=OFF` wie in der macOS-CI). Damit ist belegt, dass der Port die
Referenzplattform nicht beschädigt, und mehr lässt sich ohne Apple-Hardware nicht
behaupten. Die Darwin-spezifischen Zweige selbst wurden nie ausgeführt, nur übersetzt und
gelesen. Was dieser Prüfstand abdeckt und was nicht, steht Punkt für Punkt in
[VALIDATION.md](VALIDATION.md).
