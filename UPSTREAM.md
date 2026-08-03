# Upstream-Bezug

- Repository: https://github.com/FareedKhan-dev/kimi-k3-in-c
- geprüfter Commit: `85ab2cd901aa81b70caac7711f06864d594b8ff3`
- Stand des Ports: 3. August 2026
- Upstream-Lizenz: Apache License 2.0

Der Installer checkt exakt diesen Commit aus. `apply_macos_port.py` prüft zusätzlich jede
zu ändernde Quelltextstelle auf den erwarteten Kontext und bricht bei Abweichungen ab.

## Änderungskennzeichnung

Beim Anwenden werden unter anderem folgende Upstream-Dateien verändert:

- `Makefile`
- `CMakeLists.txt`
- `README.md`
- `src/core/k3_ops.c`
- `src/io/k3_st.c`
- `src/io/k3_trunk.c`
- `src/cache/k3_cache.c`
- `src/cli/k3_run.c`
- `scripts/k3-doctor.sh`
- `scripts/download-model.sh`
- `scripts/pack-trunk.sh`
- `.github/workflows/ci.yml`

Neu angelegt wird `docs/MACOS.md`. Der Installer exportiert danach alle Änderungen als
`*.patch`.
