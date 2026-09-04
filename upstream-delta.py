#!/usr/bin/env python3
"""Misst den Port gegen einen beliebigen Upstream-Checkout, ohne ihn anzuwenden.

    ./upstream-delta.py /pfad/zu/kimi-k3-in-c

Fuer jede Ersetzung in apply_macos_port.py wird festgestellt, in welchem Verhaeltnis sie
zu diesem Checkout steht:

    DELTA-BLEIBT        der erwartete Kontext steht unveraendert da, der Port wuerde greifen
    UPSTREAM-HAT-ES     das Ergebnis der Ersetzung steht schon im Baum
    KONTEXT-GEAENDERT   weder das eine noch das andere, die Stelle hat sich bewegt
    NEU                 eine Datei, die der Port anlegt und die es upstream nicht gibt

Das ist eine mechanische Aussage ueber Textstellen und keine fachliche. KONTEXT-GEAENDERT
heisst nicht, dass die Aenderung noch gebraucht wird: der Upstream kann dasselbe Problem
an anderer Stelle geloest haben. Die fachliche Spalte steht in UPSTREAM.md und ist von
Hand gepflegt, weil sie sich nicht aus Textvergleichen ergibt.

Der Transformer selbst wird nicht veraendert: replace_once, write_file und
make_executable werden fuer die Dauer der Messung durch Sonden ersetzt, die nur lesen.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER))

import apply_macos_port as port  # noqa: E402


def _sonde_ersetzung(root: Path, relative: str, old: str, new: str) -> str:
    pfad = root / relative
    if not pfad.is_file():
        return "FEHLT"
    text = pfad.read_text(encoding="utf-8", errors="replace")
    if new in text:
        return "UPSTREAM-HAT-ES"
    if old in text:
        return "DELTA-BLEIBT"
    return "KONTEXT-GEAENDERT"


def _sonde_datei(root: Path, relative: str, content: str, executable: bool = False) -> str:
    pfad = root / relative
    if not pfad.exists():
        return "NEU"
    if pfad.read_text(encoding="utf-8", errors="replace") == content:
        return "UPSTREAM-HAT-ES"
    return "KONTEXT-GEAENDERT"


def _sonde_bit(root: Path, relative: str) -> str:
    pfad = root / relative
    if not pfad.is_file():
        return "FEHLT"
    return "UPSTREAM-HAT-ES" if os.access(pfad, os.X_OK) else "DELTA-BLEIBT"


def messen(root: Path) -> int:
    port.replace_once = _sonde_ersetzung
    port.write_file = _sonde_datei
    port.make_executable = _sonde_bit

    # patch_doctor geht nicht ueber replace_once, sondern vergleicht den SHA-256 der
    # ganzen Datei und meldet in der Sprache des Transformers. Die zwei Antworten werden
    # hier in dieselbe Skala uebersetzt wie alles andere.
    uebersetzung = {"changed": "DELTA-BLEIBT", "already patched": "UPSTREAM-HAT-ES"}

    summe: dict[str, int] = {}
    abbrueche = 0
    for arbeitsschritt in (
        port.patch_makefile, port.patch_cmake, port.patch_ops, port.patch_safetensors,
        port.patch_trunk, port.patch_cache, port.patch_cli, port.patch_doctor,
        port.patch_download, port.patch_pack_trunk, port.patch_readme_and_docs,
        port.patch_ci,
    ):
        print(f"\n=== {arbeitsschritt.__name__} ===")
        try:
            ergebnisse = arbeitsschritt(root)
        except port.PortError as fehler:
            abbrueche += 1
            print(f"  ABBRUCH            {fehler}")
            continue
        for name, urteil in ergebnisse:
            urteil = uebersetzung.get(urteil, urteil)
            summe[urteil] = summe.get(urteil, 0) + 1
            print(f"  {urteil:<18} {name}")

    # patch_doctor legt seinen Ersatztext in der Staging-Ablage des Transformers ab. Auf
    # die Platte kommt davon nichts, weil _commit nie laeuft; trotzdem geleert, damit ein
    # spaeterer Import in demselben Prozess nicht darauf stoesst.
    port._STAGE.clear()

    print("\n=== Summe ===")
    for urteil in sorted(summe):
        print(f"  {urteil:<18} {summe[urteil]}")
    if abbrueche:
        print(f"  ABBRUCH            {abbrueche}")
    return 0


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0 if len(sys.argv) == 2 else 2
    root = Path(sys.argv[1]).expanduser().resolve()
    if not (root / "Makefile").is_file():
        print(f"upstream-delta: {root} sieht nicht nach kimi-k3-in-c aus", file=sys.stderr)
        return 1
    return messen(root)


if __name__ == "__main__":
    raise SystemExit(main())
