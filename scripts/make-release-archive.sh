#!/usr/bin/env bash
# Baut das Release-Archiv dieses Pakets. Laeuft lokal, ohne Netz und ohne GitHub.
#
# Warum ein Skript und kein run:-Block im Release-Workflow: Shell, die nur in einem
# Workflow steht, laeuft erst beim Tag zum ersten Mal, und dann ist das Release schon
# angelegt. Dieses Skript laeuft in der CI bei jedem Push und auf jedem Rechner von Hand.
#
# Der Inhalt kommt aus `git ls-files`, abzueglich der Repo-Innereien: das Archiv ist ein
# Quellpaket des Ports, keine Kopie des Arbeitsverzeichnisses.
#
# Anmerkung zum Verzeichnis: `scripts/` in diesem Repo hat nichts mit `scripts/` im
# portierten Upstream-Checkout zu tun, in dem `k3-doctor.sh` und `download-model.sh`
# liegen. Hier steht nur die Release-Kette dieses Pakets.
set -euo pipefail

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(CDPATH= cd -- "$HERE/.." && pwd)

# Das ZIP-Format kann keinen Zeitpunkt vor 1980 darstellen, und ein echter Zeitstempel
# wuerde zwei Laeufe voneinander unterscheidbar machen. Deshalb bekommt jeder Eintrag
# denselben festen Zeitpunkt. TZ=UTC steht ueberall dabei, weil `touch -t` lokale Zeit
# liest und `zip` die Zeit ueber localtime() in das DOS-Feld schreibt.
ARCHIVE_MTIME=198001010000.00

usage() {
    cat <<'EOF'
usage: scripts/make-release-archive.sh [--print-name] <ausgabeverzeichnis>

  --print-name   nur den Dateinamen des Artefakts ausgeben und beenden
                 (liest ausschliesslich VERSION, braucht kein git)

Das Archiv wird als <ausgabeverzeichnis>/<name>.zip abgelegt; das Verzeichnis wird
angelegt, wenn es fehlt. Der volle Pfad steht in der letzten Zeile der Ausgabe.
EOF
}

PRINT_NAME_ONLY=0
OUTDIR=""
SEEN_OUTDIR=0
while [ "$#" -gt 0 ]; do
    case "$1" in
        --print-name) PRINT_NAME_ONLY=1 ;;
        -h|--help) usage; exit 0 ;;
        --) shift; break ;;
        -*) echo "unbekannte Option: $1" >&2; usage >&2; exit 2 ;;
        *) OUTDIR=$1; SEEN_OUTDIR=$((SEEN_OUTDIR + 1)) ;;
    esac
    shift
done
while [ "$#" -gt 0 ]; do
    OUTDIR=$1
    SEEN_OUTDIR=$((SEEN_OUTDIR + 1))
    shift
done
if [ "$SEEN_OUTDIR" -gt 1 ]; then
    echo "make-release-archive: nur ein Ausgabeverzeichnis" >&2
    exit 2
fi

# Einzige Versionsquelle des Pakets. validate.sh liest dieselbe Datei und prueft dieselbe
# Form; hier steht die Pruefung noch einmal, weil das Skript auch ohne validate.sh laeuft.
VERSION=$(tr -d ' \t\r\n' < "$ROOT/VERSION")
printf '%s\n' "$VERSION" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$' || {
    echo "make-release-archive: VERSION haelt keine dreiteilige Nummer: '$VERSION'" >&2
    exit 1
}
PREFIX="kimi-k3-in-c-macos-$VERSION"
NAME="$PREFIX.zip"

if [ "$PRINT_NAME_ONLY" -eq 1 ]; then
    printf '%s\n' "$NAME"
    exit 0
fi

if [ "$SEEN_OUTDIR" -eq 0 ]; then
    echo "make-release-archive: Ausgabeverzeichnis fehlt" >&2
    usage >&2
    exit 2
fi

command -v git >/dev/null 2>&1 || {
    echo "make-release-archive: git wird gebraucht, um die versionierten Dateien zu listen" >&2
    exit 1
}
command -v zip >/dev/null 2>&1 || {
    echo "make-release-archive: zip fehlt" >&2
    exit 1
}
# Dieselbe Wurzelpruefung wie in make-sha256sums.sh: ein Aufruf aus einem Unterverzeichnis
# eines fremden Repos wuerde sonst dessen Dateiliste packen. --show-prefix ist genau an der
# Wurzel leer und bleibt richtig, wenn der Pfad hierher durch einen Symlink laeuft, was
# unter /tmp auf macOS der Normalfall ist.
git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1 &&
[ -z "$(git -C "$ROOT" rev-parse --show-prefix 2>/dev/null)" ] || {
    echo "make-release-archive: $ROOT ist nicht die Wurzel eines git-Arbeitsbaums" >&2
    exit 1
}

if command -v sha256sum >/dev/null 2>&1; then
    hash_of() { sha256sum -- "$1" | cut -d' ' -f1; }
elif command -v shasum >/dev/null 2>&1; then    # macOS bringt shasum mit, nicht sha256sum
    hash_of() { shasum -a 256 -- "$1" | cut -d' ' -f1; }
else
    echo "make-release-archive: weder sha256sum noch shasum vorhanden" >&2
    exit 1
fi

# Hash einer Datei aus dem Repo-Manifest holen. Feste Satzbreite statt eines Musters:
# 64 Hexstellen, zwei Leerzeichen, ./Pfad. So bleibt ein Pfad mit Leerzeichen heil und
# ein Punkt im Namen wird nicht als Regex-Platzhalter gelesen.
repo_hash_of() {
    awk -v want="./$1" '
        substr($0, 1, 64) ~ /^[0-9a-f]+$/ && substr($0, 67) == want { print substr($0, 1, 64) }
    ' "$ROOT/SHA256SUMS"
}

# Was nicht ins Archiv gehoert. Das Paket ist ein Quellarchiv des Ports; die Werkstatt
# dieses Repos gehoert nicht hinein, und ein Schluessel oder eine Landingpage schon gar
# nicht. Muster statt Aufzaehlung, damit eine spaeter hinzugefuegte Datei nicht
# stillschweigend mitfaehrt.
excluded() {
    case "$1" in
        .git|.git/*|.github|.github/*) return 0 ;;
        .gitignore|.gitattributes|.gitmodules) return 0 ;;
        index.html|course.html|*/index.html|*/course.html) return 0 ;;
        *.pem|*.key|*.p12|*.pfx|*.keystore|id_rsa*|id_ed25519*) return 0 ;;
        .env|.env.*) return 0 ;;
    esac
    return 1
}

STAGE=$(mktemp -d "${TMPDIR:-/tmp}/kimi-k3-release.XXXXXX")
trap 'rm -rf "$STAGE"' EXIT HUP INT TERM

mkdir -p "$STAGE/$PREFIX"
cd "$ROOT"

SHIPPED=""
SKIPPED=""
# -z und read -d '': ein Pfad mit Leerzeichen oder Zeilenumbruch darf nicht in zwei
# Eintraege zerfallen. `git ls-files -s` liefert zusaetzlich den Modus, damit die
# Ausfuehrbarkeit im Archiv nicht von der umask des bauenden Rechners abhaengt.
while IFS= read -r -d '' entry; do
    mode=${entry%% *}
    f=${entry#*$'\t'}
    if excluded "$f"; then
        SKIPPED="$SKIPPED$f"$'\n'
        continue
    fi
    # SHA256SUMS wird nicht kopiert, sondern weiter unten fuer den Archivinhalt neu
    # erzeugt: das Repo-Manifest listet auch die ausgeschlossenen Dateien, und ein
    # `shasum -a 256 -c SHA256SUMS` im entpackten Archiv wuerde daran scheitern.
    if [ "$f" = SHA256SUMS ]; then
        continue
    fi
    mkdir -p "$STAGE/$PREFIX/$(dirname -- "$f")"
    cp -- "$f" "$STAGE/$PREFIX/$f"
    case "$mode" in
        100755) chmod 755 "$STAGE/$PREFIX/$f" ;;
        *)      chmod 644 "$STAGE/$PREFIX/$f" ;;
    esac
    SHIPPED="$SHIPPED$f"$'\n'
done < <(git -C "$ROOT" ls-files -s -z)

[ -n "$SHIPPED" ] || {
    echo "make-release-archive: keine Datei uebrig, die ins Archiv gehoert" >&2
    exit 1
}

# Manifest fuer genau den Inhalt dieses Archivs. Es traegt dieselbe Form wie das
# Repo-Manifest, deshalb genuegt im entpackten Archiv ein `shasum -a 256 -c SHA256SUMS`.
MANIFEST="$STAGE/$PREFIX/SHA256SUMS"
: > "$MANIFEST"
while IFS= read -r f; do
    [ -n "$f" ] || continue
    h=$(cd "$STAGE/$PREFIX" && hash_of "$f")
    # Gegenprobe gegen das Repo-Manifest: die Datei im Archiv muss bitgleich mit der
    # versionierten sein, und das Repo-Manifest darf nicht veraltet sein. Faellt das hier
    # auf, ist ./make-sha256sums.sh faellig, bevor ein Tag gesetzt wird.
    want=$(repo_hash_of "$f")
    if [ -z "$want" ]; then
        echo "make-release-archive: $f fehlt im Repo-Manifest; ./make-sha256sums.sh laufen lassen" >&2
        exit 1
    fi
    if [ "$want" != "$h" ]; then
        echo "make-release-archive: $f weicht vom Repo-Manifest ab; ./make-sha256sums.sh laufen lassen" >&2
        exit 1
    fi
    printf '%s  ./%s\n' "$h" "$f" >> "$MANIFEST"
done <<EOF
$(printf '%s' "$SHIPPED" | LC_ALL=C sort)
EOF
chmod 644 "$MANIFEST"

# Alle Zeitstempel gleich, sonst unterscheiden sich zwei Laeufe im DOS-Zeitfeld.
find "$STAGE/$PREFIX" -exec env TZ=UTC touch -t "$ARCHIVE_MTIME" -- {} +

mkdir -p "$OUTDIR"
OUTDIR=$(CDPATH= cd -- "$OUTDIR" && pwd)

# In eine frische Datei schreiben: `zip` auf ein vorhandenes Archiv aktualisiert es und
# laesst alte Eintraege stehen. Erst danach an den Zielort schieben.
TMPZIP="$STAGE/$NAME"
(
    cd "$STAGE"
    # Feste, sortierte Liste ueber -@ statt -r: die Reihenfolge von -r haengt am
    # Dateisystem. -X laesst die Unix-Extrafelder (uid, gid, zweite Zeitangabe) weg.
    find "$PREFIX" -type f -print | LC_ALL=C sort |
        TZ=UTC zip -X -q -9 -@ "$TMPZIP"
)
mv "$TMPZIP" "$OUTDIR/$NAME"
chmod 644 "$OUTDIR/$NAME"

printf 'make-release-archive: %s Dateien, Version %s\n' \
    "$(printf '%s' "$SHIPPED" | grep -c '' || true)" "$VERSION"
if [ -n "$SKIPPED" ]; then
    printf 'make-release-archive: nicht mitgepackt: %s\n' \
        "$(printf '%s' "$SKIPPED" | tr '\n' ' ')"
fi
printf '%s\n' "$OUTDIR/$NAME"
