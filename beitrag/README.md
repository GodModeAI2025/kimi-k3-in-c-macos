# Vorbereiteter Upstream-Beitrag

Hier liegt der Teil des Ports, der nach der Messung vom 4. September 2026 als einziger
noch ohne Umbau in `FareedKhan-dev/kimi-k3-in-c` passt: die Erkennung von Homebrews
libomp im Makefile. Die vollständige Messung, Zeile für Zeile, steht in
[UPSTREAM.md](../UPSTREAM.md).

**Stand: nichts davon ist eingereicht.** Es gibt keinen Fork, keinen Branch beim
Upstream und keinen Pull Request. Gegen den echten Upstream ist `einreichen.sh` nur mit
`--probe` gelaufen; der Veröffentlichungspfad ist ausschließlich gegen Attrappen von
`git` und `gh` geprüft worden, die jeden Aufruf protokollieren und nichts weitergeben.

| Datei | Inhalt |
| --- | --- |
| `0001-build-without-openmp-when-libomp-is-absent-on-macos.patch` | der Patch, `git format-patch` gegen `117e9d2`; lässt sich unverändert auf `ac1584a` anwenden, siehe [Nachmessung](../UPSTREAM.md#nachmessung-gegen-upstream-main-16-september-2026) |
| `PR.md` | der Text des Pull Requests, nach der Vorlage aus `.github/PULL_REQUEST_TEMPLATE.md` des Upstream |
| `einreichen.sh` | Probelauf und Einreichung |

## Der Befund

Der Upstream setzt im Darwin-Zweig des Makefile `-lomp` unbedingt und prüft danach nur
noch, ob `omp.h` existiert; findet er sie nicht, gibt er zwei `$(warning)` aus und baut
trotzdem mit den OpenMP-Flags weiter. Auf einem Mac mit Homebrew, aber ohne libomp
übersetzt `make` also alle Objekte und stirbt dann am Linker. Nachgestellt auf
Upstream-`main`, indem `OMP_PREFIX` auf ein Verzeichnis zeigt, das es nicht gibt, was der
einzige Eingang der Erkennung ist:

```
$ make OMP_PREFIX=/opt/homebrew/opt/libomp-not-installed bin/k3
Makefile:70: libomp not found at /opt/homebrew/opt/libomp-not-installed. Install it with `brew install libomp`,
Makefile:71: or point the build at another copy with `make OMP_PREFIX=/path/to/libomp`.
[... alle sechs Objekte übersetzen fehlerfrei ...]
ld: warning: search path '/opt/homebrew/opt/libomp-not-installed/lib' not found
ld: library 'omp' not found
clang: error: linker command failed with exit code 1 (use -v to see invocation)
make: *** [bin/k3] Error 1
```

Die vorhandene Prüfung kann den Fall nicht abfangen, weil `brew --prefix` für eine nicht
installierte Formel einen Pfad ausgibt und mit 0 endet:

```
$ brew list --formula | grep -x cowsay || echo "cowsay ist nicht installiert"
cowsay ist nicht installiert
$ brew --prefix cowsay; echo "rc=$?"
/opt/homebrew/opt/cowsay
rc=0
```

Der Pfad ist also fast immer nicht leer, das `$(wildcard)` greift nur, wenn das
Verzeichnis zufällig fehlt, und selbst dann bleibt `-lomp` auf der Linkzeile stehen.

## Was der Patch ändert

Er prüft die zwei Dateien, die der Build wirklich braucht, `omp.h` und `libomp.dylib`.
Fehlt eine davon, fallen die OpenMP-Flags weg statt der Build. Jede parallele Region im
Upstream steht hinter `#ifdef _OPENMP`, und `<omp.h>` wird nirgends eingebunden, deshalb
entsteht ein korrektes einkerniges Binary und kein Übersetzungsfehler. Dazu kommt ein
Schritt im macOS-Job der Upstream-CI, der genau diesen Weg fährt: der Job installiert
libomp und läuft sonst nie dort entlang.

Gemessen auf macOS 27, Apple Silicon, Apple clang 21.0.0, gegen `117e9d2`:

| Lauf | `make` | `otool -L bin/k3` | `make test` |
| --- | --- | --- | --- |
| vorher, ohne libomp | `ld: library 'omp' not found`, Error 1 | kein Binary | kommt nicht so weit |
| nachher, ohne libomp | linkt, drei `$(warning)` | ohne libomp | `22 passed, 0 failed, 0 skipped`, `ALL WEIGHTLESS TESTS PASSED` |
| nachher, mit libomp | linkt, still | `libomp.dylib` | dieselbe Ausgabe |
| nachher, `make portable`, beide Fälle | linkt | wie oben | keine Compiler-Warnung |

Bewusst nicht im Patch: der `-Wl,-rpath`-Zusatz und die Ziele `macos` und
`macos-openmp` aus diesem Port. Sobald die Erkennung stimmt, tun beide nichts mehr, was
`make` nicht selbst täte, und ein Pull Request, der drei Dinge auf einmal will, wird
langsamer gelesen.

## Einreichen

```bash
beitrag/einreichen.sh
```

Das Skript holt `main` frisch, wendet den Patch mit `git am` an, legt den Fork an, pusht
den Branch und öffnet den Pull Request mit dem Text aus `PR.md`. Vorher fragt es einmal
nach. `beitrag/einreichen.sh --probe` macht nur die erste Hälfte und veröffentlicht
nichts; das ist der Lauf, mit dem sich am Tag der Einreichung prüfen lässt, ob der Patch
noch passt.

Die Optionen werden alle gelesen, an welcher Stelle sie auch stehen. `--probe` schlägt
`--ja`: wo beide stehen, endet der Lauf nach dem Probelauf. Eine unbekannte Option bricht
mit Rückgabewert 2 ab, bevor irgendetwas geholt wird. Das war nicht immer so: bis dahin
wertete das Skript nur sein erstes Argument aus, weshalb `einreichen.sh --ja --probe`
das `--probe` still verwarf und ohne Rückfrage Fork, Push und Pull Request fuhr. Gemessen
gegen eine Attrappe von `git` und `gh`, die jeden Aufruf mitschreibt: vorher sieben
Fremdaufrufe bis `gh pr create`, danach ein einziger `git clone` und die Meldung
`Probelauf beendet, es wurde nichts veroeffentlicht.`

Beim ersten Lauf richtet das Skript mit `gh auth setup-git` den Credential-Helper von
`gh` ein, weil ein HTTPS-Push sonst nach einem Passwort fragt, das es nicht mehr gibt.
Den frisch angelegten Fork wartet es ab: GitHub legt ihn asynchron an, deshalb drei
Anläufe mit Pause statt eines 404, das wie ein Fehler im Patch aussieht.

Zwei Dinge, die vor dem Aufruf zu entscheiden sind: der Patch trägt die Autorenzeile und
die Trailer, unter denen er entstanden ist. Wer das anders haben möchte, ändert den
`From:`-Kopf der Patch-Datei oder amendet den Commit nach `git am`. Und der Upstream
schreibt in `CONTRIBUTING.md` Commits im Imperativ und ohne Vergangenheitsform vor,
weshalb Patch und Pull-Request-Text als einzige Texte dieses Repositoriums englisch sind.
