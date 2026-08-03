#!/usr/bin/env python3
"""Syntax-check every `run:` block the port adds to the GitHub workflow.

A workflow step is shell, but it is shell nobody ever runs locally: a stray `fi`, an
unbalanced quote or a `cmd && { exit 1; }` written the wrong way round is only discovered
when a macOS runner has already spent ten minutes building. `bash -n` costs nothing and
catches the whole class.

The blocks are extracted from the transformer, which is the source of truth for what the
generated ci.yml contains, so this stays honest even without a checkout to patch.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TRANSFORMER = HERE.parent / "apply_macos_port.py"


def main() -> int:
    text = TRANSFORMER.read_text(encoding="utf-8")

    # Line scanner rather than one regex: a `run: |` body is defined by indentation, and
    # an alternation with a backreference across branches silently matches almost nothing.
    blocks: list[tuple[str, str]] = []
    lines = text.splitlines()
    name = "<unnamed>"
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("- name:"):
            name = stripped[len("- name:"):].strip()
        elif stripped in ("run: |", "run: |-"):
            open_indent = len(line) - len(line.lstrip())
            body: list[str] = []
            i += 1
            while i < len(lines):
                nxt = lines[i]
                if not nxt.strip():
                    body.append("")
                    i += 1
                    continue
                if (len(nxt) - len(nxt.lstrip())) <= open_indent:
                    break
                body.append(nxt)
                i += 1
            real = [l for l in body if l.strip()]
            if real:
                indent = min(len(l) - len(l.lstrip()) for l in real)
                blocks.append((name, "\n".join(l[indent:] if l.strip() else "" for l in body)))
            continue
        i += 1

    if not blocks:
        print("ci-shell-smoke: no run: blocks found in the transformer", file=sys.stderr)
        return 1

    bash = shutil.which("bash")
    if not bash:
        print("ci-shell-smoke: bash absent; skipped")
        return 0

    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        for i, (step, body) in enumerate(blocks):
            script = Path(tmp) / f"step{i}.sh"
            # GitHub runs `bash -e` for these, so check under the same shell options.
            script.write_text("set -e\n" + body, encoding="utf-8")
            done = subprocess.run([bash, "-n", str(script)], capture_output=True, text=True)
            if done.returncode != 0:
                failures += 1
                print(f"ci-shell-smoke: syntax error in step {step!r}:\n{done.stderr}",
                      file=sys.stderr)

    if failures:
        return 1
    print(f"ci-shell-smoke: {len(blocks)} workflow run blocks are valid bash")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
