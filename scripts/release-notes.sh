#!/usr/bin/env bash
# Gibt den CHANGELOG-Abschnitt zur Version aus VERSION auf stdout aus.
#
# Zwei Aufgaben in einem Mechanismus: `.github/workflows/release.yml` nimmt die Ausgabe
# als Text des Releases, und `validate.sh` ruft dasselbe Skript auf, um zu pruefen, dass
# zu der Nummer in VERSION ueberhaupt ein Eintrag existiert. Damit kann die Version nicht
# hochgezogen werden, ohne dass jemand den Eintrag schreibt.
set -euo pipefail

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(CDPATH= cd -- "$HERE/.." && pwd)

VERSION=$(tr -d ' \t\r\n' < "$ROOT/VERSION")
printf '%s\n' "$VERSION" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$' || {
    echo "release-notes: VERSION haelt keine dreiteilige Nummer: '$VERSION'" >&2
    exit 1
}

[ -f "$ROOT/CHANGELOG.md" ] || {
    echo "release-notes: CHANGELOG.md fehlt" >&2
    exit 1
}

# Der Abschnitt reicht von seiner Ueberschrift bis zur naechsten Ueberschrift derselben
# Ebene. Die Ueberschrift selbst bleibt draussen: GitHub zeigt Tag und Titel ohnehin an.
ABSCHNITT=$(awk -v v="$VERSION" '
    /^## / {
        if (drin) { exit }
        kopf = substr($0, 4)
        sub(/[ \t]+$/, "", kopf)
        if (kopf == v || index(kopf, v " ") == 1) { drin = 1 }
        next
    }
    drin { print }
' "$ROOT/CHANGELOG.md")

# Leerzeilen am Rand abschneiden, sonst beginnt der Release-Text mit einer leeren Zeile.
ABSCHNITT=$(printf '%s\n' "$ABSCHNITT" | sed -e '/./,$!d' | sed -e :a -e '/^\n*$/{$d;N;};/\n$/ba')

if [ -z "$ABSCHNITT" ]; then
    echo "release-notes: CHANGELOG.md hat keinen Abschnitt '## $VERSION'" >&2
    exit 1
fi

printf '%s\n' "$ABSCHNITT"
