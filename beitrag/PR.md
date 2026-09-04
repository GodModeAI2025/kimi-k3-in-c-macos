## What this changes

On macOS the build no longer requires Homebrew's libomp. When `omp.h` and
`libomp.dylib` are both present under `OMP_PREFIX`, the flags are wired up exactly as
before; when either is missing, the Makefile drops the OpenMP flags and builds a
single-threaded binary instead of failing at the link.

## Why

`make` on a Mac that has Homebrew but no libomp compiles every object and then dies:

```
ld: warning: search path '/opt/homebrew/opt/libomp/lib' not found
ld: library 'omp' not found
clang: error: linker command failed with exit code 1
make: *** [bin/k3] Error 1
```

Nothing in a normal macOS toolchain installs libomp, so this is the default state of a
Mac rather than an edge case, and it contradicts README.md's "macOS/arm64 builds with
plain `make`".

The existing guard cannot catch it, because `brew --prefix libomp` prints a path and
exits 0 for a formula that is not installed:

```
$ brew list --formula | grep -x cowsay || echo "cowsay is not installed"
cowsay is not installed
$ brew --prefix cowsay; echo "exit=$?"
/opt/homebrew/opt/cowsay
exit=0
```

So the wildcard check on `omp.h` fires only when the prefix directory happens to be
absent, and even then it only warns while `-lomp` stays on the link line. This patch
probes for the two files the build actually consumes and changes the flags accordingly.

The macOS CI job runs `brew install libomp` and therefore never walks the fallback path,
so it gets a step that points `OMP_PREFIX` at a directory that does not exist, which is
the only input the detection block has.

## Verification

- [x] `make test` passes (all weightless gates)
- [x] `make portable` builds with no new warnings
- [ ] If kernels changed: not applicable, no kernel touched
- [ ] If the config or tokenizer path changed: not applicable
- [x] If output could change: `./bin/k3_model tests/fixtures` reports
      `VERDICT: ENGINE MATCHES THE REFERENCE EXACTLY` in both build modes

Measured on macOS 27, Apple Silicon, Apple clang 21.0.0, against `117e9d2`:

| arm | `make` | `otool -L bin/k3` | `make test` |
|---|---|---|---|
| before, libomp absent | `ld: library 'omp' not found`, Error 1 | no binary | not reached |
| after, libomp absent | links, three `$(warning)` lines | no libomp | `22 passed, 0 failed, 0 skipped`, `ALL WEIGHTLESS TESTS PASSED` |
| after, libomp present | links, silent | `libomp.dylib` | same output |
| after, `make portable`, both states | links | as above | no compiler warnings |

"libomp absent" is reproduced with `make OMP_PREFIX=/path/that/does/not/exist`, which is
what the new CI step does and what a Mac without the formula produces on its own.

## Numbers, if this is a performance change

Not a performance change on any machine that has libomp: the flags are byte-identical
there. On a machine without it the binary is single-threaded where previously there was
no binary at all, so there is no before-arm to compare against. No timings were taken.

## Risk

A Mac with a half-installed libomp, header present and dylib missing or the reverse, now
builds serial where it previously failed at the link. That is the intended behaviour, but
it is quieter: someone who expects threads gets three `$(warning)` lines rather than a
stopped build. `OMP_CFLAGS`/`OMP_LDFLAGS` keep `?=`, so an explicit setting on the command
line or in the environment still overrides the detection in either direction.

The change is confined to the `Darwin` branch of the platform block; the Linux, MinGW and
generic branches are untouched, and the CI addition is a step inside the existing
`build-and-test-macos` job.
