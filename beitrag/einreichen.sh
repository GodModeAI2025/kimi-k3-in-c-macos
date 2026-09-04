#!/usr/bin/env bash
# Reicht den vorbereiteten Beitrag bei FareedKhan-dev/kimi-k3-in-c ein.
#
#   beitrag/einreichen.sh --probe   holt frisches upstream/main, wendet den Patch an und
#                                   hoert danach auf. Schreibt nirgendwo hin.
#   beitrag/einreichen.sh           dasselbe, danach Fork, Push und Pull Request.
#   beitrag/einreichen.sh --ja      ohne Rueckfrage.
#
# Warum ein Skript und keine Anleitung: der Patch haengt an einem Upstream-Stand, der
# sich weiterbewegt. Der Probelauf sagt an dem Tag, an dem jemand einreichen will, ob er
# noch sauber anwendbar ist, und zwar mit demselben `git am`, das der Ernstfall benutzt.
#
# Dieses Skript ist im Rahmen der Vorbereitung nur mit --probe gelaufen. Es wurde nichts
# geforkt, nichts gepusht und kein Pull Request angelegt.
set -euo pipefail

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PATCHFILE="$HERE/0001-build-without-openmp-when-libomp-is-absent-on-macos.patch"
BODY="$HERE/PR.md"
UPSTREAM="FareedKhan-dev/kimi-k3-in-c"
BRANCH="macos/libomp-optional"

PROBE=0
NACHFRAGEN=1
case "${1:-}" in
    --probe) PROBE=1 ;;
    --ja)    NACHFRAGEN=0 ;;
    -h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    "")      ;;
    *)       echo "einreichen: unbekannte Option: $1" >&2; exit 2 ;;
esac

[ -f "$PATCHFILE" ] || { echo "einreichen: $PATCHFILE fehlt" >&2; exit 1; }
[ -s "$BODY" ]      || { echo "einreichen: $BODY fehlt oder ist leer" >&2; exit 1; }
command -v git >/dev/null 2>&1 || { echo "einreichen: git fehlt" >&2; exit 1; }
if [ "$PROBE" -eq 0 ]; then
    command -v gh >/dev/null 2>&1 || {
        echo "einreichen: die GitHub-CLI (gh) fehlt; ohne sie geht nur --probe" >&2
        exit 1
    }
    gh auth status >/dev/null 2>&1 || {
        echo "einreichen: gh ist nicht angemeldet; 'gh auth login' und noch einmal" >&2
        exit 1
    }
fi

TMP=$(mktemp -d "${TMPDIR:-/tmp}/kimi-k3-beitrag.XXXXXX")
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

# Ein frischer Klon und nicht der Arbeitsbaum nebenan: der Patch soll gegen den Stand
# geprueft werden, den der Upstream heute hat, nicht gegen eine alte lokale Kopie.
echo "einreichen: hole $UPSTREAM"
git clone --quiet "https://github.com/$UPSTREAM.git" "$TMP/src"
cd "$TMP/src"
BASE=$(git rev-parse --short HEAD)
git checkout --quiet -b "$BRANCH"

if ! git am --quiet "$PATCHFILE"; then
    git am --abort >/dev/null 2>&1 || true
    cat >&2 <<MELDUNG
einreichen: der Patch passt nicht mehr auf $UPSTREAM main ($BASE).

Der Upstream hat die geaenderten Stellen bewegt. Der Patch gehoert neu gebaut, bevor
irgendetwas eingereicht wird; UPSTREAM.md sagt, worum es inhaltlich geht.
MELDUNG
    exit 1
fi

TITEL=$(git log -1 --format=%s)
echo "einreichen: sauber angewendet auf $BASE"
git --no-pager diff --stat "HEAD~1..HEAD"

if [ "$PROBE" -eq 1 ]; then
    echo
    echo "einreichen: Probelauf beendet, es wurde nichts veroeffentlicht."
    exit 0
fi

KONTO=$(gh api user --jq .login)
echo
echo "Was jetzt passiert:"
echo "  1. Fork von $UPSTREAM unter $KONTO anlegen, falls noch keiner da ist"
echo "  2. Branch $BRANCH dorthin pushen"
echo "  3. Pull Request gegen $UPSTREAM main anlegen: $TITEL"
if [ "$NACHFRAGEN" -eq 1 ]; then
    printf 'weiter? [j/N] '
    read -r ANTWORT
    case "$ANTWORT" in
        j|J|ja|Ja) ;;
        *) echo "einreichen: abgebrochen, nichts veroeffentlicht."; exit 0 ;;
    esac
fi

gh repo fork "$UPSTREAM" --clone=false --remote=false

# gh legt den Fork asynchron an. Ein Push zwei Sekunden spaeter laeuft in ein 404, das
# nichts mit dem Patch zu tun hat, deshalb drei Anlaeufe mit Pause. Und der Push geht
# ueber HTTPS: ohne den Credential-Helper von gh fragt git nach einem Passwort, das es
# seit 2021 nicht mehr gibt. `gh auth setup-git` richtet den Helper ein, einmalig.
gh auth setup-git
ZIEL="https://github.com/$KONTO/$(basename "$UPSTREAM").git"
for VERSUCH in 1 2 3; do
    if git push --quiet "$ZIEL" "$BRANCH"; then
        break
    fi
    if [ "$VERSUCH" -eq 3 ]; then
        echo "einreichen: der Branch liess sich nicht nach $ZIEL pushen" >&2
        exit 1
    fi
    echo "einreichen: Fork noch nicht bereit, neuer Versuch in 5 Sekunden"
    sleep 5
done
gh pr create \
    --repo "$UPSTREAM" \
    --base main \
    --head "$KONTO:$BRANCH" \
    --title "$TITEL" \
    --body-file "$BODY"
