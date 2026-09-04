# Validierungsbericht

**Datum:** 3. August 2026, fortgeschrieben am 4. September 2026
**Bezugsstand:** `85ab2cd901aa81b70caac7711f06864d594b8ff3`
**Ziel-Plattform:** macOS 27, Apple Silicon. Die Paketprüfung ist am 4. September 2026 auf
macOS 27 gelaufen (Darwin 27.0.0, arm64, Apple clang 21.0.0). Die Engine ist auf macOS 27
nie gebaut worden, und ein `macos-27`-Runner-Image gibt es nicht, siehe „Nicht in dieser
Umgebung ausführbar“ am Ende.

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
stärkste Aussage, die sich ohne einen Build der Engine auf einem Mac treffen lässt.

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
- Compile-Smoke-Test für `F_NOCACHE`, `F_RDADVISE`, Darwin-`ru_maxrss` und die Form der
  Mach-VM-Aufrufe. **Einschränkung:** die Mach-Typen und -Konstanten deklariert der Test
  selbst, damit er auch ohne macOS-SDK übersetzt. Für diesen Teil prüft er nur die
  Code-Form (Argumenttypen, das in/out-`count`-Protokoll, die Fehlerpfade) und **nichts**
  an Apples echten Headern; `fcntl` und `getrusage` kommen dagegen aus dem SDK, sobald der
  Test auf einem Mac läuft. Das echte `vm_statistics64_data_t` hat rund zwanzig
  32-Bit-`natural_t`-Zähler; deshalb weitet der Engine-Code jeden Zähler vor der Summe auf
  `uint64_t`. Der Engine-Code selbst übersetzt gegen Apples Header ausschließlich in den
  macOS-Jobs eines portierten Upstream-Checkouts.
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
ci-shell-smoke: 7 workflow run blocks are valid bash
doctor smoke: simulated Darwin/arm64 checks passed
validate: installer and transformer use the same upstream commit
validate: Darwin API syntax smoke passed
validate: arm64 NEON compile smoke passed (no fused multiply-add)
validate: SHA256SUMS is self-consistent (staleness check, not authenticity)
validate: SHA256SUMS lists every versioned file except itself
validate: CHANGELOG.md has an entry for version 1.5.1
validate: the documented download path matches kimi-k3-in-c-macos-1.5.1.zip
validate: package checks passed for version 1.5.1
```

Die Versionsnummer der letzten Zeile stammt aus `VERSION`. `validate.sh` liest die Datei
und bricht ab, wenn dort keine dreiteilige Nummer steht.

`VERSION` ist die einzige Stelle, an der die Nummer gepflegt wird. Die letzten beiden
Prüfungen halten alles andere daran fest: `CHANGELOG.md` muss einen Abschnitt zu dieser
Nummer haben, und `README.md` wie `CHANGELOG.md` müssen genau den Pfad
`releases/download/v<Nummer>/<Archivname>` nennen, den
`scripts/make-release-archive.sh --print-name` erzeugt. Beide Prüfungen laufen offline
und ohne Git-Metadaten, also auch in einem entpackten Release-Archiv.

Das Manifest wird nicht von Hand gepflegt, sondern mit `./make-sha256sums.sh` aus
`git ls-files` erzeugt. `validate.sh` prüft beide Hälften: die Hashes der gelisteten
Dateien und ob die Liste alle versionierten Dateien enthält. `SHA256SUMS` selbst steht
nicht darin, eine Prüfsummendatei enthält ihre eigene Prüfsumme nicht.

### CI dieses Repositoriums

`.github/workflows/ci.yml` fährt genau diese Prüfungen, verteilt auf zwei Runner:

- `paket-linux` auf `ubuntu-latest`: `selftest.py`, die drei Python-Smoke-Tests unter `tests/`,
  `bash -n` für die Shell-Skripte des Pakets, die Abdeckung von `SHA256SUMS` gegen
  `git ls-files` sowie zwei Konsistenzprüfungen zwischen Code und Dokumentation, nämlich
  der Upstream-Commit und das Ziel des Badges. Dazu die Release-Kette: das Archiv wird
  zweimal gebaut und byteweise verglichen, `scripts/check-release-archive.sh` prüft
  Inhalt, verbotene Einträge, die Ausführbarkeit der Skripte und `SHA256SUMS` im
  entpackten Archiv, und der Release-Text wird aus `CHANGELOG.md` gelöst.
- `vollpruefung-macos` auf `macos-latest`: `./validate.sh` vollständig, danach eine
  Prüfung, dass die plattformabhängigen Blöcke wirklich gelaufen sind. `validate.sh`
  überspringt einzelne Blöcke mit einer Meldung und bleibt grün, wenn `cc`, `clang`, ein
  SHA-256-Werkzeug oder die Git-Metadaten des Checkouts fehlen. Den `cc`-Fall fängt
  `tests/build-selection-smoke.py` zum Teil vorher ab: der Test konfiguriert ein kleines
  C-Projekt, sobald `cmake` installiert ist. Findet CMake dort keinen C-Compiler, bricht der
  Lauf mit `No CMAKE_C_COMPILER could be found` ab, bevor `validate.sh` seinen eigenen
  `cc`-Zweig erreicht. Ohne `cmake` überspringt der Test diesen Teil, und ein vorhandenes
  `clang` genügt CMake auch ohne `cc`. Auf dem macOS-Runner, dessen Userland dieses Paket
  abbildet, ist ein übersprungener Lauf kein Erfolg.

`.github/workflows/release.yml` läuft nur auf ein Tag `v*`. Es enthält keine
Packaging-Logik: es lehnt ein Tag ab, das nicht `v` plus `VERSION` ist, ruft
`scripts/make-release-archive.sh` und `scripts/check-release-archive.sh` auf und hängt das
Archiv mit `softprops/action-gh-release@v2` an das Release. Dieselben Skripte laufen in
`ci.yml` und von Hand, deshalb ist der Tag-Lauf keine Premiere.

Beide Workflow-Dateien liegen nur im Repositorium. Das Release-Archiv packt `.github/` nicht
mit, wer diesen Abschnitt im entpackten Archiv liest, findet die beiden Dateien dort also
nicht. Nachzulesen sind sie im Repositorium unter `.github/workflows/`.

Was diese CI **nicht** prüft: sie klont den Upstream nicht, baut die Engine nicht und
lädt keine Gewichte. Ein grünes Badge belegt den Zustand des Pakets, nicht dass der
portierte Baum auf Apple Silicon übersetzt. Der Reproduzierbarkeitsvergleich gilt für zwei
Läufe auf demselben Rechner mit derselben `zip`-Version; über Rechnergrenzen hinweg ist er
nicht geprüft.

## Zweite Review-Runde: was gegen Apples Quellen geprüft wurde

Vier Befunde wurden nicht durch Lesen, sondern gegen den XNU-Quelltext bzw. Homebrews
Quelltext verifiziert:

- `bsd/sys/resource.h`: `struct rusage` liefert die benannten Felder nur bei
  `__DARWIN_C_LEVEL >= __DARWIN_C_FULL`, sonst `long ru_opaque[14]`. `bsd/sys/cdefs.h`
  setzt `__DARWIN_C_LEVEL = _POSIX_C_SOURCE`, sobald dieses definiert und
  `_DARWIN_C_SOURCE` es nicht ist. `k3_run.c` deklarierte genau das — `ru.ru_maxrss` war
  auf macOS **kein gültiges Feld**. Der Port hätte auf keinem Mac übersetzt.
- `bsd/kern/sys_generic.c`: `read_internal` weist jede Anforderung über `INT_MAX` mit
  `EINVAL` ab. Linux kappt stattdessen bei `0x7ffff000` und liefert eine kurze,
  **positive** Länge, weshalb die Leseschleifen dort funktionieren. `embed_tokens` und
  `lm_head` sind je 2,35 GB, Trunk-Layer 0 ist 2,34 GB — auf macOS wäre das erste `pread`
  des Modells fehlgeschlagen.
- `osfmk/kern/host.c`: `stat->free_count = vm_page_free_count + speculative_count`. Die
  spekulativen Seiten stecken bereits in `free_count`; sie erneut zu addieren zählt eine
  ganze Seitenklasse doppelt.
- Homebrew `cmd/--prefix.rb`: druckt den Pfad und liefert 0 auch für nicht installierte
  Formeln.

Zusätzlich lokal gemessen statt vermutet:

- `MADV_HUGEPAGE` ist unter `_POSIX_C_SOURCE` **auch auf Linux nicht sichtbar** (glibc
  versteckt es hinter `__USE_MISC`). Der ursprüngliche `#if defined(MADV_HUGEPAGE)`-Test
  hat die 2-MB-Arena des Expert-Caches damit auf der Referenzplattform abgeschaltet —
  nachgewiesen über die Präprozessor-Ausgabe (`const int huge = 0;`). Die Guards prüfen
  jetzt `__APPLE__`, also die Plattform statt der Makro-Sichtbarkeit.
- `\b` in `grep -E` ist eine GNU-Erweiterung. BSD-`grep` (also `/usr/bin/grep` auf macOS)
  behandelt die Sequenz als literales `b`, wodurch die **negative** FMA-Assertion in
  `validate.sh` stillschweigend durchgelaufen wäre. Ersetzt durch POSIX-Klassen.
- `command -v cc` kann auf macOS nicht fehlschlagen: `/usr/bin/cc`, `make` und `git` sind
  `xcrun`-Shims, die auch ohne Command Line Tools existieren. Doctor und Installer rufen
  die Werkzeuge jetzt auf, statt nur ihre Namen aufzulösen.
- Die Leseprobe des Doctors war locale- und tempoabhängig. `/usr/bin/time -p` schreibt in
  einer Komma-Locale `real 0,00`; `awk` vergleicht diese Zeichenkette mit 0 als String,
  findet sie größer und ließ die Probe die Plausibilitätsprüfung passieren. Der Doctor
  meldete dann `ok  sequential read probe:  (upper bound)` ohne Zahl, dazu eine Division
  durch Null auf stderr. Unter `LC_ALL=C` scheiterte dieselbe Messung an der Prüfung und
  landete in der Warnung `duration could not be parsed`. Gemessen vor der Reparatur:
  6 Fehlschläge in 20 Läufen von `tests/doctor-macos-smoke.sh` unter `de_DE.UTF-8`,
  3 in 10 Läufen unter `LC_ALL=C`. Zeitmessung und Arithmetik laufen jetzt unter
  `LC_ALL=C`, und eine Dauer unterhalb der Auflösung von 0,01 s bekommt eine eigene
  Meldung statt einer leeren Zahl.

### Tests, die vorher nichts prüfen konnten

- Der Doctor-Smoke-Test hatte `hw.memsize` und die `vm_stat`-Summe im selben Preset-Eimer,
  sodass ein vollständig kaputter `vm_stat`-Parse dieselbe Ausgabe erzeugt hätte.
  Die Fixtures liegen jetzt in verschiedenen Eimern (256 GiB installiert, 38 GiB frei) —
  verifiziert: ein absichtlich zerstörter Parse lässt den Test fehlschlagen.
- `assert "find -printf" not in download` konnte nie fehlschlagen, weil die Upstream-Zeile
  `find "$DEST" -maxdepth 1 -name '*.safetensors' -printf …` lautet und die Zeichenkette
  so nie zusammenhängend vorkommt. Geprüft wird jetzt auf die Flags einzeln —
  verifiziert durch Wiedereinbau von `find -maxdepth`.
- `darwin-platform-smoke.c` verwendete `_DARWIN_C_SOURCE`, während `k3_run.c` nur
  `_POSIX_C_SOURCE` deklarierte. Der Test übersetzte damit ein anderes `struct rusage` als
  die echte Datei — genau deshalb blieb der harte Build-Fehler unentdeckt.
- Der zweite Probelauf mit dem `dd`-Ersatz belegte nur, dass die Ratenrechnung überhaupt
  ausgeführt wird. Gegen den unreparierten Stand liefert er dieselbe Zeile
  `sequential read probe: 1 MB/s (upper bound)`, in `de_DE.UTF-8` wie unter `LC_ALL=C`:
  `awk` entscheidet locale-blind, ob eine Zuweisung wie eine Zahl aussieht, lässt `1,00`
  als String durch den Vergleich mit 0 und wandelt sie danach über ein locale-abhängiges
  `strtod` doch wieder in 1.0. Nur eine Dauer von exakt `0,00` teilt durch Null, und keine
  Zusicherung kann die Uhr dazu bringen, diese zu liefern. Der Smoke-Test prüft die
  Locale-Pins deshalb am erzeugten `port.DOCTOR`-Text: `LC_ALL=C /usr/bin/time -p` muss
  vorkommen, und kein `awk` im Probe-Block darf ohne `LC_ALL=C` stehen. Verifiziert: gegen
  `apply_macos_port.py` vor der Reparatur schlägt der Test in beiden Locales fehl, ein
  Rückbau allein der drei `awk`-Pins ebenso.

## Dritte und vierte Runde: Bedienbarkeit und Prüfschärfe

- `./scripts/download-model.sh` und `./scripts/pack-trunk.sh` standen so in der Anleitung,
  waren aber als `100644` eingecheckt — also *Permission denied*. Alle drei Skripte werden
  jetzt ausführbar gemacht; der erzeugte Patch enthält die drei Modusänderungen.
- Der `strict-warnings`-Job läuft auf Ubuntu und sah damit ausschließlich den
  `#else`-Zweig jedes `#if defined(__APPLE__)`. Der Darwin-Code war der einzige Teil des
  Baums ohne `-Werror`. Ein macOS-Job übersetzt ihn jetzt mit `-Werror`.
- Kein macOS-Job baute je mit OpenMP. Zwei neue Schritte fahren den Standard-`make`
  einmal ohne und einmal mit installiertem `libomp` und prüfen per `otool -L`, dass
  `bin/k3` im ersten Fall **kein** `libomp` linkt. Das ist der Regressionstest für den
  kritischsten Befund dieser Prüfung. Ausgeführt wird er bisher nicht: die beiden Schritte
  stehen in dem Workflow, den der Port in einen Upstream-Checkout schreibt, und einen
  solchen Checkout gibt es in der CI dieses Repositoriums nicht.
- `scripts/k3-doctor.sh` ist die einzige Datei, die vollständig ersetzt wird. Sie wurde
  über zwei Teilzeichenketten „erkannt“, womit lokale Änderungen kommentarlos verworfen
  worden wären — genau die Zusicherung, die das Paket bewirbt, an der einzigen Stelle
  gebrochen, an der sie zählt. Jetzt per SHA-256 auf den geprüften Inhalt festgenagelt,
  mit Negativtest.
- Der erzeugte Doctor legte eine mehrere GB große Probedatei im Modellverzeichnis an,
  ohne `trap`. Ein Strg-C ließ sie liegen. Jetzt mit Aufräum-Trap.
- `tests/ci-shell-smoke.py` prüft alle sieben `run:`-Blöcke des Workflows mit `bash -n`
  unter `set -e`. Workflow-Shell ist die Shell, die niemand lokal ausführt.
- Zwei Assertions prüften Schreibweise statt Verhalten: `"k3_read_span" in src` ist jetzt
  durch einen Scan aller `pread`-Aufrufe hinterlegt, und die Feature-Test-Ebene von
  `darwin-platform-smoke.c` muss mit der jeder portierten Darwin-Datei übereinstimmen —
  genau diese Lücke ließ den `ru_maxrss`-Baufehler eine grüne Suite passieren.

## Nicht in dieser Umgebung ausführbar

Diese Grenze ist hart und wird hier nicht beschönigt:

- kein nativer Build der Engine auf einem realen Apple-Silicon-Mac; auf einem solchen
  Rechner gelaufen ist nur die Prüfsuite dieses Pakets
- kein nativer Build der Engine auf einem realen Intel-Mac
- kein vollständiger Testlauf mit dem etwa 1,56 TB großen Checkpoint
- keine Performance-Messung eines 93-Layer-Laufs auf Apple-Hardware
- die Darwin-Codepfade (`F_NOCACHE`, `F_RDADVISE`, Mach-VM-Statistiken, `ru_maxrss`)
  wurden auf Syntax und API-Verwendung geprüft, aber **nie ausgeführt**
- in diesem Repository liegt kein Upstream-Quelltext, also kompiliert hier nirgends der
  *echte* `k3_ops.c` für Darwin/arm64; geprüft werden die injizierten NEON-Blöcke einzeln
  gegen ein Bare-Metal-aarch64-Target

Dafür ergänzt der Port GitHub-Actions-Jobs für `macos-26`, `macos-15` und
`macos-26-intel`. Diese Jobs bauen den Port mit Make und CMake und führen die Tests ohne
Modellgewichte aus, sobald sie in einem Repository mit dem Upstream-Quelltext laufen, auf
den der Port angewendet wurde. Ein Push oder Pull Request in diesem Repository löst sie
nicht aus, siehe „CI dieses Repositoriums“.
`macos-26` ist das neueste allgemein verfügbare Image und damit der beste verfügbare
Stellvertreter für macOS 27; sobald ein `macos-27`-Image GA ist, gehört es in die Matrix.
Für Intel gibt es keinen macOS-27-Job und wird es keinen geben, weil macOS 26 die letzte
Intel-fähige Version ist.
