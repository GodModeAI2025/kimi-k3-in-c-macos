#!/usr/bin/env python3
"""Exercise generated Make/CMake architecture selection without the upstream checkout."""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("macos_port", HERE / "apply_macos_port.py")
assert SPEC and SPEC.loader
port = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(port)


def capture_new(fn, relative: str) -> list[str]:
    values: list[str] = []

    def capture(_root: Path, rel: str, _old: str, new: str) -> str:
        if rel == relative:
            values.append(new)
        return "captured"

    real = port.replace_once
    port.replace_once = capture
    try:
        fn(Path("/"))
    finally:
        port.replace_once = real
    return values


def run() -> None:
    make_bin = shutil.which("make")
    if not make_bin:
        raise RuntimeError("make is required")

    make_blocks = capture_new(port.patch_makefile, "Makefile")
    cmake_blocks = capture_new(port.patch_cmake, "CMakeLists.txt")
    assert make_blocks and len(cmake_blocks) == 2

    with tempfile.TemporaryDirectory(prefix="k3-build-selection-") as tmp_s:
        tmp = Path(tmp_s)
        fake = tmp / "fake-bin"
        fake.mkdir()
        (fake / "uname").write_text(
            "#!/bin/sh\n"
            "case \"$1\" in\n"
            "  -s) echo \"${FAKE_OS:-Darwin}\";;\n"
            "  -m) echo \"${FAKE_ARCH:-arm64}\";;\n"
            "  *) echo \"${FAKE_OS:-Darwin}\";;\n"
            "esac\n",
            encoding="utf-8",
        )
        (fake / "brew").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        (fake / "uname").chmod(0o755)
        (fake / "brew").chmod(0o755)

        makefile = tmp / "selection.mk"
        makefile.write_text(
            make_blocks[0]
            + '\nprint:\n\t@printf "ARCH=<%s> OMP_CFLAGS=<%s> OMP_LDFLAGS=<%s>\\n" '
            + '"$(ARCH)" "$(OMP_CFLAGS)" "$(OMP_LDFLAGS)"\n',
            encoding="utf-8",
        )
        base_env = os.environ.copy()
        base_env["PATH"] = str(fake) + os.pathsep + base_env.get("PATH", "")

        def make_values(os_name: str, arch: str) -> str:
            env = base_env.copy()
            env.update(FAKE_OS=os_name, FAKE_ARCH=arch)
            return subprocess.check_output(
                [make_bin, "-s", "-f", str(makefile), "print"], env=env, text=True
            ).strip()

        arm = make_values("Darwin", "arm64")
        intel = make_values("Darwin", "x86_64")
        linux = make_values("Linux", "x86_64")
        assert "ARCH=<>" in arm and "OMP_CFLAGS=<>" in arm
        assert "ARCH=<-march=native>" in intel and "OMP_CFLAGS=<>" in intel
        assert "OMP_CFLAGS=<-fopenmp>" in linux and "OMP_LDFLAGS=<-fopenmp>" in linux

        cmake_bin = shutil.which("cmake")
        if cmake_bin:
            src = tmp / "cmake-src"
            build = tmp / "cmake-build"
            src.mkdir()
            (src / "main.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")
            (src / "CMakeLists.txt").write_text(
                "cmake_minimum_required(VERSION 3.16)\n"
                "project(k3_selection_smoke C)\n"
                "set(CMAKE_SYSTEM_PROCESSOR arm64)\n"
                "set(APPLE TRUE)\n"
                "set(CMAKE_EXPORT_COMPILE_COMMANDS ON)\n"
                + cmake_blocks[0]
                + "\nadd_library(k3_flags INTERFACE)\n"
                "target_compile_options(k3_flags INTERFACE -Wall -Wextra -ffp-contract=off)\n"
                + cmake_blocks[1]
                + "\nadd_executable(smoke main.c)\n"
                "target_link_libraries(smoke PRIVATE k3_flags)\n",
                encoding="utf-8",
            )
            subprocess.run(
                [cmake_bin, "-S", str(src), "-B", str(build), "-DK3_ENABLE_OPENMP=OFF"],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            subprocess.run(
                [cmake_bin, "--build", str(build), "-j2"],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            commands = json.loads((build / "compile_commands.json").read_text(encoding="utf-8"))
            command = commands[0]["command"]
            assert "-mavx2" not in command and "-mfma" not in command

    print("build-selection smoke: Make and CMake architecture logic passed")


if __name__ == "__main__":
    run()
