#!/usr/bin/env bash
# Prueft ein gebautes Release-Archiv, bevor es jemand veroeffentlicht.
#
# Aufruf: scripts/check-release-archive.sh <archiv.zip>
#
# Geprueft wird das Archiv, nicht das Repo: was drin ist, was nicht drin sein darf, und
# ob der Kern des Pakets haelt, also `shasum -a 256 -c SHA256SUMS` im entpackten Baum.
# Dieselbe Datei laeuft in ci.yml bei jedem Push und in release.yml vor dem Upload; ein
# kaputtes Paket faellt damit auf, bevor ein Tag gesetzt wird, nicht danach.
set -euo pipefail

ARCHIVE=${1:-}
if [ -z "$ARCHIVE" ]; then
    echo "usage: scripts/check-release-archive.sh <archiv.zip>" >&2
    exit 2
fi
[ -f "$ARCHIVE" ] || { echo "check-release-archive: $ARCHIVE gibt es nicht" >&2; exit 1; }
[ -s "$ARCHIVE" ] || { echo "check-release-archive: $ARCHIVE ist leer" >&2; exit 1; }
command -v unzip >/dev/null 2>&1 || {
    echo "check-release-archive: unzip fehlt" >&2
    exit 1
}

ARCHIVE=$(CDPATH= cd -- "$(dirname -- "$ARCHIVE")" && pwd)/$(basename -- "$ARCHIVE")

TMP=$(mktemp -d "${TMPDIR:-/tmp}/kimi-k3-release-check.XXXXXX")
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

LIST="$TMP/liste"
unzip -Z1 "$ARCHIVE" > "$LIST"
[ -s "$LIST" ] || { echo "check-release-archive: das Archiv enthaelt nichts" >&2; exit 1; }

fail=0

# Genau ein Wurzelverzeichnis, und es heisst wie das Archiv. Ohne diese Pruefung koennte
# ein Archiv beim Entpacken das Arbeitsverzeichnis des Nutzers zumuellen. Die Wurzel kommt
# aus dem Inhalt und nicht aus dem Dateinamen, damit die Meldung sagt, was wirklich falsch
# ist: mehrere Wurzeln, oder eine Wurzel, die nicht zum Namen passt.
WURZELN=$(sed -e 's|/.*||' "$LIST" | LC_ALL=C sort -u)
if [ "$(printf '%s\n' "$WURZELN" | grep -c '')" -ne 1 ]; then
    echo "check-release-archive: das Archiv hat mehr als ein Wurzelverzeichnis:" >&2
    printf '%s\n' "$WURZELN" >&2
    exit 1
fi
PREFIX=$WURZELN
if [ "$PREFIX" != "$(basename -- "$ARCHIVE" .zip)" ]; then
    echo "check-release-archive: Wurzelverzeichnis $PREFIX passt nicht zum Archivnamen $(basename -- "$ARCHIVE")" >&2
    exit 1
fi
while IFS= read -r entry; do
    case "$entry" in
        "$PREFIX"/?*|"$PREFIX"/) ;;
        *)
            echo "check-release-archive: Eintrag ausserhalb von $PREFIX/: $entry" >&2
            fail=1
            ;;
    esac
done < "$LIST"

# Was drin sein muss. Absichtlich der Kern und nicht die ganze Liste: eine neu
# hinzugefuegte Testdatei soll hier nichts brechen, eine fehlende Kerndatei schon.
for want in \
    SHA256SUMS \
    VERSION \
    LICENSE \
    NOTICE \
    README.md \
    UPSTREAM.md \
    VALIDATION.md \
    CHANGELOG.md \
    apply_macos_port.py \
    install-macos.sh \
    make-sha256sums.sh \
    selftest.py \
    validate.sh \
    tests/darwin-platform-smoke.c \
    tests/neon-smoke.c
do
    if ! grep -qxF "$PREFIX/$want" "$LIST"; then
        echo "check-release-archive: $want fehlt im Archiv" >&2
        fail=1
    fi
done

# Was nicht drin sein darf. Die Repo-Innereien gehoeren nicht in ein Quellpaket, die
# Landingpage nicht in ein Installationsarchiv, und ein Schluessel nirgendwohin.
# grep -E ueber die ganze Liste, damit auch ein Treffer in einem Unterverzeichnis auffaellt.
VERBOTEN='(^|/)(\.git|\.github|\.gitignore|\.gitattributes|\.gitmodules|\.env|index\.html|course\.html|node_modules)(/|$)|\.(pem|key|p12|pfx|keystore)$|(^|/)id_(rsa|ed25519)'
if TREFFER=$(grep -En "$VERBOTEN" "$LIST"); then
    echo "check-release-archive: verbotener Inhalt im Archiv:" >&2
    printf '%s\n' "$TREFFER" >&2
    fail=1
fi

[ "$fail" -eq 0 ] || exit 1

# Der Kern dieses Releases: nach dem Entpacken muss die Selbstpruefung durchlaufen.
unzip -q "$ARCHIVE" -d "$TMP/aus"
cd "$TMP/aus/$PREFIX"

if command -v sha256sum >/dev/null 2>&1; then
    sha256sum -c SHA256SUMS --quiet
elif command -v shasum >/dev/null 2>&1; then    # macOS bringt shasum mit, nicht sha256sum
    shasum -a 256 -c SHA256SUMS > /dev/null
else
    echo "check-release-archive: weder sha256sum noch shasum vorhanden" >&2
    exit 1
fi
echo "check-release-archive: SHA256SUMS im entpackten Archiv stimmt"

# Der dokumentierte Weg beginnt mit ./install-macos.sh. Ueberlebt das Ausfuehrbarkeitsbit
# das Packen nicht, ist der Weg kaputt, und ohne diese Zusicherung faellt es niemandem auf.
for exe in install-macos.sh validate.sh make-sha256sums.sh apply_macos_port.py \
           selftest.py scripts/make-release-archive.sh; do
    [ -x "$exe" ] || {
        echo "check-release-archive: $exe ist im Archiv nicht ausfuehrbar" >&2
        exit 1
    }
done
echo "check-release-archive: die Skripte des Pakets sind ausfuehrbar"

# Die Version im Archiv muss die Version im Namen sein. Sonst traegt ein Release die eine
# Nummer im Dateinamen und die andere in der Datei, die validate.sh am Ende ausgibt.
IN_ARCHIVE=$(tr -d ' \t\r\n' < VERSION)
if [ "$PREFIX" != "kimi-k3-in-c-macos-$IN_ARCHIVE" ]; then
    echo "check-release-archive: Archivname $PREFIX passt nicht zu VERSION $IN_ARCHIVE" >&2
    exit 1
fi

printf 'check-release-archive: %s geprueft, %s Eintraege, Version %s\n' \
    "$(basename -- "$ARCHIVE")" "$(grep -c '' "$LIST")" "$IN_ARCHIVE"
