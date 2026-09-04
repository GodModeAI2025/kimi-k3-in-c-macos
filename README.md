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
- `upstream-delta.py`, das den Port gegen einen beliebigen Upstream-Stand misst, ohne
  ihn anzuwenden

## Was du nicht bekommst

- **keine Modellgewichte.** Der Checkpoint liegt bei etwa 1,56 TB, der gepackte Trunk bei
  etwa 109 GB. Der Download ist deine Sache.
- keine Kopie des Upstream-Repositories, der Installer holt sie beim Lauf
- keine signierte oder notarisierte `k3`-Binary. Das Release ist ein Quellarchiv, gebaut
  wird auf deinem Rechner.
- keine Messung auf echter Apple-Hardware, siehe
  [Verifizierungsgrenze](#verifizierungsgrenze)

## Für wen

Für Leute mit einem Mac und viel schnellem lokalem Speicher, die Kimi K3 von der Platte
streamen wollen und Sekunden pro Token als Größenordnung akzeptieren. Wer ein interaktiv
nutzbares Modell auf dem Mac sucht, liest zuerst
[CPU-Streaming oder MLX-Quants](#cpu-streaming-oder-mlx-quants).

Vorher noch eine Einordnung, die sich seit August verschoben hat: der Upstream hat am
26. August 2026 eigene macOS- und Apple-Silicon-Unterstützung gemerged. Ein großer Teil
dessen, was dieses Paket tut, steht dort inzwischen selbst. Was noch eigenes Delta ist
und was nicht, ist nachgemessen und steht Zeile für Zeile in [UPSTREAM.md](UPSTREAM.md).
Wer heute mit einem frischen Upstream-Checkout anfängt, braucht davon vermutlich weniger,
als der Umfang dieses Pakets vermuten lässt.

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

`.github/workflows/release.yml` gehört in keine der beiden Zeilen: es läuft nur, wenn ein
Tag `v*` gepusht wird, baut das Archiv und wiederholt vor dem Upload die Archivprüfung,
die `ci.yml` bei jedem Push schon gefahren hat.

## Direkt auf dem Mac installieren

Zuerst Apples Command Line Tools installieren, sofern noch nicht vorhanden:

```bash
xcode-select --install
```

Dann das Release-Archiv holen, die Prüfsummen kontrollieren und den Installer starten:

```bash
curl -LO https://github.com/GodModeAI2025/kimi-k3-in-c-macos/releases/download/v1.5.1/kimi-k3-in-c-macos-1.5.1.zip
unzip kimi-k3-in-c-macos-1.5.1.zip
cd kimi-k3-in-c-macos-1.5.1
shasum -a 256 -c SHA256SUMS
./install-macos.sh ~/src/kimi-k3-in-c-macos
```

`v1.5.1` ist die Nummer in `VERSION` und noch kein Tag: unter Releases liegt bisher nur
`v1.5.0`, dessen Archiv nicht mehr dem Stand dieses Baums entspricht. Bis das Tag steht,
führt der Weg über den Klon weiter unten.

`shasum -a 256 -c SHA256SUMS` prüft, ob das Archiv in sich stimmig ist. Über die Herkunft
sagt es nichts: Manifest und Prüfer liegen im selben Archiv, wer eine Datei ändert, erzeugt
beides neu. Eine Signatur gibt es nicht. Was in einer Version steckt, steht in
[CHANGELOG.md](CHANGELOG.md).

Wer lieber am Git-Stand arbeitet, klont das Repo und startet den Installer aus dem Klon:

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

`./validate.sh` läuft auch im entpackten Release-Archiv; die Abdeckungsprüfung des Manifests
überspringt es dort mit einer Meldung, weil die Git-Metadaten fehlen. `./make-sha256sums.sh`
gehört dagegen zum Klon und bricht im entpackten Archiv mit `is not the root of a git work
tree` ab.

## Release bauen

Das Artefakt entsteht lokal, ohne GitHub und ohne Netz:

```bash
./scripts/make-release-archive.sh dist
./scripts/check-release-archive.sh dist/kimi-k3-in-c-macos-1.5.1.zip
```

Auch das ist ein Weg für den Klon: `make-release-archive.sh` nimmt die Dateiliste aus
`git ls-files` und bricht im entpackten Archiv mit `ist nicht die Wurzel eines
git-Arbeitsbaums` ab. `check-release-archive.sh` prüft ein fertiges ZIP und braucht kein Repo.

Zwei Läufe liefern dasselbe Archiv, Byte für Byte: alle Zeitstempel im ZIP stehen fest,
die Dateiliste ist sortiert, und die Modi kommen aus dem Git-Index statt aus der `umask`
des bauenden Rechners. Was hineingehört, kommt aus `git ls-files`, abzüglich `.github/`
und `.gitignore`. Das `SHA256SUMS` im Archiv deckt genau den Archivinhalt ab, und jede
gepackte Datei wird zusätzlich gegen das Manifest des Repos gehalten.

`.github/workflows/release.yml` ruft dieselben Skripte auf, sobald ein Tag `v*` gepusht
wird, und hängt das Ergebnis an das Release. Die Nummer steht in `VERSION`; ein Tag, das
nicht `v` plus diese Nummer ist, bricht den Lauf ab, bevor etwas hochgeladen wird. Der
Text des Releases ist der Abschnitt aus [CHANGELOG.md](CHANGELOG.md), den
`./scripts/release-notes.sh` ausgibt.

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
| Latenz | Sekunden pro Token | Token pro Sekunde |
| Qualität | die des veröffentlichten Checkpoints: der Trunk wird verlustfrei gestreamt und nicht nachquantisiert, die Experten liegen im Checkpoint ohnehin schon als MXFP4 vor | die des kleineren Modells, zusätzlich um den Quantisierungsfehler verschoben |
| Qualität, belegt durch | Upstream-README zu MXFP4 im ausgelieferten Checkpoint und Upstream-Roadmap, Abschnitt *Explicitly not planned*: nachträgliches int4 misst rund 17 % mittleren relativen Gewichtsfehler auf den K3-Attention-Tensoren, int8 rund 1 %, deshalb wird der Trunk nicht angefasst | nichts aus diesem Repo; hier ist nie ein MLX-Modell gelaufen |
| brauchbar für | Batch, Offline-Auswertung, ein Modell dieser Größe überhaupt laufen sehen | interaktive Nutzung |
| Lizenz | Apache 2.0 für den Code des Upstream und dieses Ports, die Gewichte haben ihre eigene | hängt am jeweiligen Modell |

Drei Fragen entscheiden das in der Praxis, in dieser Reihenfolge:

1. **Muss es Kimi K3 sein?** Wenn ein Modell einer kleineren Klasse die Aufgabe löst, ist
   MLX der kürzere Weg und dieses Paket das falsche Werkzeug. Der einzige Grund für den
   Weg hier ist, dass es dieses Modell sein soll.
2. **Wie viel schneller lokaler Speicher ist da?** Unter etwa 1,56 TB endet der Weg vor
   dem ersten Token, unabhängig vom RAM. Die Leserate zählt dabei genauso wie der Platz,
   weil sie pro Token anfällt und nicht einmalig; der Doctor misst sie mit einer
   sequentiellen Leseprobe und gibt das Ergebnis ausdrücklich als obere Schranke aus.
3. **Sind Sekunden pro Token in Ordnung?** Wenn nein, hilft an dieser Stelle keine
   Einstellung. Die Zeit geht für das Nachladen der Gewichte drauf, nicht für die
   Rechnung, und daran ändert ein größerer Mac wenig.

**Zahlen für macOS gibt es hier nicht.** Der Doctor nennt in seiner Preset-Leiter
veröffentlichte Linux-Werte von etwa 19 bis 32 Sekunden pro Token, je nach Speicherbudget,
und weist darauf hin, dass die Engine bei den kleinsten Budgets rund 135 GB pro Token von
der Platte liest. Auf Apple-Hardware ist dieser Port nie gemessen worden, weder Durchsatz
noch Latenz. Wer eine Zahl für den Vergleich braucht, muss sie selbst messen. Geschätzte
Werte stünden hier nur, um eine Tabelle zu füllen.

## Roadmap

Der Stand ist ein Schnappschuss. Was ansteht, in dieser Reihenfolge:

1. **Den Upstream-Beitrag einreichen.** Der Drift ist am 4. September 2026 gemessen
   worden, Stelle für Stelle, und die Entscheidung ist gefallen: der Pin bleibt auf
   `85ab2cd9`, ein Rebase auf `117e9d29` würde überwiegend Änderungen wiederherstellen,
   die der Upstream inzwischen selbst hat. Von den Punkten, die er noch nicht hat, ist
   einer klein und wichtig genug für einen eigenen Pull Request: der Upstream setzt auf
   Darwin unbedingt `-lomp`, womit `make` auf einem Mac ohne Homebrew-libomp am Linker
   stirbt. Der Patch dagegen liegt fertig in [`beitrag/`](beitrag/README.md), geprüft
   gegen `117e9d2`. Eingereicht ist er nicht, das ist der nächste Schritt und eine
   Handlung des Eigentümers: `beitrag/einreichen.sh`. Die Messung steht in
   [UPSTREAM.md](UPSTREAM.md).
2. **Doctor-Pin nachziehen.** `apply_macos_port.py` nagelt `scripts/k3-doctor.sh` per
   SHA-256 auf `66b13087…` fest, der aktuelle Upstream-Doctor hasht auf `91b5e903…`.
   Gegen Upstream-`main` bricht der Transformer also ab, wie vorgesehen. Der Pin gehört
   zu Punkt 1 und wird nicht einzeln nachgezogen. Der Doctor ist zugleich das größte
   offene Delta: upstream ist er weiterhin ausdrücklich `LINUX ONLY` und weist einen Mac
   in Zeile 18 ab. Ihn dort zu ersetzen ist eine Entscheidung des Upstream-Eigentümers
   und kein Patch, den man ungefragt schickt.
3. **Was nach 1.5.0 kommt.** `v1.5.0` ist der eingefrorene Schnappschuss auf `85ab2cd9`.
   `VERSION` steht inzwischen auf `1.5.1`, weil der Baum seit dem Tag ein anderes Archiv
   baut als das veröffentlichte; der Pin bleibt dabei `85ab2cd9`. Punkt 1 verschwindet
   dadurch nicht, er wandert in die nächste Minor-Nummer: ein Rebase ändert, was das
   Paket tut, und das ist eine neue Version und kein Nachtrag zu dieser.
4. **Auf echter Hardware messen.** Für diesen Port existiert kein einziger Durchsatzwert
   auf Apple Silicon. Solange das so bleibt, steht im Abschnitt oben keine Zahl.

Nicht geplant ist eine vorgebaute, signierte `k3`-Binary. Sie verlangt Developer-ID,
Notarisierung und die Weiterverbreitung von Upstream-Code, und ihr Nutzen gegenüber dem
Klon ist gering.

## Verifizierungsgrenze

Die Prüfsuite dieses Pakets ist auf einem Apple-Silicon-Mac unter macOS 27 gelaufen. Die
Engine selbst ist dort nicht gebaut worden, und der 1,56-TB-Checkpoint stand nicht zur
Verfügung. Deshalb wurden hier die Portierungslogik, Quellkontexte, Shell-Skripte,
Darwin-Codepfade, ARM64-Intrinsics sowie Make/CMake-Auswahl geprüft, aber kein kompletter
93-Layer-Lauf auf echter Apple-Hardware gemessen. Der angewendete Port ergänzt native
GitHub-Actions-Jobs, die genau diesen Build- und Testschritt auf ARM64- und Intel-macOS
übernehmen, sobald sie in einem Repository mit dem Upstream-Quelltext laufen. In diesem
Repository laufen sie nicht.

Was **tatsächlich ausgeführt** wurde: der Port wird auf einen echten Klon des angehefteten
Commits angewendet, und der portierte Baum baut auf Linux/x86-64 warnungsfrei und besteht
die vollständige gewichtslose Testsuite (`make test` und `ctest`, letzteres mit
`-DK3_ENABLE_OPENMP=OFF` wie in der macOS-CI). Damit ist belegt, dass der Port die
Referenzplattform nicht beschädigt, und mehr lässt sich ohne einen Build der Engine auf
einem Mac nicht behaupten. Die Darwin-spezifischen Zweige selbst wurden nie ausgeführt,
nur übersetzt und gelesen. Was dieser Prüfstand abdeckt und was nicht, steht Punkt für
Punkt in [VALIDATION.md](VALIDATION.md).
