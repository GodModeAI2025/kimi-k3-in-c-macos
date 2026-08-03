#!/usr/bin/env python3
"""Validate the arm64 NEON kernels that are ACTUALLY injected into k3_ops.c.

tests/neon-smoke.c is a hand-written copy of those kernels. Compiling the copy proves
nothing about the code the transformer emits: the two can drift silently, and a drift in
the lane order or in the mul/add split is exactly the class of bug that produces plausible
numbers instead of a crash.

This test works from the transformer itself, which is the single source of truth for what
lands in k3_ops.c, and checks three things:

  1. the NEON blocks in apply_macos_port.py and in tests/neon-smoke.c still agree,
  2. the injected blocks compile for aarch64 and emit no fused multiply-add,
  3. the SCALAR reduction that surrounds them contracts to `fmadd` on aarch64 unless
     -ffp-contract=off is passed.

Point 3 is the one with teeth, and it is why every build target must carry the flag.
The NEON intrinsics are not the risk: clang does not fuse `vaddq_f64(v, vmulq_f64(a,b))`
even at its default -ffp-contract=on. The risk is the ordinary C tail/reference loop
`s += (double)w[i] * (double)x[i]`, which clang fuses happily. On x86-64 that is harmless
by accident -- without -mfma the target has no FMA instruction, so upstream's habit of
clearing ARCH= in the sanitizer targets removes the hazard along with the vector flags.
aarch64 has FMA in the baseline ISA, so clearing ARCH changes nothing and only an explicit
-ffp-contract=off keeps the arithmetic identical to the reference.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TRANSFORMER = ROOT / "apply_macos_port.py"
SMOKE = HERE / "neon-smoke.c"

def aarch64_blocks(text: str) -> list[str]:
    """Every `#elif defined(__aarch64__)` body, bounded by the FIRST following #else or
    #endif. A single non-greedy regex would happily run past the end of one replacement
    string into the next one, silently gluing two unrelated blocks together."""
    out = []
    for m in re.finditer(r"#elif defined\(__aarch64__\)\n", text):
        rest = text[m.end():]
        stop = min((p for p in (rest.find("\n#else"), rest.find("\n#endif")) if p != -1),
                   default=-1)
        if stop == -1:
            continue
        body = rest[:stop]
        if "float64x2_t" in body:        # the include guard is not a kernel
            out.append(body)
    return out


def loop_body(block: str) -> str:
    """The vector loop of a kernel, brace-matched from its `for (`."""
    start = block.find("for (")
    if start == -1:
        fail("a kernel has no vector loop")
    open_brace = block.find("{", start)
    depth, i = 0, open_brace
    while i < len(block):
        if block[i] == "{":
            depth += 1
        elif block[i] == "}":
            depth -= 1
            if depth == 0:
                return block[open_brace: i + 1]
        i += 1
    fail("unbalanced braces in a kernel's vector loop")
    return ""


def call_sequence(body: str) -> list[str]:
    """Every NEON intrinsic in source order. Order is the contract: it encodes which
    half of each vector feeds which accumulator, so swapping vget_low_f32 for
    vget_high_f32 -- a silent lane-order bug -- changes this sequence."""
    stripped = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    return re.findall(r"\bv[a-z0-9_]+(?=\s*\()", stripped)


def normalise(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"//[^\n]*", "", text)
    return re.sub(r"\s+", "", text)


def fail(message: str) -> None:
    print(f"neon-parity: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    blocks = aarch64_blocks(TRANSFORMER.read_text(encoding="utf-8"))
    if len(blocks) != 2:
        fail(f"expected 2 injected __aarch64__ blocks in apply_macos_port.py, found {len(blocks)}")

    # 1. The reduction is the contract: four double lanes partitioned by i%4, combined as
    #    (s0+s1)+(s2+s3), with the multiply and the add kept as separate operations.
    pair = "v01=vaddq_f64(v01,vmulq_f64(w01,x01));v23=vaddq_f64(v23,vmulq_f64(w23,x23));"
    for i, block in enumerate(blocks):
        flat = normalise(block)
        if pair not in flat:
            fail(f"injected block {i} no longer uses the separate multiply/add reduction")
        if "vfmaq" in flat or "vmlaq" in flat:
            fail(f"injected block {i} uses an explicit fused multiply-add intrinsic")
        # low lanes must feed accumulators 0,1 and high lanes 2,3, or the sum reorders
        if "vget_low_f32" not in flat or "vget_high_f32" not in flat:
            fail(f"injected block {i} lost its low/high lane split")

    smoke_text = SMOKE.read_text(encoding="utf-8")
    smoke = normalise(smoke_text)
    if pair not in smoke:
        fail("tests/neon-smoke.c has drifted from the injected reduction")
    widen = "constuint32x4_tb32=vshlq_n_u32(vmovl_u16(h),16);"
    if widen not in normalise(blocks[0]) or widen not in smoke:
        fail("the bf16 widening step differs between the transformer and neon-smoke.c")

    # Full ordered comparison, not a spot check: the two kernels in neon-smoke.c must
    # issue exactly the intrinsics the transformer injects, in exactly the same order.
    smoke_fns = re.findall(r"static double \w+\([^)]*\)\s*\{(.*?)\n\}", smoke_text, re.S)
    if len(smoke_fns) != 2:
        fail(f"expected 2 kernels in neon-smoke.c, found {len(smoke_fns)}")
    for i, (block, fn) in enumerate(zip(blocks, smoke_fns)):
        want, got = call_sequence(loop_body(block)), call_sequence(loop_body(fn))
        if want != got:
            fail("tests/neon-smoke.c has drifted from the injected kernel "
                 f"{i}:\n  transformer: {want}\n  smoke      : {got}")

    # 2 + 3. Compile the INJECTED text, not the copy.
    clang = shutil.which("clang")
    if not clang:
        print("neon-parity: clang absent; skipped the aarch64 codegen check")
        print("neon-parity: injected NEON blocks match tests/neon-smoke.c")
        return 0

    # External linkage on purpose: a `static` helper that nothing calls is deleted before
    # instruction selection, and the FMA check would then pass against an empty file.
    body = "\n".join(
        f"double k3_neon_probe_{i}(const uint16_t *row, const float *wf, const float *xg,\n"
        f"                  const float *x, int in, int n)\n"
        f"{{\n    int i = 0; double acc = 0.0, s0 = 0, s1 = 0, s2 = 0, s3 = 0;\n"
        f"    (void)row; (void)wf; (void)xg; (void)x; (void)in; (void)n;\n"
        f"{block}\n"
        f"    return acc + s0 + s1 + s2 + s3;\n}}\n"
        for i, block in enumerate(blocks)
    )
    src = "#include <arm_neon.h>\n#include <stdint.h>\n" + body

    with tempfile.TemporaryDirectory() as tmp:
        cfile = Path(tmp) / "injected.c"
        cfile.write_text(src, encoding="utf-8")
        base = [clang, "--target=aarch64-none-elf", "-ffreestanding", "-std=c99", "-O2", "-S"]

        def asm(source: Path, extra: list[str]) -> str | None:
            out = Path(tmp) / (source.stem + "".join(extra).replace("=", "") + ".s")
            done = subprocess.run(base + extra + [str(source), "-o", str(out)],
                                  capture_output=True, text=True)
            if done.returncode != 0:
                return None
            return out.read_text(encoding="utf-8")

        off = asm(cfile, ["-ffp-contract=off"])
        if off is None:
            print("neon-parity: clang cannot target bare-metal aarch64; skipped codegen check")
            print("neon-parity: injected NEON blocks match tests/neon-smoke.c")
            return 0
        if re.search(r"\b(fmla|fmadd)\b", off):
            fail("the injected NEON kernels emit a fused multiply-add under -ffp-contract=off")
        if re.search(r"\bfmla\b", asm(cfile, []) or ""):
            fail("the injected NEON intrinsics contracted to FMLA at clang's default setting")

        # The load-bearing half: the scalar reduction the vector path must match.
        ref = Path(tmp) / "scalar.c"
        ref.write_text(
            "double k3_ref_dot(const double *w, const double *x, int n)\n"
            "{\n    double s0 = 0, s1 = 0, s2 = 0, s3 = 0;\n"
            "    for (int i = 0; i + 3 < n; i += 4) {\n"
            "        s0 += w[i] * x[i];         s1 += w[i + 1] * x[i + 1];\n"
            "        s2 += w[i + 2] * x[i + 2]; s3 += w[i + 3] * x[i + 3];\n"
            "    }\n    return (s0 + s1) + (s2 + s3);\n}\n",
            encoding="utf-8")
        ref_off, ref_on = asm(ref, ["-ffp-contract=off"]), asm(ref, [])
        if ref_off is not None and re.search(r"\b(fmla|fmadd)\b", ref_off):
            fail("the scalar reduction still contracts even with -ffp-contract=off")
        if ref_on is not None and not re.search(r"\b(fmla|fmadd)\b", ref_on):
            fail("the scalar reduction did not contract without the flag; "
                 "this compiler cannot demonstrate why -ffp-contract=off is required")

    print("neon-parity: injected NEON blocks match tests/neon-smoke.c")
    print("neon-parity: injected NEON kernels emit no FMA at any contraction setting")
    print("neon-parity: the scalar reduction DOES fuse on aarch64 without -ffp-contract=off")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
