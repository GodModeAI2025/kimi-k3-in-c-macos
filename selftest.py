#!/usr/bin/env python3
"""Self-test the context-checked macOS port applier without network access."""
from __future__ import annotations

import importlib.util
import tempfile
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("macos_port", HERE / "apply_macos_port.py")
assert SPEC and SPEC.loader
port = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(port)


def main() -> int:
    pairs: dict[str, list[tuple[str, str]]] = defaultdict(list)

    def capture(_root: Path, relative: str, old: str, new: str) -> str:
        pairs[relative].append((old, new))
        return "captured"

    def capture_file(_root: Path, relative: str, content: str, executable: bool = False) -> str:
        pairs[relative].append(("", content))
        return "captured"

    real_replace, real_write = port.replace_once, port.write_file
    port.replace_once, port.write_file = capture, capture_file
    try:
        dummy = Path("/")
        for fn in (
            port.patch_makefile,
            port.patch_cmake,
            port.patch_ops,
            port.patch_safetensors,
            port.patch_trunk,
            port.patch_cache,
            port.patch_cli,
            port.patch_download,
            port.patch_pack_trunk,
            port.patch_readme_and_docs,
            port.patch_ci,
        ):
            fn(dummy)
    finally:
        port.replace_once, port.write_file = real_replace, real_write

    with tempfile.TemporaryDirectory(prefix="k3-macos-port-test-") as tmp:
        root = Path(tmp)
        for relative, replacements in pairs.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            old_parts = [old for old, _new in replacements if old]
            if old_parts:
                path.write_text("\n/* selftest separator */\n".join(old_parts), encoding="utf-8")
        doctor = root / "scripts/k3-doctor.sh"
        doctor.parent.mkdir(parents=True, exist_ok=True)
        doctor.write_text(
            "#!/usr/bin/env bash\n# LINUX ONLY\n"
            "echo 'k3-doctor: this script and the streaming engine are Linux-only.'\n",
            encoding="utf-8",
        )

        first = port.apply(root)
        assert first
        second = port.apply(root)
        assert second
        assert all(status in {"already patched", "created"} for _name, status in second)
        trunk = (root / "src/io/k3_trunk.c").read_text(encoding="utf-8")
        assert "F_NOCACHE" in trunk and "F_RDADVISE" in trunk
        ops = (root / "src/core/k3_ops.c").read_text(encoding="utf-8")
        assert "arm_neon.h" in ops and ops.count("vcvt_f64_f32") >= 8
        cli = (root / "src/cli/k3_run.c").read_text(encoding="utf-8")
        assert "HOST_VM_INFO64" in cli and "return (double)ru.ru_maxrss;" in cli
        download = (root / "scripts/download-model.sh").read_text(encoding="utf-8")
        assert "find -printf" not in download and "stat -c" not in download
        pack = (root / "scripts/pack-trunk.sh").read_text(encoding="utf-8")
        assert 'find "$MODEL" -maxdepth' not in pack
        ci = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        # macos-26 is the newest generally-available image and the closest proxy for the
        # macOS 27 target; the Intel line ends at macOS 26, so it is pinned there.
        assert "macos-26" in ci and "macos-26-intel" in ci
        assert (root / "docs/MACOS.md").is_file()

        makefile = (root / "Makefile").read_text(encoding="utf-8")
        # A non-empty `brew --prefix libomp` does NOT mean libomp is installed, so the
        # detection has to probe for the dylib itself or the link step fails.
        assert "libomp.dylib" in makefile, "Homebrew detection must probe for the dylib"
        # aarch64 has FMA in its baseline ISA, so clearing ARCH does not disable
        # contraction the way it does on x86-64. Every target needs the flag explicitly.
        for target in ("asan", "ubsan"):
            body = makefile.split(f"\n{target}:", 1)[1].split("\n\n", 1)[0]
            assert "-ffp-contract=off" in body, f"{target} target must pin FP contraction"

    print("selftest: all context replacements and idempotency checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
