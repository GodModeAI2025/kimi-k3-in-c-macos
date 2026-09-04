# Änderungen

Die Versionsnummer steht in `VERSION` und nirgendwo sonst. `validate.sh` liest sie,
`scripts/make-release-archive.sh` baut den Archivnamen daraus, `scripts/release-notes.sh`
holt den passenden Abschnitt aus dieser Datei, und `.github/workflows/release.yml` lehnt
ein Tag ab, das nicht `v` plus diese Nummer ist.

Vor 1.5.0 gibt es keinen veröffentlichten Stand. `VERSION` trug zwischenzeitlich 1.0.0,
das war eine Nummer im Repo und kein Release: es gab weder Tag noch Archiv.

## 1.5.0

Erstes Release dieses Repositoriums. Stand des Pakets: 4. September 2026.

### Was im Archiv liegt

`kimi-k3-in-c-macos-1.5.0.zip` enthält die versionierten Dateien des Ports und ein
`SHA256SUMS`, das genau diesen Inhalt abdeckt:

- `apply_macos_port.py`, den kontextgeprüften Transformer
- `install-macos.sh`, der den gepinnten Upstream klont, portiert, baut und testet
- `validate.sh` und `tests/`, die netzfreie Prüfsuite für das Paket selbst
- `make-sha256sums.sh` und `scripts/` für Manifest und Release-Archiv
- `README.md`, `UPSTREAM.md`, `VALIDATION.md`, `CHANGELOG.md`, `LICENSE`, `NOTICE`

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

### Enthalten, seit `VERSION` auf 1.5.0 steht

- `k3_run.c` schaltet auf `_DARWIN_C_SOURCE`; unter `_POSIX_C_SOURCE` ist `ru_maxrss` auf
  Darwin kein gültiges Feld, der Port hätte auf keinem Mac übersetzt
- Lesevorgänge auf 1 GiB pro Aufruf begrenzt, weil Darwin jede Anforderung über `INT_MAX`
  mit `EINVAL` ablehnt, während Linux kappt
- `scripts/k3-doctor.sh` wird per SHA-256 festgenagelt statt über zwei Teilzeichenketten
  erkannt, damit lokale Änderungen nicht kommentarlos verworfen werden
- Zeitmessung und Arithmetik der Leseprobe laufen unter `LC_ALL=C`; in einer Komma-Locale
  meldete der Doctor vorher eine leere Rate und teilte auf stderr durch Null
- `SHA256SUMS` wird aus `git ls-files` erzeugt, und `validate.sh` prüft beide Hälften:
  die Hashes und die Vollständigkeit der Liste
- `validate.sh` liest `VERSION` und lehnt alles ab, was keine dreiteilige Nummer ist
- `.github/workflows/ci.yml` fährt die Paketprüfungen auf Linux und macOS

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
