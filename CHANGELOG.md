# Änderungen

Die Versionsnummer steht in `VERSION` und nirgendwo sonst. `validate.sh` liest sie,
`scripts/make-release-archive.sh` baut den Archivnamen daraus, `scripts/release-notes.sh`
holt den passenden Abschnitt aus dieser Datei, und `.github/workflows/release.yml` lehnt
ein Tag ab, das nicht `v` plus diese Nummer ist.

Vor 1.5.0 gibt es keinen veröffentlichten Stand. `VERSION` trug zwischenzeitlich 1.0.0,
das war eine Nummer im Repo und kein Release: es gab weder Tag noch Archiv.

## 1.5.1

Warum überhaupt eine neue Nummer: der Inhalt des Pakets hat sich seit `v1.5.0` bewegt,
die Nummer nicht, und damit hätte dieselbe Nummer zwei verschiedene Stände bezeichnet.
Gemessen: das veröffentlichte Asset `kimi-k3-in-c-macos-1.5.0.zip` hat den SHA-256
`ede5ef20bc6f799937c1f24d009d01c2d3f8bf8cd2308e7b4afb10ce7b77be3b` und 23 Einträge, aus dem
Baum am Stand `69b823c` entstand unter demselben Namen ein Archiv mit 28. Fünf Dateien sind neu
(`upstream-delta.py` und die vier unter `beitrag/`), sechs weitere haben einen anderen
Inhalt: `README.md`, `CHANGELOG.md`, `UPSTREAM.md`, `SECURITY.md`, `validate.sh` und
`SHA256SUMS`. Kein Prüfer im Paket hätte das gemeldet, weil keiner das gebaute Archiv
gegen das veröffentlichte hält; aufgefallen ist es beim Nachbauen von Hand.

Ein Patch-Stand und keine neue Minor-Nummer: an dem, was der Port mit dem
Upstream-Quelltext macht, ändert sich nichts. Der Pin bleibt `85ab2cd9`,
`apply_macos_port.py` ist unverändert, `install-macos.sh` auch.

- `beitrag/einreichen.sh` wertet jedes Argument aus statt nur des ersten. Vorher war
  `--probe` keine Option, sondern eine Position: `einreichen.sh --ja --probe` verwarf das
  `--probe` still und fuhr ohne Rückfrage Fork, Push und Pull Request gegen ein fremdes
  Repositorium. Unbekannte Optionen brechen jetzt an jeder Stelle mit Rückgabewert 2 ab.
  `--probe` schlägt `--ja`.
- Der Abstand zum Upstream ist gemessen statt geschätzt. `UPSTREAM.md` führt jede Stelle
  des Transformers gegen `117e9d29` auf: was der Upstream inzwischen selbst hat, was
  eigenes Delta bleibt, und womit das jeweils belegt ist.
- `upstream-delta.py` ist das Werkzeug dazu. Es legt Sonden über `replace_once`,
  `write_file` und `make_executable`, wendet nichts an und läuft gegen jeden beliebigen
  Upstream-Checkout.
- `beitrag/` hält den einen Punkt bereit, der nach der Messung als eigenständiger Beitrag
  taugt: die libomp-Erkennung im Makefile des Upstream, als Patch gegen `117e9d2`, mit
  Pull-Request-Text und einem Skript, das ihn einreicht. Eingereicht ist nichts.
- `UPSTREAM.md` hat eine Nachmessung gegen `ac1584a`, fünf Commits nach `117e9d29`:
  `upstream-delta.py` liefert dieselbe Ausgabe, der Patch unter `beitrag/` lässt sich
  unverändert anwenden, und der neue parallele Trunk-Leser des Upstream (`18b5129`)
  läuft nur mit OpenMP. `beitrag/PR.md` nennt das im Abschnitt zum Risiko.
- Der Abschnitt zu CPU-Streaming und MLX-Quants in `README.md` hat jetzt eine Zeile zur
  Qualität und drei Fragen, an denen sich die Entscheidung entlanghangeln lässt.
- Derselbe Abschnitt behauptete, MLX halte die Gewichte im Unified Memory, und leitete
  daraus ab, der Weg sei für K3 arithmetisch verstellt. Jedes MLX-Array liegt im Unified
  Memory; dass dort alle Gewichte gleichzeitig liegen müssen, verlangen nur die üblichen
  MLX-Runner, nicht MLX. `Ibarakilol/mlx-lean-moe` (MIT, 13. September 2026) hält auf
  `mlx.core` nur die immer aktiven Gewichte resident und lädt die geroutete Auswahl von
  der Platte nach, gemessen mit 2,10 GiB Spitzenspeicher (`mx.get_peak_memory()`) bei 19
  GiB Checkpoint auf einem 8-GB-M1. Für K3 bliebe damit der Trunk resident, rund 109 GB,
  woran 512 GB nicht scheitern. Die Empfehlung steht unverändert, der Grund ist jetzt der
  richtige: eine solche Engine gibt es für die K3-Architektur nicht, und gemessen ist hier
  ohnehin kein MLX-Modell.

### Installieren

```bash
curl -LO https://github.com/GodModeAI2025/kimi-k3-in-c-macos/releases/download/v1.5.1/kimi-k3-in-c-macos-1.5.1.zip
unzip kimi-k3-in-c-macos-1.5.1.zip
cd kimi-k3-in-c-macos-1.5.1
shasum -a 256 -c SHA256SUMS
./install-macos.sh ~/src/kimi-k3-in-c-macos
```

Dieses Archiv entsteht mit dem Tag zu dieser Nummer. Ältere Releases tragen den Stand ihres
eigenen Tags, nicht diesen.

## 1.5.0

Erstes Release dieses Repositoriums. Stand des Pakets: 4. September 2026.

### Was im Archiv liegt

`kimi-k3-in-c-macos-1.5.0.zip` enthält die versionierten Dateien des Ports und ein
`SHA256SUMS`, das genau diesen Inhalt abdeckt:

- `apply_macos_port.py`, den kontextgeprüften Transformer
- `install-macos.sh`, der den gepinnten Upstream klont, portiert, baut und testet
- `validate.sh` und `tests/`, die netzfreie Prüfsuite für das Paket selbst
- `make-sha256sums.sh` und `scripts/` für Manifest und Release-Archiv
- `README.md`, `UPSTREAM.md`, `VALIDATION.md`, `CHANGELOG.md`, `SECURITY.md`, `LICENSE`,
  `NOTICE`

Nicht im Archiv: `.github/`, `.gitignore` und alles andere, was nur zum Betrieb dieses
Repositoriums gehört. `scripts/check-release-archive.sh` prüft beide Richtungen, was
drin sein muss und was nicht drin sein darf.

### Gepinnter Upstream

Der Port ist gegen den geprüften Commit
`85ab2cd901aa81b70caac7711f06864d594b8ff3` von `FareedKhan-dev/kimi-k3-in-c` gebaut.
`install-macos.sh` checkt exakt diesen Commit aus, und `apply_macos_port.py` prüft jede
zu ändernde Quelltextstelle auf den erwarteten Kontext und bricht bei Abweichungen ab.

### SHA256SUMS

`SHA256SUMS` beweist keine Authentizität. Manifest und Prüfer liegen im selben Baum, wer
eine Datei ändert, erzeugt beides neu. Die Prüfung fängt ein veraltetes Manifest ab, dafür
ist sie da; über die Herkunft der Dateien sagt sie nichts. Es gibt keine Signatur und
keine Notarisierung.

### Was seit dem ersten Stand des Repos dazugekommen ist

Die Nummer 1.5.0 steht seit `0eeae06` vom 3. August 2026 in `VERSION`. Bis dahin, von
1.0.0 aus, kamen die Befunde der Portierungsreview hinein:

- `k3_run.c` schaltet auf `_DARWIN_C_SOURCE`; unter `_POSIX_C_SOURCE` ist `ru_maxrss` auf
  Darwin kein gültiges Feld, der Port hätte auf keinem Mac übersetzt (`c01bf16`)
- Lesevorgänge auf 1 GiB pro Aufruf begrenzt, weil Darwin jede Anforderung über `INT_MAX`
  mit `EINVAL` ablehnt, während Linux kappt (`c01bf16`)
- `scripts/k3-doctor.sh` wird per SHA-256 festgenagelt statt über zwei Teilzeichenketten
  erkannt, damit lokale Änderungen nicht kommentarlos verworfen werden (`0eeae06`)

Danach kam dazu, ohne neue Nummer, weil bis zu diesem Release nichts davon veröffentlicht
war:

- Zeitmessung und Arithmetik der Leseprobe laufen unter `LC_ALL=C`; in einer Komma-Locale
  meldete der Doctor vorher eine leere Rate und teilte auf stderr durch Null
- `SHA256SUMS` wird aus `git ls-files` erzeugt, und `validate.sh` prüft beide Hälften:
  die Hashes und die Vollständigkeit der Liste
- `validate.sh` liest `VERSION` und lehnt alles ab, was keine dreiteilige Nummer ist
- `.github/workflows/ci.yml` fährt die Paketprüfungen auf Linux und macOS
- die Release-Kette selbst: Packaging-Skript, Archivprüfer, Release-Workflow

### Installieren

```bash
curl -LO https://github.com/GodModeAI2025/kimi-k3-in-c-macos/releases/download/v1.5.0/kimi-k3-in-c-macos-1.5.0.zip
unzip kimi-k3-in-c-macos-1.5.0.zip
cd kimi-k3-in-c-macos-1.5.0
shasum -a 256 -c SHA256SUMS
./install-macos.sh ~/src/kimi-k3-in-c-macos
```

Der Installer braucht Apples Command Line Tools (`xcode-select --install`) und lädt den
Upstream beim Lauf. Wer das Paket vorher selbst prüfen will, ruft `./validate.sh` auf.

### Was dieses Release nicht leistet

- keine Modellgewichte. Der Checkpoint liegt bei etwa 1,56 TB, der gepackte Trunk bei
  etwa 109 GB.
- keine vorgebaute `k3`-Binary, keine Signatur, keine Notarisierung
- keine Messung auf echter Apple-Hardware. Für diesen Port existiert kein einziger
  Durchsatzwert auf Apple Silicon.
- kein aktueller Upstream. `85ab2cd9` ist vom 1. August 2026; Upstream-`main` stand am
  4. September 2026 bei `117e9d29` und ist 36 Commits voraus. Gegen diesen Stand bricht
  der Transformer an der Doctor-Hash-Prüfung ab. Dieses Release ist der eingefrorene
  Schnappschuss auf `85ab2cd9`; ob rebased oder eingefroren weitergeführt wird, ist offen.
- keine Aussage darüber, dass die Engine auf Apple Silicon baut. In diesem Repository
  liegt kein Upstream-Quelltext, siehe `VALIDATION.md`.
