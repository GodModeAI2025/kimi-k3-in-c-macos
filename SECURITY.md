# Sicherheitsrichtlinie

## Unterstützte Versionen

`1.5.0` ist das erste und bisher einzige Release dieses Repositoriums, davor gab es weder Tag
noch Archiv. `VERSION` steht inzwischen auf `1.5.1`, zu dem es noch kein Tag gibt: der Baum baut
ein anderes Archiv als das veröffentlichte `1.5.0`, und dieselbe Nummer soll nicht zwei Stände
bezeichnen. Die Nummer steht in `VERSION` und nirgendwo sonst. Gelesen wird die Datei von `validate.sh`,
`scripts/make-release-archive.sh`, `scripts/check-release-archive.sh`,
`scripts/release-notes.sh` und `.github/workflows/release.yml`, das ein Tag ablehnt, das nicht
`v` plus diese Nummer ist.

| Stand | unterstützt |
| --- | --- |
| der aktuelle Commit auf `main`, derzeit `1.5.1` | ja |
| das veröffentlichte Archiv `1.5.0` | ja |
| ältere Checkouts, Forks, Kopien | nein |

Gemeldet und behoben wird gegen den aktuellen Stand von `main`, Backports gibt es nicht. Der
Abschnitt „Direkt auf dem Mac installieren“ in `README.md` nennt die Nummer aus `VERSION`, also
`1.5.1`; ein Archiv dazu gibt es erst, wenn das Tag steht. Veröffentlicht ist bisher allein
`1.5.0`, und dessen Archiv ist nicht mehr der Stand von `main`. Wer den aktuellen Stand will,
klont `main`.

## Schwachstelle melden

https://github.com/GodModeAI2025/kimi-k3-in-c-macos/security/advisories/new

Private Vulnerability Reporting ist für dieses Repo aktiv. Bitte kein öffentliches Issue, keine
Discussion und kein Pull Request, der den Fix im Diff sichtbar macht, solange die Sache nicht
besprochen ist.

In die Meldung gehören: betroffene Datei mit Zeile, der Ablauf zum Auslösen, macOS- und
Toolchain-Version. Geht es um den Upstream-Code selbst, also um `FareedKhan-dev/kimi-k3-in-c`,
melde bitte dort. Eine Reaktionszeit ist nicht zugesagt; eine Erinnerung im selben
Advisory-Thread ist willkommen.

## Bedrohungsmodell

Der Installer klont fremden Code, transformiert ihn und baut ihn, zur Installationszeit statt
zur Release-Zeit. Das Release-Archiv friert den Port ein, nicht den Upstream: was gebaut wird,
holt der Installer beim Lauf, und vorab prüfen lässt sich nur der Port. Ziel eines Angriffs ist
Codeausführung auf der Maschine des Nutzers während `./install-macos.sh`.

Was der Installer anfasst: ein `git clone` in Zeile 105, sonst kein Netzaufruf; `curl` und
`wget` kommen im Skript nicht vor. `sudo` steht im ganzen Checkout nur als Wort in einem
Kommentar (`apply_macos_port.py` Zeile 1120). Nichts läuft als root, und es gibt keinen Daemon.

Der Angriffsweg führt über dieses Repo, nicht über Upstream allein. `install-macos.sh`
Zeile 106 bis 111 checkt den gepinnten Commit aus und vergleicht `rev-parse HEAD` mit dem Pin;
wer Upstream übernimmt und den Branch umschreibt, kommt an dieser Prüfung nicht vorbei. Wer
dagegen Schreibzugriff auf `main` dieses Repos erlangt oder einen Nutzer auf einen Fork lenkt,
ändert den Pin und damit alles, was der Pin absichert. `apply_macos_port.py` und
`install-macos.sh` werden per `git clone` bezogen, ohne Signatur.

Nach dem Patch rufen Zeile 131, 134, 137 und 143 bis 144 `make` und `make test` im geklonten
Baum auf. Makefile, CMake-Dateien und Testskripte stammen aus fremder Hand und laufen mit den
Rechten des Nutzers.

Außerhalb des Modells: Modellgewichte, Inferenzausgaben und Angriffe auf einen laufenden
Dienst. Der Installer lädt keine Gewichte, der dokumentierte nächste Schritt schon.
`scripts/download-model.sh` gehört Upstream, wird vom Port mitverändert und vom Installer nie
aufgerufen; Zeile 25 dieser Datei ruft `python3 -m pip install --quiet --upgrade
"huggingface_hub[cli]"` ohne Versionsangabe auf, danach lädt sie rund 1,56 TB von Hugging Face.
Diese Grenze prüft hier niemand.

## Vertrauensgrenzen

Die Grenze verläuft an `install-macos.sh` Zeile 105. Davor Code aus diesem Repo, den man vor
dem Start lesen kann. Danach fremder Code, den dieses Repo nur an definierten Stellen anfasst.

Als vertrauenswürdig behandelt:

- Der Commit `85ab2cd901aa81b70caac7711f06864d594b8ff3` von `FareedKhan-dev/kimi-k3-in-c`,
  gepinnt in vier Dateien (`install-macos.sh` Zeile 7, `apply_macos_port.py` Zeile 17,
  `UPSTREAM.md` Zeile 4 und `README.md` in „Was du bekommst“ und „Einen vorhandenen Checkout
  portieren“). `validate.sh` Zeile 21 bis 22 prüft, dass Installer und Transformer denselben
  Commit nennen.
- Die lokale Toolchain und der Nutzer, der das Skript startet. `install-macos.sh` Zeile 68 bis
  81 prüft, dass die Command Line Tools da sind und `git`, `python3`, `make` und `cc` wirklich
  starten. Woher sie im `PATH` kommen, prüft niemand.

Als nicht vertrauenswürdig behandelt:

- Jeder Upstream-Zustand jenseits des Pins. `apply_macos_port.py` prüft jede zu ändernde Stelle
  auf ihren exakten Kontext und bricht bei Abweichung ab. Alle Schreibvorgänge sammelt `_STAGE`
  (Zeile 33, Begründung im Kommentar ab Zeile 28) im Speicher und schreibt sie erst nach der
  letzten erfolgreichen Ersetzung, damit ein Abbruch keinen halb portierten Baum hinterlässt.
- Der Inhalt der einzigen vollständig ersetzten Datei. `scripts/k3-doctor.sh` ist per SHA-256
  festgenagelt (`DOCTOR_BASE_SHA256`, Zeile 21, geprüft in Zeile 1204 bis 1210); bei Abweichung
  verweigert der Transformer die Arbeit, statt lokale Änderungen kommentarlos zu verwerfen.

Was der Pin leistet: der Commit-Name ist ein Inhaltshash über den ganzen Baum, git prüft ihn
beim Transfer, ein manipuliertes Branch-Update ändert also nicht, was gebaut wird. Was er nicht
leistet: er ist keine Signatur und sagt nichts über die Herkunft, die Hashfunktion darunter ist
SHA-1, und wer den Pin selbst ändert, hebt die Prüfung auf. Signierte Commits oder Tags prüft
nirgends jemand.

## Bekannte Lücken

- **Der Installationspfad prüft dieses Paket überhaupt nicht.** `install-macos.sh` nennt weder
  `validate.sh` noch `SHA256SUMS` noch `selftest.py`. Wer nur den Installer startet, bekommt
  keine Integritätsprüfung der Dateien dieses Repos. Der dokumentierte Weg setzt
  `shasum -a 256 -c SHA256SUMS` davor, und `validate.sh` prüft dasselbe Manifest; aufrufen muss
  beides der Nutzer selbst.
- **SHA256SUMS beweist keine Authentizität.** Manifest und Prüfer liegen im selben Baum, wer
  eine Datei ändert, erzeugt beides neu. `validate.sh` schreibt das selbst hin (Zeile 55 bis 58
  und 64 bis 67) und meldet den Erfolg als „staleness check, not authenticity“. Abgedeckt sind
  30 von 31 versionierten Dateien; nicht abgedeckt ist allein `SHA256SUMS`, das seinen eigenen
  Hash nicht enthalten kann. Fehlen `sha256sum` und `shasum`, überspringt `validate.sh`
  Zeile 68 bis 69 die Prüfung kommentarlos.
- **Der Pin ist veraltet.** `UPSTREAM.md` Zeile 5 nennt als Stand des Ports den 3. August 2026;
  Upstream `main` liegt inzwischen 36 Commits weiter (`117e9d29`, 26. August 2026, über die
  GitHub-API geprüft am 4. September 2026). Gegen diesen Stand bricht der Port an der
  Doctor-Hash-Prüfung ab (`91b5e903…` gegen gepinnte `66b13087…`), und weil `install-macos.sh`
  unter `set -euo pipefail` läuft, startet der Build nicht. Das ist eine Bremse, keine Prüfung:
  wer den Pin hochzieht und die Kontextfehler nachzieht, baut ungeprüften Code. Was gegen
  diesen Stand noch eigenes Delta ist und was der Upstream inzwischen selbst hat, ist am
  4. September 2026 Stelle für Stelle gemessen worden und steht in `UPSTREAM.md`;
  nachmessen lässt es sich mit `./upstream-delta.py <upstream-checkout>`.
- **Die CI prüft das Paket, nicht die Engine.** `.github/workflows/ci.yml` fährt bei jedem
  Push auf `main` und in jedem Pull Request gegen `main` die Prüfsuite auf Linux und macOS,
  dazu die Manifest-Prüfung und den Bau des Release-Archivs. Upstream-Quelltext liegt hier
  keiner, also baut hier auch nichts die Engine; die macOS-Jobs, die der Port erzeugt, laufen
  erst im portierten Upstream-Checkout. Im Release-Archiv fehlen die Workflow-Dateien,
  `.github/` wird nicht mitgepackt.
- **Vorhersagbare Temp-Pfade.** `validate.sh` und `tests/doctor-macos-smoke.sh` bilden in
  Zeile 5 jeweils `${TMPDIR:-/tmp}/…$$` und legen den Pfad in Zeile 7 mit `mkdir -p` an, das
  auf einem schon existierenden Verzeichnis durchläuft, statt mit `mktemp`. Auf macOS ist
  `TMPDIR` pro Nutzer privat, dort geht das ins Leere; relevant wird es, wo `/tmp` geteilt ist,
  etwa auf einem Linux-Runner.
- **Kein Scanner sieht die einzige Abhängigkeit.** Es gibt keine Dependency-Datei, nur URL und
  Commit-Hash in einem Shell-Skript. Dependabot bemerkt einen zurückgezogenen Upstream nicht.
- **Die Patch-Datei wird ungeprüft überschrieben.** `install-macos.sh` Zeile 119 bis 120
  schreibt nach `${DEST%/}.patch`, ohne zu prüfen, ob dort schon etwas liegt, obwohl Zeile 97
  genau diese Prüfung für das Zielverzeichnis macht. Das kostet im schlechten Fall eine fremde
  Datei. Codeausführung folgt daraus nicht: die Datei wird von keinem Skript wieder eingelesen
  und dient laut `README.md`, Abschnitt „Direkt auf dem Mac installieren“, dem Review.

## Was dieses Projekt nicht leistet

- **Kein Build auf echter Apple-Hardware.** Die Darwin-Zweige (`F_NOCACHE`, `F_RDADVISE`,
  Mach-VM-Statistiken, `ru_maxrss`) wurden übersetzt und gelesen, nie ausgeführt. Belegt ist
  nur, dass der Port die Referenzplattform Linux/x86-64 nicht beschädigt. `README.md` nennt
  macOS 27 auf Apple Silicon als Ziel, ein passendes Runner-Image existiert nicht. Nachzulesen
  in `README.md` unter „Zielplattform und was die CI davon abdeckt“ und in `VALIDATION.md`
  unter „Nicht in dieser Umgebung ausführbar“.
- **Keine Aussage über die Sicherheit der Upstream-Engine.** Geprüft wurden die geänderten
  Stellen, nicht der übrige Inferenz-Code und nicht sein Umgang mit Modelldateien.
- **Keine Sandbox.** Build und Tests laufen mit den vollen Rechten des Nutzers in dessen
  Home-Verzeichnis. Wer das nicht will, nimmt eine VM oder einen separaten Account.
- **Kein signiertes oder notarisiertes Binary.** Es wird keins ausgeliefert, es gibt kein
  Developer-ID-Zertifikat und keine Notarisierung.
