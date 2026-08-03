#!/usr/bin/env python3
"""Apply the macOS portability layer to FareedKhan-dev/kimi-k3-in-c.

The transformations are intentionally context-checked: every replacement must match the
upstream source exactly once. This avoids silently applying a stale port to a changed code
base. The script is idempotent for a tree that has already been patched.
"""
from __future__ import annotations

import argparse
import stat
import sys
from pathlib import Path

BASE_COMMIT = "85ab2cd901aa81b70caac7711f06864d594b8ff3"


class PortError(RuntimeError):
    pass


# Every edit is staged in memory and flushed only after ALL of them have matched. A
# transformer that writes as it goes turns one changed upstream line into a half-patched
# checkout: the earlier files are rewritten, the failing one is left partly converted, and
# re-running cannot recover because its own context no longer matches. The documented
# "port an existing checkout" workflow runs straight into that, so writes are deferred.
_STAGE: "dict[Path, tuple[str, bool]]" = {}


def _stage_read(path: Path) -> str:
    if path in _STAGE:
        return _STAGE[path][0]
    return path.read_text(encoding="utf-8")


def _stage_write(path: Path, content: str, executable: bool = False) -> None:
    _STAGE[path] = (content, executable or (path in _STAGE and _STAGE[path][1]))


def _stage_exists(path: Path) -> bool:
    return path in _STAGE or path.exists()


def _commit(root: Path) -> None:
    for path, (content, executable) in _STAGE.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        if executable:
            path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    _STAGE.clear()


def replace_once(root: Path, relative: str, old: str, new: str) -> str:
    path = root / relative
    if not path.is_file():
        raise PortError(f"missing expected file: {relative}")
    text = _stage_read(path)
    # Check the complete replacement first: some replacements deliberately retain the
    # original Linux branch inside a new platform guard.
    if new in text:
        return "already patched"
    if old in text:
        count = text.count(old)
        if count != 1:
            raise PortError(f"expected one match in {relative}, found {count}")
        _stage_write(path, text.replace(old, new, 1))
        return "changed"
    raise PortError(
        f"upstream context changed in {relative}; refusing an unsafe fuzzy replacement"
    )


def write_file(root: Path, relative: str, content: str, executable: bool = False) -> str:
    path = root / relative
    if _stage_exists(path):
        if _stage_read(path) == content:
            result = "already patched"
        else:
            raise PortError(f"{relative} already exists with different content")
    else:
        result = "created"
    _stage_write(path, content, executable)
    return result


def patch_makefile(root: Path) -> list[tuple[str, str]]:
    changed: list[tuple[str, str]] = []
    old = r'''CC       ?= cc
PYTHON   ?= python3
BUILD    ?= build
BIN      ?= bin
PREFIX   ?= /usr/local

# -march=native is a real win on the expert matmuls but produces a binary that will not
# run on an older CPU. `make portable` drops it.
ARCH     ?= -march=native

# -Wpointer-arith is not cosmetic: weight pointers are `const void *`, and arithmetic on
# a void pointer is a silent GNU extension that strides by ONE BYTE. Without this flag
# that mistake compiles clean under -Wall -Wextra and returns the wrong tensor.
#
# -ffp-contract=off keeps floating-point results reproducible across compilers by
# disabling automatic FMA contraction. The test-suite compares against a reference to a
# fixed tolerance; letting the compiler fuse changes results by more than that.
WARN     := -Wall -Wextra -Wpointer-arith -Wshadow -Wvla -Wno-unused-parameter
CFLAGS   ?= -O3 -std=gnu99 $(WARN) $(ARCH) -fopenmp -ffp-contract=off
LDFLAGS  ?= -lm -fopenmp
'''
    new = r'''CC       ?= cc
PYTHON   ?= python3
BUILD    ?= build
BIN      ?= bin
PREFIX   ?= /usr/local

UNAME_S  := $(shell uname -s)
UNAME_M  := $(shell uname -m)

# Linux keeps the original OpenMP + native-architecture defaults. Stock Apple Clang does
# not ship OpenMP, so macOS builds without it unless Homebrew libomp is already present.
# Apple Silicon uses hand-written NEON paths for the bf16 and MXFP4 dot products; the
# remaining kernels retain their portable C99 implementation.
ifeq ($(UNAME_S),Darwin)
  ifeq ($(UNAME_M),x86_64)
    ARCH ?= -march=native
  else
    ARCH ?=
  endif
  # `brew --prefix libomp` PRINTS A PATH AND EXITS 0 even when libomp is not installed,
  # so a non-empty answer proves nothing. Probe for the dylib itself: without this the
  # default build on the very common "Homebrew present, libomp absent" Mac would append
  # -lomp for a library that is not there and fail at link after compiling everything.
  BREW_OMP  := $(shell command -v brew >/dev/null 2>&1 && brew --prefix libomp 2>/dev/null || true)
  BREW_LIBOMP := $(if $(BREW_OMP),$(wildcard $(BREW_OMP)/lib/libomp.dylib),)
  ifneq ($(BREW_LIBOMP),)
    OMP_CFLAGS ?= -Xpreprocessor -fopenmp -I$(BREW_OMP)/include
    OMP_LDFLAGS ?= -L$(BREW_OMP)/lib -Wl,-rpath,$(BREW_OMP)/lib -lomp
  else
    OMP_CFLAGS ?=
    OMP_LDFLAGS ?=
  endif
else
  # -march=native is a real win on the expert matmuls but produces a binary that will not
  # run on an older CPU. `make portable` drops it.
  ARCH ?= -march=native
  OMP_CFLAGS ?= -fopenmp
  OMP_LDFLAGS ?= -fopenmp
endif

# -Wpointer-arith is not cosmetic: weight pointers are `const void *`, and arithmetic on
# a void pointer is a silent GNU extension that strides by ONE BYTE. Without this flag
# that mistake compiles clean under -Wall -Wextra and returns the wrong tensor.
#
# -ffp-contract=off keeps floating-point results reproducible across compilers by
# disabling automatic FMA contraction. The test-suite compares against a reference to a
# fixed tolerance; letting the compiler fuse changes results by more than that.
WARN     := -Wall -Wextra -Wpointer-arith -Wshadow -Wvla -Wno-unused-parameter
CFLAGS   ?= -O3 -std=gnu99 $(WARN) $(ARCH) $(OMP_CFLAGS) -ffp-contract=off
LDFLAGS  ?= -lm $(OMP_LDFLAGS)
'''
    changed.append(("Makefile platform flags", replace_once(root, "Makefile", old, new)))

    old = r'''.PHONY: all test test-all bench portable debug asan ubsan format clean install help \
        tok cfg ops cache st oracle weights-test
'''
    new = r'''.PHONY: all test test-all bench portable macos macos-openmp debug asan ubsan \
        format clean install help tok cfg ops cache st oracle weights-test
'''
    changed.append(("Makefile phony targets", replace_once(root, "Makefile", old, new)))

    old = r'''## portable: no -march=native, runs on any x86-64
portable:
	$(MAKE) ARCH="-mavx2 -mfma" all

## debug: -O0 -g, assertions on
debug:
	$(MAKE) CFLAGS="-O0 -g3 -std=gnu99 $(WARN) -fopenmp -ffp-contract=off" all
'''
    new = r'''## portable: documented x86-64 baseline; native architecture baseline elsewhere
portable:
	@if [ "$(UNAME_M)" = "x86_64" ]; then \
	    $(MAKE) ARCH="-mavx2 -mfma" all; \
	else \
	    $(MAKE) ARCH= all; \
	fi

## macos: build with stock Apple Clang and no external OpenMP dependency
macos:
	@test "$(UNAME_S)" = "Darwin" || { echo "macos target requires Darwin"; exit 1; }
	$(MAKE) OMP_CFLAGS= OMP_LDFLAGS= all

## macos-openmp: threaded macOS build using Homebrew libomp
macos-openmp:
	@test "$(UNAME_S)" = "Darwin" || { echo "macos-openmp target requires Darwin"; exit 1; }
	@command -v brew >/dev/null 2>&1 || { echo "Homebrew is required; install it first"; exit 1; }
	@OMP="$$(brew --prefix libomp 2>/dev/null || true)"; \
	 test -n "$$OMP" && test -r "$$OMP/lib/libomp.dylib" \
	   || { echo "libomp is missing; run: brew install libomp"; exit 1; }; \
	 $(MAKE) \
	   OMP_CFLAGS="-Xpreprocessor -fopenmp -I$$OMP/include" \
	   OMP_LDFLAGS="-L$$OMP/lib -Wl,-rpath,$$OMP/lib -lomp" all

## debug: -O0 -g, assertions on
debug:
	$(MAKE) CFLAGS="-O0 -g3 -std=gnu99 $(WARN) $(ARCH) $(OMP_CFLAGS) -ffp-contract=off" \
	        LDFLAGS="-lm $(OMP_LDFLAGS)" all
'''
    changed.append(("Makefile macOS targets", replace_once(root, "Makefile", old, new)))

    # The sanitizer targets drop -ffp-contract=off and neutralise ARCH. On x86-64 that was
    # harmless: clearing ARCH also clears -mavx2, so __AVX2__ goes undefined and the scalar
    # path compiles. arm64 has no such escape -- __aarch64__ is defined by the target, not
    # by a flag, so the NEON path is ALWAYS compiled. Without -ffp-contract=off clang fuses
    # `vaddq_f64(v, vmulq_f64(a,b))` into FMLA (verified: 2 fmla in the generated assembly),
    # which breaks the bit-exact reduction contract k3_ops.c documents and makes the op
    # tests fail against their reference on a perfectly correct tree.
    old = r'''asan:
	$(MAKE) CFLAGS="-O1 -g -std=gnu99 $(WARN) -fsanitize=address,undefined -fno-omit-frame-pointer" \
	        LDFLAGS="-lm -fsanitize=address,undefined" ARCH= all

ubsan:
	$(MAKE) CFLAGS="-O1 -g -std=gnu99 $(WARN) -fsanitize=undefined" \
	        LDFLAGS="-lm -fsanitize=undefined" ARCH= all
'''
    new = r'''asan:
	$(MAKE) CFLAGS="-O1 -g -std=gnu99 $(WARN) -fsanitize=address,undefined -fno-omit-frame-pointer -ffp-contract=off" \
	        LDFLAGS="-lm -fsanitize=address,undefined" ARCH= all

ubsan:
	$(MAKE) CFLAGS="-O1 -g -std=gnu99 $(WARN) -fsanitize=undefined -ffp-contract=off" \
	        LDFLAGS="-lm -fsanitize=undefined" ARCH= all
'''
    changed.append(("sanitizer FP contraction", replace_once(root, "Makefile", old, new)))
    return changed


def patch_cmake(root: Path) -> list[tuple[str, str]]:
    changed: list[tuple[str, str]] = []
    old = r'''option(K3_NATIVE_ARCH "Optimise for the building CPU (-march=native)" OFF)
option(K3_SANITIZE    "Build with ASan + UBSan"                        OFF)

find_package(OpenMP)
'''
    new = r'''option(K3_NATIVE_ARCH   "Optimise for the building CPU"       OFF)
option(K3_SANITIZE      "Build with ASan + UBSan"                     OFF)
option(K3_ENABLE_OPENMP "Use OpenMP when the toolchain provides it"   ON)

if(K3_ENABLE_OPENMP)
  find_package(OpenMP)
endif()
'''
    changed.append(("CMake options", replace_once(root, "CMakeLists.txt", old, new)))

    old = r'''if(K3_NATIVE_ARCH)
  target_compile_options(k3_flags INTERFACE -march=native)
else()
  # Documented baseline. The engine assumes AVX2 + FMA are available.
  target_compile_options(k3_flags INTERFACE -mavx2 -mfma)
endif()
'''
    new = r'''# AVX2 is an optional x86 fast path guarded by __AVX2__. Do not pass x86 flags to an
# arm64 compiler: arm64 uses native NEON dot products plus portable C99 fallbacks.
set(K3_IS_X86_64 FALSE)
if(CMAKE_SYSTEM_PROCESSOR MATCHES "^(x86_64|amd64|AMD64)$")
  set(K3_IS_X86_64 TRUE)
endif()
# A universal macOS build contains both arm64 and x86_64, so global AVX flags are invalid.
if(APPLE AND CMAKE_OSX_ARCHITECTURES MATCHES ";")
  set(K3_IS_X86_64 FALSE)
endif()

if(K3_NATIVE_ARCH)
  if(K3_IS_X86_64 OR NOT APPLE)
    target_compile_options(k3_flags INTERFACE -march=native)
  endif()
elseif(K3_IS_X86_64)
  # Documented x86-64 distribution baseline.
  target_compile_options(k3_flags INTERFACE -mavx2 -mfma)
endif()

if(APPLE)
  message(STATUS "macOS port enabled: F_NOCACHE streaming and native ru_maxrss units")
  if(CMAKE_SYSTEM_PROCESSOR MATCHES "^(arm64|aarch64)$")
    message(STATUS "Apple Silicon uses native NEON dot products and portable fallbacks")
  endif()
endif()
'''
    changed.append(("CMake architecture selection", replace_once(root, "CMakeLists.txt", old, new)))
    return changed



def patch_ops(root: Path) -> list[tuple[str, str]]:
    # Add arm64 NEON implementations while preserving the scalar reduction order.
    changed: list[tuple[str, str]] = []

    old = r''' *   - the AVX2 path (guarded by __AVX2__), which reproduces the scalar code's
 *     four-accumulator partition and reduction tree exactly rather than choosing a
 *     more natural one.
'''
    new = r''' *   - the SIMD paths (AVX2 on x86-64 and NEON on arm64), which reproduce the
 *     scalar code's four-accumulator partition and reduction tree exactly rather than
 *     choosing a more natural one.
'''
    changed.append(("numeric-core SIMD contract", replace_once(root, "src/core/k3_ops.c", old, new)))

    old = r'''#if defined(__AVX2__)
#include <immintrin.h>
#endif
'''
    new = r'''#if defined(__AVX2__)
#include <immintrin.h>
#elif defined(__aarch64__)
#include <arm_neon.h>
#endif
'''
    changed.append(("arm64 NEON include", replace_once(root, "src/core/k3_ops.c", old, new)))

    old = r'''#if defined(__AVX2__)
        {
            __m256d v = _mm256_setzero_pd();
            for (; i + 3 < in; i += 4) {
                /* bf16 -> f32 is a 16-bit left shift, so widen the four u16 to u32,
                 * shift, and reinterpret. No table, no rounding. */
                const __m128i h  = _mm_loadl_epi64((const __m128i *)(row + i));
                const __m128i b32 = _mm_slli_epi32(_mm_cvtepu16_epi32(h), 16);
                const __m256d wd = _mm256_cvtps_pd(_mm_castsi128_ps(b32));
                const __m256d xd = _mm256_cvtps_pd(_mm_loadu_ps(x + i));
                v = _mm256_add_pd(v, _mm256_mul_pd(wd, xd));   /* NOT fmadd: see above */
            }
            double a[4];
            _mm256_storeu_pd(a, v);
            acc = (a[0] + a[1]) + (a[2] + a[3]);
        }
#else
'''
    new = r'''#if defined(__AVX2__)
        {
            __m256d v = _mm256_setzero_pd();
            for (; i + 3 < in; i += 4) {
                /* bf16 -> f32 is a 16-bit left shift, so widen the four u16 to u32,
                 * shift, and reinterpret. No table, no rounding. */
                const __m128i h  = _mm_loadl_epi64((const __m128i *)(row + i));
                const __m128i b32 = _mm_slli_epi32(_mm_cvtepu16_epi32(h), 16);
                const __m256d wd = _mm256_cvtps_pd(_mm_castsi128_ps(b32));
                const __m256d xd = _mm256_cvtps_pd(_mm_loadu_ps(x + i));
                v = _mm256_add_pd(v, _mm256_mul_pd(wd, xd));   /* NOT fmadd: see above */
            }
            double a[4];
            _mm256_storeu_pd(a, v);
            acc = (a[0] + a[1]) + (a[2] + a[3]);
        }
#elif defined(__aarch64__)
        {
            /* Keep four logical double accumulators, split into two NEON vectors. The
             * lanes are i%4 = 0,1 and 2,3, so the scalar reduction tree is unchanged. */
            float64x2_t v01 = vdupq_n_f64(0.0);
            float64x2_t v23 = vdupq_n_f64(0.0);
            for (; i + 3 < in; i += 4) {
                const uint16x4_t h = vld1_u16(row + i);
                const uint32x4_t b32 = vshlq_n_u32(vmovl_u16(h), 16);
                const float32x4_t wf = vreinterpretq_f32_u32(b32);
                const float32x4_t xf = vld1q_f32(x + i);
                const float64x2_t w01 = vcvt_f64_f32(vget_low_f32(wf));
                const float64x2_t w23 = vcvt_f64_f32(vget_high_f32(wf));
                const float64x2_t x01 = vcvt_f64_f32(vget_low_f32(xf));
                const float64x2_t x23 = vcvt_f64_f32(vget_high_f32(xf));
                v01 = vaddq_f64(v01, vmulq_f64(w01, x01));   /* deliberately not FMA */
                v23 = vaddq_f64(v23, vmulq_f64(w23, x23));
            }
            const double a0 = vgetq_lane_f64(v01, 0);
            const double a1 = vgetq_lane_f64(v01, 1);
            const double a2 = vgetq_lane_f64(v23, 0);
            const double a3 = vgetq_lane_f64(v23, 1);
            acc = (a0 + a1) + (a2 + a3);
        }
#else
'''
    changed.append(("bf16 arm64 NEON matmul", replace_once(root, "src/core/k3_ops.c", old, new)))

    old = r'''             * the scalar and the AVX2 path so the two agree bit for bit on every
             * machine. The split is written out rather than left to the compiler
'''
    new = r'''             * the scalar, AVX2 and arm64 NEON paths so they agree bit for bit on
             * every supported architecture. The split is written out rather than left to the compiler
'''
    changed.append(("MXFP4 SIMD contract", replace_once(root, "src/core/k3_ops.c", old, new)))

    old = r'''#if defined(__AVX2__)
            {
                __m256d v = _mm256_setzero_pd();
                for (; i + 3 < n; i += 4) {
                    const __m256d wd = _mm256_cvtps_pd(_mm_loadu_ps(wf + i));
                    const __m256d xd = _mm256_cvtps_pd(_mm_loadu_ps(xg + i));
                    v = _mm256_add_pd(v, _mm256_mul_pd(wd, xd));  /* not fmadd */
                }
                double a[4];
                _mm256_storeu_pd(a, v);
                s0 = a[0]; s1 = a[1]; s2 = a[2]; s3 = a[3];
            }
#else
'''
    new = r'''#if defined(__AVX2__)
            {
                __m256d v = _mm256_setzero_pd();
                for (; i + 3 < n; i += 4) {
                    const __m256d wd = _mm256_cvtps_pd(_mm_loadu_ps(wf + i));
                    const __m256d xd = _mm256_cvtps_pd(_mm_loadu_ps(xg + i));
                    v = _mm256_add_pd(v, _mm256_mul_pd(wd, xd));  /* not fmadd */
                }
                double a[4];
                _mm256_storeu_pd(a, v);
                s0 = a[0]; s1 = a[1]; s2 = a[2]; s3 = a[3];
            }
#elif defined(__aarch64__)
            {
                float64x2_t v01 = vdupq_n_f64(0.0);
                float64x2_t v23 = vdupq_n_f64(0.0);
                for (; i + 3 < n; i += 4) {
                    const float32x4_t wf4 = vld1q_f32(wf + i);
                    const float32x4_t xf4 = vld1q_f32(xg + i);
                    const float64x2_t w01 = vcvt_f64_f32(vget_low_f32(wf4));
                    const float64x2_t w23 = vcvt_f64_f32(vget_high_f32(wf4));
                    const float64x2_t x01 = vcvt_f64_f32(vget_low_f32(xf4));
                    const float64x2_t x23 = vcvt_f64_f32(vget_high_f32(xf4));
                    v01 = vaddq_f64(v01, vmulq_f64(w01, x01));   /* not FMA */
                    v23 = vaddq_f64(v23, vmulq_f64(w23, x23));
                }
                s0 = vgetq_lane_f64(v01, 0); s1 = vgetq_lane_f64(v01, 1);
                s2 = vgetq_lane_f64(v23, 0); s3 = vgetq_lane_f64(v23, 1);
            }
#else
'''
    changed.append(("MXFP4 arm64 NEON dot product", replace_once(root, "src/core/k3_ops.c", old, new)))
    return changed


def patch_safetensors(root: Path) -> list[tuple[str, str]]:
    changed: list[tuple[str, str]] = []
    old = r'''#define _GNU_SOURCE            /* O_DIRECT */
#define _POSIX_C_SOURCE 200809L
#define _FILE_OFFSET_BITS 64
'''
    new = r'''#if defined(__APPLE__)
#define _DARWIN_C_SOURCE       /* F_NOCACHE */
#else
#define _GNU_SOURCE            /* O_DIRECT */
#define _POSIX_C_SOURCE 200809L
#define _FILE_OFFSET_BITS 64
#endif
'''
    changed.append(("safetensors feature macros", replace_once(root, "src/io/k3_st.c", old, new)))

    old = r'''#include "k3_st.h"

/* ------------------------------------------------------------------ helpers */
'''
    new = r'''#include "k3_st.h"

/* Open a second descriptor that avoids polluting the filesystem cache. Linux exposes
 * O_DIRECT; macOS exposes the equivalent policy as F_NOCACHE on an already-open fd.
 * Failure is optional: callers retain the normal buffered descriptor as a fallback. */
static int k3_open_cache_bypassed(const char *path)
{
#if defined(__APPLE__)
    int fd = open(path, O_RDONLY);
    if (fd < 0) return -1;
    if (fcntl(fd, F_NOCACHE, 1) != 0) {
        close(fd);
        return -1;
    }
    return fd;
#else
    return open(path, O_RDONLY | O_DIRECT);
#endif
}

/* Largest byte count handed to a single pread.
 *
 * Linux clamps a read to 0x7ffff000 and RETURNS that count, so a loop over a 2.35 GB
 * tensor simply goes round twice. Darwin does not: XNU's read_internal rejects any
 * request above INT_MAX outright with EINVAL, and the loops here treat a negative
 * return as a fatal short read. embed_tokens and lm_head are 2.35 GB each as bf16, so
 * on macOS the very first pread of the model would fail. Clamping costs one extra
 * iteration on the two largest tensors and nothing anywhere else. */
#define K3_READ_CHUNK ((size_t)1 << 30)

static size_t k3_read_span(int64_t remaining)
{
    return (size_t)(remaining > (int64_t)K3_READ_CHUNK ? (int64_t)K3_READ_CHUNK : remaining);
}

/* ------------------------------------------------------------------ helpers */
'''
    changed.append(("safetensors cache-bypass helper", replace_once(root, "src/io/k3_st.c", old, new)))

    old = r'''        ssize_t r = pread(s->fd[t->shard], (char *)buf + got,
                          (size_t)(t->nbytes - got), (off_t)(t->off + got));
'''
    new = r'''        ssize_t r = pread(s->fd[t->shard], (char *)buf + got,
                          k3_read_span(t->nbytes - got), (off_t)(t->off + got));
'''
    changed.append(("safetensors oversized read", replace_once(root, "src/io/k3_st.c", old, new)))

    old = r'''    /* A second descriptor on the same file, for streamed expert reads that must not go
     * through the page cache. Optional: if the filesystem refuses O_DIRECT the reader
     * falls back to fd[]. */
    if (s->dfd) s->dfd[shard] = open(path, O_RDONLY | O_DIRECT);
'''
    new = r'''    /* A second descriptor on the same file for streamed expert reads that should not
     * displace useful pages. Optional on both platforms; fd[] remains the fallback. */
    if (s->dfd) s->dfd[shard] = k3_open_cache_bypassed(path);
'''
    changed.append(("safetensors direct descriptor", replace_once(root, "src/io/k3_st.c", old, new)))
    return changed


def patch_trunk(root: Path) -> list[tuple[str, str]]:
    changed: list[tuple[str, str]] = []
    old = r'''#define _GNU_SOURCE            /* O_DIRECT */
#define _POSIX_C_SOURCE 200809L
#define _FILE_OFFSET_BITS 64
'''
    new = r'''#if defined(__APPLE__)
#define _DARWIN_C_SOURCE       /* F_NOCACHE, F_RDADVISE */
#else
#define _GNU_SOURCE            /* O_DIRECT, posix_fadvise */
#define _POSIX_C_SOURCE 200809L
#define _FILE_OFFSET_BITS 64
#endif
'''
    changed.append(("trunk feature macros", replace_once(root, "src/io/k3_trunk.c", old, new)))

    old = r'''#include <fcntl.h>
#include <stdio.h>
'''
    new = r'''#include <fcntl.h>
#include <limits.h>
#include <stdio.h>
'''
    changed.append(("trunk limits include", replace_once(root, "src/io/k3_trunk.c", old, new)))

    old = r'''static int k3_alloc_direct(void **out, size_t bytes);   /* defined below */

/* WHERE THE TIME IN A BIND ACTUALLY GOES.
'''
    new = r'''static int k3_alloc_direct(void **out, size_t bytes);   /* defined below */

/* See k3_st.c: Darwin's read path rejects any request above INT_MAX with EINVAL rather
 * than returning a short count. Trunk layer 0 is 2.34 GB, so it needs the same clamp. */
#define K3_READ_CHUNK ((size_t)1 << 30)

static size_t k3_read_span(int64_t remaining)
{
    return (size_t)(remaining > (int64_t)K3_READ_CHUNK ? (int64_t)K3_READ_CHUNK : remaining);
}

/* Open the packed trunk with the strongest cache-bypass policy the platform offers.
 * tr->direct means "cache bypass active", not specifically the Linux O_DIRECT flag. */
static int k3_open_stream_file(const char *path, int *direct)
{
#if defined(__APPLE__)
    int fd = open(path, O_RDONLY);
    if (fd < 0) return -1;
    *direct = (fcntl(fd, F_NOCACHE, 1) == 0);
    return fd;                         /* buffered fallback if F_NOCACHE was refused */
#else
    int fd = open(path, O_RDONLY | O_DIRECT);
    if (fd >= 0) { *direct = 1; return fd; }
    *direct = 0;
    return open(path, O_RDONLY);
#endif
}

static const char *k3_stream_mode_name(int direct)
{
    if (!direct) return "buffered I/O";
#if defined(__APPLE__)
    return "F_NOCACHE (filesystem cache disabled)";
#else
    return "O_DIRECT (page cache bypassed)";
#endif
}

/* WHERE THE TIME IN A BIND ACTUALLY GOES.
'''
    changed.append(("trunk cache-bypass helper", replace_once(root, "src/io/k3_trunk.c", old, new)))

    old = r'''    tr->direct = 1;
    tr->fd = open(p, O_RDONLY | O_DIRECT);
    if (tr->fd < 0) {
        tr->direct = 0;
        tr->fd = open(p, O_RDONLY);
    }
    if (tr->fd < 0) { fprintf(stderr, "k3_trunk: cannot open %s\n", p); return -1; }
    {
        jval *a = json_get(root, "align");
        const int64_t want = (a && a->t == J_NUM) ? (int64_t)a->num : 0;
        if (tr->direct && want != K3_TRUNK_ALIGN) {
            /* A trunk packed before the alignment change cannot be read with O_DIRECT:
             * its run offsets are arbitrary. Say so rather than fail every read. */
            fprintf(stderr, "k3_trunk: trunk.json reports align %lld, expected %d; "
                            "falling back to buffered reads (repack to enable O_DIRECT)\n",
                    (long long)want, K3_TRUNK_ALIGN);
            close(tr->fd);
            tr->direct = 0;
            tr->fd = open(p, O_RDONLY);
            if (tr->fd < 0) return -1;
        }
    }
'''
    new = r'''    tr->fd = k3_open_stream_file(p, &tr->direct);
    if (tr->fd < 0) { fprintf(stderr, "k3_trunk: cannot open %s\n", p); return -1; }
#if !defined(__APPLE__)
    {
        jval *a = json_get(root, "align");
        const int64_t want = (a && a->t == J_NUM) ? (int64_t)a->num : 0;
        if (tr->direct && want != K3_TRUNK_ALIGN) {
            /* Linux O_DIRECT requires aligned runs. F_NOCACHE on macOS does not, so this
             * compatibility fallback is intentionally Linux-only. */
            fprintf(stderr, "k3_trunk: trunk.json reports align %lld, expected %d; "
                            "falling back to buffered reads (repack to enable O_DIRECT)\n",
                    (long long)want, K3_TRUNK_ALIGN);
            close(tr->fd);
            tr->direct = 0;
            tr->fd = open(p, O_RDONLY);
            if (tr->fd < 0) return -1;
        }
    }
#endif
'''
    changed.append(("trunk open path", replace_once(root, "src/io/k3_trunk.c", old, new)))

    old = r'''    printf("              reads use %s\n",
           tr->direct ? "O_DIRECT (page cache bypassed)" : "buffered I/O");
'''
    new = r'''    printf("              reads use %s\n", k3_stream_mode_name(tr->direct));
'''
    changed.append(("trunk I/O report", replace_once(root, "src/io/k3_trunk.c", old, new)))

    old = r'''    const int huge = !getenv("K3_NOHUGE");
    const size_t align = huge ? (2u << 20) : 4096u;
'''
    # Key this on the PLATFORM, not on whether MADV_HUGEPAGE happens to be visible.
    # Visibility depends on the feature-test macros of the translation unit, so a
    # `#if defined(MADV_HUGEPAGE)` test silently disables the 2 MB arena on Linux too in
    # any file that does not set _GNU_SOURCE -- which is a behaviour change on the
    # reference platform, not a macOS fallback. The madvise call site keeps its own
    # visibility guard, which is upstream's and is the correct test for that line.
    new = r'''#if defined(__APPLE__)
    const int huge = 0;                /* Darwin has no Linux transparent hugepage hint */
#else
    const int huge = !getenv("K3_NOHUGE");
#endif
    const size_t align = huge ? (2u << 20) : 4096u;
'''
    changed.append(("trunk hugepage fallback", replace_once(root, "src/io/k3_trunk.c", old, new)))

    old = r'''    if (tr->direct) return;
    posix_fadvise(tr->fd, (off_t)tr->lay[L].file_off, (off_t)tr->lay[L].nbytes,
                  POSIX_FADV_WILLNEED);
'''
    new = r'''    if (tr->direct) return;
#if defined(__APPLE__)
    {
        struct radvisory ra;
        ra.ra_offset = (off_t)tr->lay[L].file_off;
        ra.ra_count = (int)(tr->lay[L].nbytes > INT_MAX ? INT_MAX : tr->lay[L].nbytes);
        (void)fcntl(tr->fd, F_RDADVISE, &ra);
    }
#else
    (void)posix_fadvise(tr->fd, (off_t)tr->lay[L].file_off,
                       (off_t)tr->lay[L].nbytes, POSIX_FADV_WILLNEED);
#endif
'''
    changed.append(("trunk prefetch advisory", replace_once(root, "src/io/k3_trunk.c", old, new)))

    old = r'''        ssize_t r = pread(tr->fd, dst + got, (size_t)(lay->nbytes - got),
                          (off_t)(lay->file_off + got));
'''
    new = r'''        ssize_t r = pread(tr->fd, dst + got, k3_read_span(lay->nbytes - got),
                          (off_t)(lay->file_off + got));
'''
    changed.append(("trunk oversized read", replace_once(root, "src/io/k3_trunk.c", old, new)))
    return changed


def patch_cache(root: Path) -> list[tuple[str, str]]:
    old = r'''        const int huge = !getenv("K3_NOHUGE");
        const size_t al = huge ? (2u << 20) : 4096u;
'''
    # As in k3_trunk.c: test the platform, not the macro's visibility. This file compiles
    # under _POSIX_C_SOURCE alone, and glibc hides MADV_HUGEPAGE behind __USE_MISC, so a
    # `#if defined(MADV_HUGEPAGE)` test is FALSE on Linux here and would quietly drop the
    # expert arena from 2 MB to 4 KB alignment on the reference platform.
    new = r'''#if defined(__APPLE__)
        const int huge = 0;            /* Darwin has no transparent-hugepage hint */
#else
        const int huge = !getenv("K3_NOHUGE");
#endif
        const size_t al = huge ? (2u << 20) : 4096u;
'''
    return [("expert-cache hugepage fallback", replace_once(root, "src/cache/k3_cache.c", old, new))]


def patch_cli(root: Path) -> list[tuple[str, str]]:
    changed: list[tuple[str, str]] = []
    # Darwin's <sys/sys/cdefs.h> sets __DARWIN_C_LEVEL to _POSIX_C_SOURCE whenever that is
    # defined and _DARWIN_C_SOURCE is not. <sys/resource.h> then declares
    #     #if __DARWIN_C_LEVEL < __DARWIN_C_FULL
    #             long ru_opaque[14];
    # instead of the named members, so `ru.ru_maxrss` does not compile at all -- the whole
    # point of the Darwin branch below. _DARWIN_C_SOURCE is a superset of POSIX 2008 here,
    # so nothing else in this file loses a declaration.
    old = r'''#define _POSIX_C_SOURCE 200809L

#include <math.h>
'''
    new = r'''#if defined(__APPLE__)
#define _DARWIN_C_SOURCE       /* struct rusage exposes ru_maxrss only at the full level */
#else
#define _POSIX_C_SOURCE 200809L
#endif

#include <math.h>
'''
    changed.append(("CLI Darwin feature level", replace_once(root, "src/cli/k3_run.c", old, new)))

    old = r'''#include <time.h>
#include <sys/resource.h>

#include "k3.h"
'''
    new = r'''#include <time.h>
#include <sys/resource.h>
#if defined(__APPLE__)
#include <mach/mach.h>
#include <mach/mach_host.h>
#endif

#include "k3.h"
'''
    changed.append(("CLI Mach includes", replace_once(root, "src/cli/k3_run.c", old, new)))

    old = r'''/* PEAK resident set, in bytes. ru_maxrss is kilobytes on Linux.
 *
 * This is the authoritative memory figure. The banner printed before allocation is a
 * PLAN and understates: it omits the safetensors index (~78 MB at full scale), reports
 * requested budgets rather than actual reservations, and cannot observe fragmentation.
 * Quote this value, not the plan. */
static double peak_rss_bytes(void)
{
    struct rusage ru;
    if (getrusage(RUSAGE_SELF, &ru) != 0) return 0.0;
    return (double)ru.ru_maxrss * 1024.0;
}

/* MemAvailable, which is what the kernel thinks can actually be handed out, not
 * MemFree. Returns 0 if it cannot be read. */
static double mem_available_bytes(void)
{
    FILE *f = fopen("/proc/meminfo", "r");
    if (!f) return 0.0;
    char line[256];
    double kb = 0.0;
    while (fgets(line, sizeof line, f))
        if (!strncmp(line, "MemAvailable:", 13)) { kb = atof(line + 13); break; }
    fclose(f);
    return kb * 1024.0;
}
'''
    new = r'''/* PEAK resident set, in bytes. Linux reports ru_maxrss in KiB; Darwin reports bytes.
 *
 * This is the authoritative memory figure. The banner printed before allocation is a
 * PLAN and understates: it omits the safetensors index (~78 MB at full scale), reports
 * requested budgets rather than actual reservations, and cannot observe fragmentation.
 * Quote this value, not the plan. */
static double peak_rss_bytes(void)
{
    struct rusage ru;
    if (getrusage(RUSAGE_SELF, &ru) != 0) return 0.0;
#if defined(__APPLE__)
    return (double)ru.ru_maxrss;
#else
    return (double)ru.ru_maxrss * 1024.0;
#endif
}

/* Reclaimable memory rather than just completely free pages. Linux exposes this as
 * MemAvailable. Darwin exposes page classes, so use free plus inactive.
 *
 * speculative_count is deliberately NOT added: XNU's vm_stats() fills the struct as
 *     stat->free_count = vm_page_free_count + speculative_count;
 *     stat->speculative_count = speculative_count;
 * so the speculative pages are ALREADY inside free_count, and adding them again counts
 * that class twice. (The vm_stat command-line tool subtracts them back out before it
 * prints "Pages free", which is why the two look independent there and are not here.)
 *
 * This stays deliberately conservative. Active file-backed pages are also reclaimable
 * on Darwin but are not counted, because over-reporting here would wave a machine
 * through into a 1.56 TB download that it cannot actually serve. Returns 0 if it cannot
 * be measured. */
static double mem_available_bytes(void)
{
#if defined(__APPLE__)
    mach_port_t host = mach_host_self();
    vm_size_t page_size = 0;
    vm_statistics64_data_t vm;
    mach_msg_type_number_t count = HOST_VM_INFO64_COUNT;
    if (host_page_size(host, &page_size) != KERN_SUCCESS ||
        host_statistics64(host, HOST_VM_INFO64, (host_info64_t)&vm, &count) != KERN_SUCCESS) {
        mach_port_deallocate(mach_task_self(), host);
        return 0.0;
    }
    /* natural_t is 32-bit; widen before summing. */
    const uint64_t pages = (uint64_t)vm.free_count + (uint64_t)vm.inactive_count;
    mach_port_deallocate(mach_task_self(), host);
    return (double)pages * (double)page_size;
#else
    FILE *f = fopen("/proc/meminfo", "r");
    if (!f) return 0.0;
    char line[256];
    double kb = 0.0;
    while (fgets(line, sizeof line, f))
        if (!strncmp(line, "MemAvailable:", 13)) { kb = atof(line + 13); break; }
    fclose(f);
    return kb * 1024.0;
#endif
}
'''
    changed.append(("CLI macOS memory accounting", replace_once(root, "src/cli/k3_run.c", old, new)))
    return changed


DOCTOR = r'''#!/usr/bin/env bash
# k3-doctor, check whether this Linux or macOS machine can run Kimi K3, and how fast.
#
# Answers three questions before a 1.56 TB checkpoint download:
#   1. Is the toolchain present and does the engine build?
#   2. How much reclaimable memory is available, and which preset does that imply?
#   3. How much local storage is available, and what sequential rate does it expose?
#
# K3_DOCTOR_PROBE_MB can reduce the default 2048 MB storage probe.

set -u

OS=$(uname -s)
ARCH=$(uname -m)
case "$OS" in
    Linux|Darwin) ;;
    *) echo "k3-doctor: supported operating systems are Linux and macOS; detected $OS"
       exit 1 ;;
esac

RED=$'\033[31m'; GRN=$'\033[32m'; YLW=$'\033[33m'; DIM=$'\033[2m'; RST=$'\033[0m'
[ -t 1 ] || { RED=""; GRN=""; YLW=""; DIM=""; RST=""; }

ok()   { printf '  %sok%s    %s\n'   "$GRN" "$RST" "$*"; }
warn() { printf '  %swarn%s  %s\n'   "$YLW" "$RST" "$*"; }
bad()  { printf '  %sFAIL%s  %s\n'   "$RED" "$RST" "$*"; FAILED=1; }
hdr()  { printf '\n%s\n' "$*"; }
info() { printf '  %sinfo  %s%s\n' "$DIM" "$*" "$RST"; }

FAILED=0
HAVE_BREW_OMP=0
MODEL_DIR="${1:-}"

printf '%s\n' "Kimi K3, environment check ($OS/$ARCH)"

# ------------------------------------------------------------------ toolchain --
hdr "toolchain"
# Presence on PATH is not evidence on macOS. /usr/bin/cc, /usr/bin/gcc, /usr/bin/make and
# /usr/bin/git are xcrun shims that exist on a stock system whether or not the Command
# Line Tools are installed; without them the shim prints "no developer tools were found"
# and exits non-zero. Testing with `command -v` therefore always succeeds and the
# xcode-select advice below could never print. Run the tool instead.
CCBIN=""
for candidate in cc gcc clang; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" --version >/dev/null 2>&1; then
        CCBIN=$(command -v "$candidate")
        break
    fi
done
if [ -n "$CCBIN" ]; then
    ok "C compiler: $($CCBIN --version 2>&1 | head -1)"
elif [ "$OS" = Darwin ]; then
    bad "no working C compiler (run: xcode-select --install)"
else
    bad "no C compiler found (install build-essential or equivalent)"
fi
if make --version >/dev/null 2>&1; then
    ok "make: $(make --version 2>&1 | head -1)"
elif [ "$OS" = Darwin ]; then
    bad "make is not usable (run: xcode-select --install)"
else
    bad "make not found"
fi
if command -v python3 >/dev/null 2>&1; then
    ok "python3: $(python3 --version 2>&1)"
else
    warn "python3 not found; download, trunk packing and analysis tools need it"
fi
if [ "$OS" = Darwin ]; then
    # `brew --prefix libomp` succeeds for an UNINSTALLED formula too, so test the dylib.
    OMP_PREFIX=$(command -v brew >/dev/null 2>&1 && brew --prefix libomp 2>/dev/null || true)
    if [ -n "$OMP_PREFIX" ] && [ -r "$OMP_PREFIX/lib/libomp.dylib" ]; then
        HAVE_BREW_OMP=1
        ok "OpenMP: Homebrew libomp detected (default make will use it)"
    else
        warn "OpenMP not detected; stock Apple Clang still builds, but runs single-threaded"
        info "for the threaded build: brew install libomp && make macos-openmp"
    fi
fi

# ------------------------------------------------------------------------ cpu --
hdr "cpu"
if [ "$OS" = Darwin ]; then
    NCPU=$(sysctl -n hw.logicalcpu 2>/dev/null || echo 1)
else
    NCPU=$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 1)
fi
ok "logical cores: $NCPU"

if [ "$OS" = Darwin ] && [ "$ARCH" = arm64 ]; then
    ok "Apple Silicon: native arm64 build"
    ok "NEON: native bf16 and MXFP4 dot-product paths enabled"
    info "remaining kernels use portable C99; published x86-64 timings are not predictive"
elif [ "$ARCH" = x86_64 ]; then
    if [ "$OS" = Darwin ]; then
        FEATURES="$(sysctl -n machdep.cpu.features 2>/dev/null || true) $(sysctl -n machdep.cpu.leaf7_features 2>/dev/null || true)"
        echo "$FEATURES" | grep -qi 'AVX2' && ok "AVX2: present" || warn "AVX2 not detected; scalar kernels will be used"
        echo "$FEATURES" | grep -qi 'FMA' && ok "FMA: present" || warn "FMA not detected"
    else
        grep -qm1 avx2 /proc/cpuinfo 2>/dev/null && ok "AVX2: present" \
            || warn "AVX2 not detected; scalar kernels will be used"
        grep -qm1 fma /proc/cpuinfo 2>/dev/null && ok "FMA: present" || warn "FMA not detected"
    fi
else
    warn "architecture $ARCH uses the portable scalar C99 path"
fi

# --------------------------------------------------------------------- memory --
hdr "memory"
MEM_BYTES=0
AVAIL_BYTES=0
if [ "$OS" = Darwin ]; then
    MEM_BYTES=$(sysctl -n hw.memsize 2>/dev/null || echo 0)
    VMSTAT=$(vm_stat 2>/dev/null || true)
    PAGE_SIZE=$(printf '%s\n' "$VMSTAT" | awk '/page size of/ {gsub(/[^0-9]/,"",$8); print $8; exit}')
    # Free plus inactive only, matching the engine's own mem_available_bytes(). Speculative
    # pages are deliberately left out: in the raw Mach struct they are already inside
    # free_count, and counting a class twice here would wave a machine through into a
    # 1.56 TB download it cannot serve. Understating is the safe direction for this gate.
    AVAIL_PAGES=$(printf '%s\n' "$VMSTAT" | awk -F: '
        /^Pages free|^Pages inactive/ {
            gsub(/[^0-9]/,"",$2); s += $2
        }
        END {printf "%.0f", s+0}')
    if [ -n "${PAGE_SIZE:-}" ] && [ -n "${AVAIL_PAGES:-}" ]; then
        AVAIL_BYTES=$(awk -v p="$PAGE_SIZE" -v n="$AVAIL_PAGES" 'BEGIN {printf "%.0f", p*n}')
    fi
else
    MEM_KB=$(awk '/MemTotal/{print $2}' /proc/meminfo 2>/dev/null || echo 0)
    AVAIL_KB=$(awk '/MemAvailable/{print $2}' /proc/meminfo 2>/dev/null || echo 0)
    MEM_BYTES=$((MEM_KB * 1024))
    AVAIL_BYTES=$((AVAIL_KB * 1024))
fi
MEM_GB=$(awk -v b="${MEM_BYTES:-0}" 'BEGIN {printf "%d", b/1024/1024/1024}')
AVAIL_GB=$(awk -v b="${AVAIL_BYTES:-0}" 'BEGIN {printf "%d", b/1024/1024/1024}')
if [ "$AVAIL_BYTES" -gt 0 ] 2>/dev/null; then
    ok "total: ${MEM_GB} GiB, reclaimable now: ${AVAIL_GB} GiB"
else
    warn "could not determine reclaimable memory; total is ${MEM_GB} GiB"
    AVAIL_GB=$MEM_GB
fi

# Preset boundaries follow the project's measured memory ladder.
#
# The number the boundaries are applied to differs by platform, on purpose. Linux
# MemAvailable is a kernel ESTIMATE that already accounts for reclaimable page cache, so
# it is directly comparable to the ladder. The Darwin figure is free + inactive VM pages,
# which deliberately omits reclaimable file-backed pages sitting in the active queue --
# a real and often large pool. It therefore understates, and understating must not turn
# into a refusal: a 64 GiB Mac in the middle of a working day can easily show under
# 10 GiB free+inactive and still run this perfectly well once macOS evicts its caches.
# So on Darwin the hard floor is checked against INSTALLED memory, and the instantaneous
# figure only chooses the preset and triggers a "close some apps" warning.
if [ "$OS" = Darwin ]; then
    FLOOR_GB=$MEM_GB
else
    FLOOR_GB=$AVAIL_GB
fi
PRESET_GB=$AVAIL_GB
[ "$PRESET_GB" -gt "$MEM_GB" ] 2>/dev/null && PRESET_GB=$MEM_GB

if   [ "$PRESET_GB" -ge 192 ]; then PRESET=server;      EXPECT="published Linux figure ~19-21 s/token"
elif [ "$PRESET_GB" -ge  96 ]; then PRESET=workstation; EXPECT="published Linux figure ~24 s/token"
elif [ "$PRESET_GB" -ge  32 ]; then PRESET=desktop;     EXPECT="published Linux figure ~28-31 s/token"
elif [ "$PRESET_GB" -ge  10 ]; then PRESET=laptop;      EXPECT="published Linux figure ~32 s/token"
else PRESET=""; EXPECT=""; fi

if [ "$FLOOR_GB" -lt 10 ] 2>/dev/null; then
    if [ "$OS" = Darwin ]; then
        bad "${MEM_GB} GiB installed, below the engine's measured floor (~8.2 GB peak RSS)"
    else
        bad "under 10 GiB available, below the engine's measured floor (~8.2 GB peak RSS)"
    fi
elif [ -n "$PRESET" ]; then
    ok "recommended memory preset: --preset $PRESET"
    if [ "$OS" = Linux ]; then
        info "$EXPECT"
    else
        info "macOS speed must be measured on this Mac"
        info "free+inactive omits reclaimable cached files, so this is a lower bound"
    fi
else
    # Installed memory clears the floor, the instantaneous figure does not.
    PRESET=laptop
    warn "only ${AVAIL_GB} GiB free right now on a ${MEM_GB} GiB Mac; close applications"
    info "starting anyway is usually fine: macOS evicts cached files under pressure"
    ok "recommended memory preset: --preset $PRESET"
fi

# -------------------------------------------------------------------- storage --
hdr "storage"
TARGET="${MODEL_DIR:-$PWD}"
if [ -d "$TARGET" ]; then
    AVAIL_DISK=$(df -Pk "$TARGET" 2>/dev/null | awk 'NR==2 {printf "%d", $4/1024/1024}')
    ok "free space at $TARGET: ${AVAIL_DISK:-?} GiB"
    if [ -n "${AVAIL_DISK:-}" ] && [ "$AVAIL_DISK" -lt 1700 ]; then
        warn "the full checkpoint needs ~1.56 TB plus ~109 GB for the packed trunk"
    fi

    PROBE_MB="${K3_DOCTOR_PROBE_MB:-2048}"
    case "$PROBE_MB" in *[!0-9]*|'') warn "invalid K3_DOCTOR_PROBE_MB=$PROBE_MB; skipping probe"; PROBE_MB=0;; esac
    if [ "$PROBE_MB" -gt 0 ]; then
        printf '  %smeasuring sequential read (%s MB temporary file)…%s\n' "$DIM" "$PROBE_MB" "$RST"
        TMPF="$TARGET/.k3_doctor_probe.$$"
        if dd if=/dev/zero of="$TMPF" bs=1048576 count="$PROBE_MB" 2>/dev/null; then
            sync
            TIMING=$({ /usr/bin/time -p sh -c 'dd if="$1" of=/dev/null bs=4194304 2>/dev/null' sh "$TMPF"; } 2>&1)
            SECONDS_REAL=$(printf '%s\n' "$TIMING" | awk '$1=="real"{print $2; exit}')
            rm -f "$TMPF"
            if [ -n "${SECONDS_REAL:-}" ] && awk -v s="$SECONDS_REAL" 'BEGIN {exit !(s>0)}'; then
                RATE=$(awk -v mb="$PROBE_MB" -v s="$SECONDS_REAL" 'BEGIN {printf "%.0f MB/s", mb/s}')
                # Say what this number is. The file was written moments ago and is still
                # in the buffer cache, and nothing here can evict it without privileges
                # (BSD dd has no conv=fsync, and `purge` needs sudo). So the figure is an
                # UPPER BOUND that may be measuring RAM, and reporting it as the disk's
                # sequential rate would be the sort of confident wrong number that sends
                # someone into a 1.56 TB download on a slow external drive.
                ok "sequential read probe: $RATE (upper bound)"
                info "the file is still cached, so this can measure RAM rather than the disk"
                info "for a real figure use a probe larger than RAM, or the vendor spec"
                info "the engine streams roughly 135 GB per token at the smallest budgets"
            else
                warn "read probe completed, but its duration could not be parsed"
            fi
        else
            warn "could not write a probe file to $TARGET"
            rm -f "$TMPF" 2>/dev/null
        fi
    fi
else
    warn "no model directory given; pass one as the first argument to check its storage"
fi

# ---------------------------------------------------------------- model files --
if [ -n "$MODEL_DIR" ]; then
    hdr "model"
    N=0
    for shard in "$MODEL_DIR"/*.safetensors; do
        [ -f "$shard" ] || continue
        N=$((N + 1))
    done
    if [ "$N" -eq 0 ]; then
        warn "no .safetensors shards in $MODEL_DIR; run scripts/download-model.sh"
    else
        ok "shards present: $N"
        [ "$N" -eq 96 ] || warn "expected 96 shards for the full checkpoint"
    fi
    for f in config.json tiktoken.model tokenizer_config.json; do
        [ -f "$MODEL_DIR/$f" ] && ok "$f" || warn "$f missing (needed for text in/out)"
    done
fi

hdr "result"
if [ "$FAILED" -eq 0 ]; then
    printf '  %sthis machine can run the macOS-compatible Kimi K3 engine%s\n' "$GRN" "$RST"
    if [ -n "$PRESET" ]; then
        M="${MODEL_DIR:-<model_dir>}"
        printf '\n  next:\n'
        if [ "$OS" = Darwin ]; then
            if [ "$HAVE_BREW_OMP" -eq 1 ]; then
                printf '    %smake -j%s%s\n' "$DIM" "$NCPU" "$RST"
            else
                printf '    %smake macos -j%s%s\n' "$DIM" "$NCPU" "$RST"
                printf '    %s# or, after brew install libomp: make macos-openmp -j%s%s\n' "$DIM" "$NCPU" "$RST"
            fi
        else
            printf '    %smake -j%s%s\n' "$DIM" "$NCPU" "$RST"
        fi
        printf '    %s./scripts/pack-trunk.sh %s ~/k3trunk%s\n' "$DIM" "$M" "$RST"
        printf '    %s./bin/k3 %s --trunk ~/k3trunk --preset %s \\%s\n' "$DIM" "$M" "$PRESET" "$RST"
        printf '    %s         --tok %s --prompt "Hello" --gen 8 --incremental%s\n' "$DIM" "$M" "$RST"
    fi
    exit 0
fi
printf '  %sblocking problems above%s\n' "$RED" "$RST"
exit 1
'''


def patch_doctor(root: Path) -> list[tuple[str, str]]:
    path = root / "scripts/k3-doctor.sh"
    if not path.is_file():
        raise PortError("missing expected file: scripts/k3-doctor.sh")
    text = _stage_read(path)
    marker = "k3-doctor, check whether this Linux or macOS machine can run Kimi K3"
    if marker in text:
        result = "already patched"
    else:
        if "LINUX ONLY" not in text or "k3-doctor: this script and the streaming engine are Linux-only" not in text:
            raise PortError("upstream context changed in scripts/k3-doctor.sh")
        result = "changed"
    _stage_write(path, DOCTOR if result == "changed" else text, executable=True)
    return [("cross-platform machine doctor", result)]


def patch_download(root: Path) -> list[tuple[str, str]]:
    changed: list[tuple[str, str]] = []
    old = r'''N=$(find "$DEST" -maxdepth 1 -name '*.safetensors' | wc -l)
B=$(find "$DEST" -maxdepth 1 -name '*.safetensors' -printf '%s\n' | awk '{s+=$1} END{print s+0}')
'''
    new = r'''# BSD find on macOS has no -printf. Python is already a required dependency and gives
# the same count/byte-total calculation on both operating systems.
TOTALS=$(python3 - "$DEST" <<'PY'
from pathlib import Path
import sys
files = sorted(Path(sys.argv[1]).glob("*.safetensors"))
print(len(files), sum(p.stat().st_size for p in files))
PY
)
read -r N B <<< "$TOTALS"
'''
    changed.append(("portable shard totals", replace_once(root, "scripts/download-model.sh", old, new)))

    old = r'''        got=$(stat -c%s "$DEST/$name" 2>/dev/null || echo 0)
'''
    new = r'''        if [ -f "$DEST/$name" ]; then
            got=$(wc -c < "$DEST/$name" | tr -d '[:space:]')
        else
            got=0
        fi
'''
    changed.append(("portable per-shard sizes", replace_once(root, "scripts/download-model.sh", old, new)))
    return changed


def patch_pack_trunk(root: Path) -> list[tuple[str, str]]:
    old = r'''# find, not `ls | wc -l`: under `set -euo pipefail` a glob that matches nothing makes
# ls exit non-zero, the pipeline fails, and the script dies AT THIS LINE -- so the
# diagnostic on the next line, which is the whole reason the check exists, never prints.
N=$(find "$MODEL" -maxdepth 1 -name '*.safetensors' | wc -l)
[ "$N" -gt 0 ] || { echo "no .safetensors in $MODEL, run download-model.sh first"; exit 1; }
'''
    new = r'''# Count only top-level shards without GNU find's non-portable -maxdepth option.
N=0
for shard in "$MODEL"/*.safetensors; do
    [ -f "$shard" ] || continue
    N=$((N + 1))
done
[ "$N" -gt 0 ] || { echo "no .safetensors in $MODEL, run download-model.sh first"; exit 1; }
'''
    return [("portable trunk shard count", replace_once(root, "scripts/pack-trunk.sh", old, new))]


MACOS_DOC = r'''# Running kimi-k3-in-c on macOS

This port supports native builds on both Apple Silicon (`arm64`) and Intel (`x86_64`). It
keeps the Linux behavior intact while mapping the operating-system-specific pieces to
Darwin equivalents.

Apple Silicon is the forward-looking target. macOS 26 (Tahoe) was announced as the last
release supporting Intel Macs, so on macOS 27 and later only the `arm64` path is
reachable. The `x86_64` path is retained for Intel Macs still on macOS 26 or earlier.

## Build

Install Apple's command-line tools once:

```bash
xcode-select --install
```

A dependency-free build with stock Apple Clang is:

```bash
make macos -j"$(sysctl -n hw.logicalcpu)"
make OMP_CFLAGS= OMP_LDFLAGS= test
```

That build is intentionally valid without OpenMP. For the threaded build:

```bash
brew install libomp
make macos-openmp -j"$(sysctl -n hw.logicalcpu)"
make test
```

A normal `make` also detects Homebrew `libomp` automatically when it is already installed.
Detection probes for `$(brew --prefix libomp)/lib/libomp.dylib` rather than trusting the
exit status of `brew --prefix`, which reports a path for uninstalled formulae too.
CMake is supported as well:

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DK3_ENABLE_OPENMP=OFF
cmake --build build -j"$(sysctl -n hw.logicalcpu)"
ctest --test-dir build --output-on-failure
```

## What changed

* Linux `O_DIRECT` becomes `F_NOCACHE` on macOS for both the packed trunk and streamed
  expert descriptors. Buffered fallback remains available when a filesystem refuses the
  cache-bypass policy.
* Linux `posix_fadvise(..., POSIX_FADV_WILLNEED)` becomes Darwin `F_RDADVISE` on the
  buffered path.
* `ru_maxrss` is interpreted in bytes on Darwin and KiB on Linux, preventing a 1024x
  overstatement of macOS peak memory.
* Available memory comes from Mach VM statistics instead of `/proc/meminfo`.
* AVX2/FMA flags are emitted only for x86-64. Apple Silicon uses hand-written NEON
  implementations for bf16 and MXFP4 dot products plus portable C99 fallbacks elsewhere.
* OpenMP is optional on macOS and can be supplied by Homebrew `libomp`.
* Model download and trunk scripts no longer depend on GNU-only `find -maxdepth`,
  `find -printf` or `stat -c`.

## What is still Linux-only

`benchmarks/memory-ladder.sh` and `benchmarks/split-sweep.sh` remain Linux-only, and
deliberately so. Both impose a real memory ceiling with `systemd-run` cgroup scopes, and
macOS has no equivalent: without a ceiling every rung would use as much memory as it
likes, so the harness would print a complete table that measures nothing. Both scripts
check for `systemd-run` and exit with that explanation rather than producing a misleading
result, so running them on a Mac fails immediately instead of quietly.

Everything under `scripts/` — the doctor, the model download and the trunk packer — does
run on macOS.

## Full model

The operational requirements have not become smaller: the checkpoint is about 1.56 TB and
the packed trunk about 109 GB. Keep both on fast local storage. The smallest published
preset still has a measured Linux peak near 8.2 GB, so a Mac with only 8 GB unified memory
is not a safe target once macOS and other processes are included.

Run the platform-aware check before downloading weights:

```bash
./scripts/k3-doctor.sh
# or include an existing model directory to check that volume:
./scripts/k3-doctor.sh /Volumes/FastSSD/k3model
```

Then follow the normal workflow:

```bash
export HF_TOKEN=hf_your_token_here
./scripts/download-model.sh /Volumes/FastSSD/k3model
./scripts/pack-trunk.sh /Volumes/FastSSD/k3model /Volumes/FastSSD/k3trunk
./bin/k3 /Volumes/FastSSD/k3model \
  --trunk /Volumes/FastSSD/k3trunk \
  --preset laptop \
  --tok /Volumes/FastSSD/k3model \
  --prompt "The capital of France is" \
  --gen 8 --incremental
```

## Performance status

The existing published timing table was measured on Linux x86-64 with AVX2/FMA and
OpenMP. It must not be reused as an Apple Silicon prediction. This port establishes a
correct native arm64 build, two hand-written NEON dot-product paths and macOS I/O
behavior. It deliberately does not claim full-model Apple Silicon performance that has
not been measured against the 1.56 TB checkpoint on actual Apple hardware.

## Numerical reproducibility

Every build target passes `-ffp-contract=off`, including `debug`, `asan` and `ubsan`.
This is not optional on Apple Silicon. The reduction loops are written as
`s0 += w[i] * x[i]` in a deliberate four-accumulator split, and aarch64 has fused
multiply-add in its baseline ISA, so clang will fuse those statements unless told not to
and the result stops matching the reference the op tests compare against. On x86-64 the
same targets get away with it only because clearing `ARCH` also drops `-mfma`, leaving
the compiler no FMA instruction to emit; aarch64 has no such accident to rely on.
'''


def patch_readme_and_docs(root: Path) -> list[tuple[str, str]]:
    changed: list[tuple[str, str]] = []
    old = r'''| **OS** | Linux, x86-64 | uses `O_DIRECT`, `posix_memalign`, `getrusage` |
| **CPU** | AVX2 + FMA | AVX-512 unnecessary. `make portable` targets generic AVX2 |
| **RAM** | 8 GB and up | every preset works; more memory is faster, never different |
| **Storage** | ~1.7 TB free | 1.56 TB checkpoint + 109 GB packed trunk, ideally on fast local disk |
| **Toolchain** | GCC ≥ 9 or Clang ≥ 10 | GNU make, or CMake |
'''
    new = r'''| **OS** | Linux x86-64; macOS on Apple Silicon or Intel | `O_DIRECT` on Linux, `F_NOCACHE` on macOS |
| **CPU** | AVX2 + FMA on x86-64; NEON dot products on arm64 | portable C99 fallbacks remain for other kernels |
| **RAM** | 8 GB and up | every preset works; more memory is faster, never different |
| **Storage** | ~1.7 TB free | 1.56 TB checkpoint + 109 GB packed trunk, ideally on fast local disk |
| **Toolchain** | GCC ≥ 9, Clang ≥ 10, or Apple Clang | GNU make, or CMake; OpenMP optional on macOS |
'''
    changed.append(("README requirements", replace_once(root, "README.md", old, new)))

    old = r'''The tokenizer and config reader are portable C99 and build anywhere. Without a checkpoint
you can still do everything in [Quick start](#quick-start).
'''
    new = r'''The tokenizer and config reader are portable C99 and build anywhere. Without a checkpoint
you can still do everything in [Quick start](#quick-start). macOS setup, I/O mappings and
performance caveats are documented in [`docs/MACOS.md`](docs/MACOS.md).
'''
    changed.append(("README macOS guide link", replace_once(root, "README.md", old, new)))

    old = r'''make -j            # seconds. Seven C files, a compiler and OpenMP
make test          # under a minute
'''
    new = r'''make -j            # Linux; on macOS this auto-detects Homebrew libomp
make macos -j      # stock Apple Clang, no external OpenMP dependency
make test          # under a minute
'''
    changed.append(("README quick start", replace_once(root, "README.md", old, new)))

    old = r'''Seconds. The only dependencies are a C99 compiler, libm and OpenMP. CMake works too:
'''
    new = r'''Seconds. Linux uses OpenMP by default. macOS builds with stock Apple Clang without it,
and automatically uses Homebrew `libomp` when installed. CMake works too:
'''
    changed.append(("README build dependencies", replace_once(root, "README.md", old, new)))

    changed.append(("macOS guide", write_file(root, "docs/MACOS.md", MACOS_DOC)))
    return changed


def patch_ci(root: Path) -> list[tuple[str, str]]:
    old = r'''  # Warnings are defects here. The engine does arithmetic on `const void *` weight
  # pointers, where a missing -Wpointer-arith silently strides by one byte.
  strict-warnings:
'''
    new = r'''  # Native Darwin coverage. macos-26 is the newest generally-available image and is the
  # closest proxy for the macOS 27 target; macos-15 keeps the previous major honest.
  # Both are Apple Silicon. macos-26-intel covers the x86-64 line, which ends with
  # macOS 26 -- Apple announced Tahoe as the last Intel-capable release, so no Intel
  # runner will ever exercise macOS 27. Add a macos-27 entry once that image is GA.
  macos-build-and-test:
    name: build + test (${{ matrix.os }})
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [macos-26, macos-15, macos-26-intel]
    steps:
      - uses: actions/checkout@v7
      - name: Toolchain
        run: |
          sw_vers
          uname -m
          cc --version
      - name: Build with stock Apple Clang
        run: make macos -j"$(sysctl -n hw.logicalcpu)"
      - name: Build weightless tests
        run: |
          make OMP_CFLAGS= OMP_LDFLAGS= \
            bin/test_ops bin/test_cache bin/test_st bin/test_cfg bin/test_tok bin/k3_model \
            -j"$(sysctl -n hw.logicalcpu)"
      - name: Run correctness gates
        run: |
          ./bin/test_ops tests/fixtures/ops
          ./bin/test_cache tests/fixtures/cache
          ./bin/test_st tests/fixtures/st "$RUNNER_TEMP/idx.json" \
            plain.f32.2d plain.bf16.1d tricky.f16.1d packed.u8.2d scalar.f32 second.shard.f32
          ./bin/test_cfg fixture tests/fixtures/ref_k3.json
          ./bin/k3_model tests/fixtures
      - name: CMake build and tests
        run: |
          cmake -S . -B build-cmake -DCMAKE_BUILD_TYPE=Release -DK3_ENABLE_OPENMP=OFF
          cmake --build build-cmake -j"$(sysctl -n hw.logicalcpu)"
          ctest --test-dir build-cmake --output-on-failure

  # Warnings are defects here. The engine does arithmetic on `const void *` weight
  # pointers, where a missing -Wpointer-arith silently strides by one byte.
  strict-warnings:
'''
    return [("macOS CI matrix", replace_once(root, ".github/workflows/ci.yml", old, new))]


def apply(root: Path) -> list[tuple[str, str]]:
    _STAGE.clear()          # never inherit a previous (possibly failed) run's staged edits
    required = ["Makefile", "CMakeLists.txt", "README.md", "src/core/k3_ops.c"]
    for relative in required:
        if not (root / relative).exists():
            raise PortError(f"{root} does not look like kimi-k3-in-c (missing {relative})")

    changes: list[tuple[str, str]] = []
    for operation in (
        patch_makefile,
        patch_cmake,
        patch_ops,
        patch_safetensors,
        patch_trunk,
        patch_cache,
        patch_cli,
        patch_doctor,
        patch_download,
        patch_pack_trunk,
        patch_readme_and_docs,
        patch_ci,
    ):
        changes.extend(operation(root))
    # Nothing has touched the working tree yet: every replacement matched, so flush.
    _commit(root)
    return changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".", help="path to a kimi-k3-in-c checkout")
    parser.add_argument("--print-base-commit", action="store_true")
    args = parser.parse_args()
    if args.print_base_commit:
        print(BASE_COMMIT)
        return 0
    root = Path(args.root).expanduser().resolve()
    try:
        changes = apply(root)
    except (OSError, PortError) as exc:
        print(f"macOS port failed: {exc}", file=sys.stderr)
        return 1

    for name, status_ in changes:
        print(f"{status_:>15}  {name}")
    print(f"\nmacOS port applied to {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
