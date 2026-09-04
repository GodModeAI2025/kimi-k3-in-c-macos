#!/usr/bin/env bash
# Regenerate SHA256SUMS from the versioned files.
#
# The manifest was maintained by hand, went stale twice during review and was still
# missing two entries afterwards. Deriving it from `git ls-files` removes the step where
# a newly added file can be forgotten. SHA256SUMS itself is the one versioned file that
# cannot appear in it, because a checksum file cannot contain its own checksum.
set -euo pipefail
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

command -v git >/dev/null 2>&1 || {
    echo "make-sha256sums: git is required to list the versioned files" >&2
    exit 1
}
# Not just "inside a work tree": unpacking the package into a subdirectory of some other
# repository would otherwise hash that repository's file list. --show-prefix is empty
# exactly at the root and, unlike a string comparison against --show-toplevel, it stays
# right when the path used to get here runs through a symlink, which on macOS is the
# normal case for anything under /tmp.
git -C "$HERE" rev-parse --is-inside-work-tree >/dev/null 2>&1 &&
[ -z "$(git -C "$HERE" rev-parse --show-prefix 2>/dev/null)" ] || {
    echo "make-sha256sums: $HERE is not the root of a git work tree" >&2
    exit 1
}

if command -v sha256sum >/dev/null 2>&1; then
    hash_of() { sha256sum -- "$1" | cut -d' ' -f1; }
elif command -v shasum >/dev/null 2>&1; then    # macOS ships shasum, not sha256sum
    hash_of() { shasum -a 256 -- "$1" | cut -d' ' -f1; }
else
    echo "make-sha256sums: neither sha256sum nor shasum is available" >&2
    exit 1
fi

TMPF=$(mktemp "${TMPDIR:-/tmp}/SHA256SUMS.XXXXXX")
trap 'rm -f "$TMPF"' EXIT HUP INT TERM

cd "$HERE"
# -z and read -d '': a path containing a space or a newline must not split into two
# entries, which is exactly the kind of silent gap this script exists to close.
while IFS= read -r -d '' f; do
    case "$f" in SHA256SUMS) continue ;; esac
    printf '%s  ./%s\n' "$(hash_of "$f")" "$f" >> "$TMPF"
done < <(git ls-files -z)

chmod 644 "$TMPF"
mv "$TMPF" "$HERE/SHA256SUMS"
trap - EXIT HUP INT TERM
printf 'make-sha256sums: wrote %s entries to SHA256SUMS\n' \
    "$(grep -c '' "$HERE/SHA256SUMS")"
