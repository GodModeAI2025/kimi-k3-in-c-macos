# Upstream-Bezug

- Repository: https://github.com/FareedKhan-dev/kimi-k3-in-c
- geprüfter Commit: `85ab2cd901aa81b70caac7711f06864d594b8ff3`
- Stand des Ports: 3. August 2026
- Upstream-Lizenz: Apache License 2.0

Der Installer checkt exakt diesen Commit aus. `apply_macos_port.py` prüft zusätzlich jede
zu ändernde Quelltextstelle auf den erwarteten Kontext und bricht bei Abweichungen ab.

## Änderungskennzeichnung

Beim Anwenden werden unter anderem folgende Upstream-Dateien verändert:

- `Makefile`
- `CMakeLists.txt`
- `README.md`
- `src/core/k3_ops.c`
- `src/io/k3_st.c`
- `src/io/k3_trunk.c`
- `src/cache/k3_cache.c`
- `src/cli/k3_run.c`
- `scripts/k3-doctor.sh`
- `scripts/download-model.sh`
- `scripts/pack-trunk.sh`
- `.github/workflows/ci.yml`

Neu angelegt wird `docs/MACOS.md`. Der Installer exportiert danach alle Änderungen als
`*.patch`.

## Messung gegen Upstream-`main`, 4. September 2026

Der Upstream hat seit dem Pin eigene macOS-Unterstützung gemerged. Bevor sich sinnvoll
über einen Rebase oder einen Beitrag reden lässt, muss gemessen sein, was vom Port
überhaupt noch etwas beiträgt. Das ist hier gemacht, Zeile für Zeile.

Gemessener Stand: `117e9d29bde14db9742f54fb66a191fd0bf03903` vom 26. August 2026,
36 Commits weiter als der Pin. Gemessen auf macOS 27, Apple Silicon, Apple clang 21.0.0.

### Verfahren

`./upstream-delta.py <upstream-checkout>` legt für die Dauer der Messung Sonden über
`replace_once`, `write_file` und `make_executable` und wendet nichts an. Der Transformer
fasst 41 Stellen an: 37 kontextgeprüfte Ersetzungen, eine neu angelegte Datei, zwei
Ausführbarkeitsbits und eine Datei, die er vollständig ersetzt. Für jede kommt eine von
vier Antworten heraus:

```
$ ./upstream-delta.py /pfad/zu/kimi-k3-in-c        # main, 117e9d29
=== Summe ===
  DELTA-BLEIBT       15
  KONTEXT-GEAENDERT  22
  NEU                1
  UPSTREAM-HAT-ES    2
  ABBRUCH            1

$ ./upstream-delta.py /pfad/zu/kimi-k3-in-c        # gegen 85ab2cd9, die Gegenprobe
=== Summe ===
  DELTA-BLEIBT       40
  NEU                1
```

Die Gegenprobe gegen den gepinnten Commit ist der Beleg dafür, dass die Sonden nicht
irgendetwas messen: dort greift jede einzelne Ersetzung, wie es sein muss.

Diese Zahlen sind eine Aussage über Textstellen, keine fachliche. `KONTEXT-GEAENDERT`
heißt nicht, dass die Änderung noch gebraucht wird, und `DELTA-BLEIBT` nicht, dass sie
etwas repariert: der Upstream kann dasselbe Problem woanders gelöst haben, und genau das
hat er in den meisten Fällen getan. Deshalb steht neben der mechanischen Spalte eine von
Hand geprüfte.

Der Transformer selbst bricht gegen `main` ohnehin ab, wie vorgesehen:

```
scripts/k3-doctor.sh differs from the reviewed upstream file
(sha256 91b5e9036eedc7eac6b97a16e8c949a471b81df1b73b1d6e13fcaac6f06fef1d);
this port replaces it wholesale and would discard those changes, so it refuses instead
```

### Was der Upstream inzwischen selbst hat

| Bereich des Ports | Upstream-`main` heute | Fundstelle |
| --- | --- | --- |
| `Makefile`, Plattformerkennung und `-mcpu=native` auf arm64 | vorhanden, `UNAME_S`/`UNAME_M` mit eigenem Darwin-Zweig | `Makefile` Zeile 47 bis 55 |
| `CMakeLists.txt`, arm64-Flags und optionales OpenMP | vorhanden, `-mcpu=native` für arm64/aarch64, `find_package(OpenMP)` und bedingtes Linken | `CMakeLists.txt` Zeile 46 bis 50, 30, 77 |
| NEON für die BF16- und MXFP4-Dot-Products | vorhanden, und zusätzlich für `k3_matmul_q8` | `src/core/k3_ops.c` Zeile 1057, 1135, 1236, 1539, 1724 |
| Darwin-Feature-Makros und `F_NOCACHE` statt `O_DIRECT` | vorhanden, zentral in einem neuen Header statt an jeder Aufrufstelle | `src/io/k3_portable_io.h` Zeile 50 bis 83 |
| `MADV_HUGEPAGE`-Rückfall in Trunk und Expert-Cache | vorhanden, `#if defined(MADV_HUGEPAGE)` an beiden Stellen | `src/io/k3_trunk.c` Zeile 383, `src/cache/k3_cache.c` Zeile 329 |
| `ru_maxrss` in Bytes statt Kilobytes auf Darwin | vorhanden | `src/cli/k3_run.c` Zeile 471 bis 475 |
| `stat -c` gegen `stat -f` im Download-Skript | vorhanden, einmal am Kopf aufgelöst | `scripts/download-model.sh` Zeile 18 bis 23 |
| macOS-Job in der CI | vorhanden, `build-and-test-macos` auf `macos-14` | `.github/workflows/ci.yml` Zeile 64 bis 101 |
| macOS im README | vorhanden, eigener Absatz in der Plattform-FAQ | `README.md` Zeile 595 |
| Ausführbarkeitsbit auf `scripts/*.sh` | vorhanden | `git ls-files -s scripts/` |

Damit ist der fachliche Kern des Ports, der Grund für seine Existenz im August, erledigt.
Das ist kein Verlust, sondern der Ausgang, den ein Out-of-Tree-Patch anstreben sollte.

### Was als eigenes Delta übrig bleibt

| Punkt | Stand upstream | Belegt durch |
| --- | --- | --- |
| **libomp-Erkennung im Makefile.** Der Upstream setzt im Darwin-Zweig `-lomp` unbedingt und prüft danach nur, ob `omp.h` da ist; findet er sie nicht, warnt er und baut mit den OpenMP-Flags weiter. | offen | `make OMP_PREFIX=/opt/homebrew/opt/libomp-not-installed bin/k3` auf `117e9d2` übersetzt alle sechs Objekte und endet mit `ld: library 'omp' not found`, `make: *** [bin/k3] Error 1`. Die vorhandene Prüfung kann das nicht sehen, weil `brew --prefix cowsay` für eine nicht installierte Formel `/opt/homebrew/opt/cowsay` ausgibt und mit `rc=0` endet. |
| **Verfügbarer Speicher im CLI.** `mem_available_bytes()` liest `/proc/meminfo` und liefert auf macOS 0. `--preset auto` steigt dann aus, und die beiden Speicherzusagen weiter unten prüfen nichts mehr, weil sie hinter `if (avail > 0.0)` stehen. | offen | `./bin/k3 <dir> --ids 1 --preset auto` auf `117e9d2`, gebaut auf diesem Mac: `--preset auto needs /proc/meminfo; pass explicit --trunk-gb/--cache-gb on this platform`. Der Port ersetzt das durch `host_statistics64` plus `host_page_size`. |
| **`scripts/k3-doctor.sh`.** Der Doctor ist upstream weiterhin ausdrücklich `LINUX ONLY` und weist alles andere gleich in Zeile 18 ab. | offen | `head -20 scripts/k3-doctor.sh`: `LINUX ONLY, like every script under scripts/`, danach `case "$(uname -s)" in Linux) ;;` mit Abbruch für alles übrige. Der Port ersetzt die Datei vollständig; ihr SHA-256 ist inzwischen `91b5e903…` statt `66b13087…`, weshalb der Transformer abbricht. |
| **`docs/MACOS.md`.** | fehlt upstream | `find docs -name 'MACOS*'` ist leer. Inhaltlich ist der Text allerdings überholt: er beschreibt die Ziele `macos` und `macos-openmp`, die es nur in diesem Port gibt. |
| **`-ffp-contract=off` in den Sanitizer-Zielen.** Upstream lässt es dort weg, während der NEON-Pfad auf aarch64 unbedingt übersetzt wird. | offen, auf dem heutigen Upstream-Baum aber ohne sichtbare Wirkung | Im erzeugten Assembler ist der Unterschied da: `cc -O1 -g -std=gnu99` auf dem heutigen `src/core/k3_ops.c` liefert 31 `fmla`/`fmadd`, mit `-ffp-contract=off` noch 5. Der Testlauf zeigt davon nichts: mit den asan-Flags des Upstream gebautes `bin/test_ops tests/fixtures/ops` meldet `22 passed, 0 failed, 0 skipped`. Das misst den Upstream-Kernel, nicht den des Ports: der Upstream hat seine NEON-Schleifen selbst geschrieben, die verbliebenen fünf Instruktionen deuten auf ausdrückliche FMA-Intrinsics. Ob die Kernel des Ports auf `85ab2cd9` ohne das Flag durchfallen, ist hier nicht nachgeprüft worden. |
| **`find -maxdepth` in `pack-trunk.sh`.** Der Port ersetzt es durch eine Glob-Schleife. | Datei upstream unverändert | Der angegebene Anlass trägt nicht: `/usr/bin/find` auf macOS 27 kennt `-maxdepth` und zählt damit korrekt nur die oberste Ebene. Ohne belegten Defekt gehört diese Änderung in keinen Beitrag. |
| **Drei macOS-Runner in der CI**, `macos-26`, `macos-15`, `macos-26-intel`. | upstream nur `macos-14` | `.github/workflows/ci.yml` Zeile 66. Eine Zusammenführung wäre ein eigener Vorgang mit eigener Begründung, keine Ergänzung. |

### Was daraus folgt

Der Pin bleibt, wo er ist. Ein Rebase des ganzen Ports auf `117e9d29` würde 22 Stellen neu
suchen und dabei überwiegend Änderungen wiederherstellen, die der Upstream inzwischen
selbst hat. Das ist Arbeit ohne Ertrag.

Von den offenen Punkten ist genau einer klein genug, allein zu stehen, und wichtig genug,
ihn einzureichen: die libomp-Erkennung. Sie ist als Patch gegen `117e9d2` vorbereitet und
liegt samt Begründung, Pull-Request-Text und Einreichungsskript in
[`beitrag/`](beitrag/README.md). Eingereicht ist nichts: es gibt keinen Fork, keinen
Branch beim Upstream und keinen Pull Request.

Der Doctor und die Speichererkennung im CLI bleiben liegen, und zwar mit Absicht. Der
Doctor ist ein vollständiger Ersatz einer Datei, die der Upstream selbst als Linux-Werkzeug
deklariert; das ist eine Entscheidung des Upstream-Eigentümers und nicht die Sorte
Änderung, die man ungefragt als Patch schickt. Die Speichererkennung ist ein zweiter,
unabhängiger Eingriff, der einen zweiten Pull Request braucht, wenn der erste angenommen
ist.
