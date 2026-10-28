#!/usr/bin/env bash
set -eu

source "$(cd "$(dirname "$0")" && pwd)/git-bundle-aliases.sh"
test_dir=$(mktemp -d "${TMPDIR:-/tmp}/git-bundle-tests.XXXXXX")
trap 'rm -rf -- "$test_dir"' EXIT
# Tests use isolated identity/config and never access a network remote.
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null
export GIT_AUTHOR_NAME=Test GIT_AUTHOR_EMAIL=test@example.invalid
export GIT_COMMITTER_NAME=Test GIT_COMMITTER_EMAIL=test@example.invalid

git init -b main "$test_dir/source repo" >/dev/null
cd "$test_dir/source repo"
printf 'first\n' > code.txt
printf '.env\n' > .gitignore
printf 'private local configuration\n' > .env
git add code.txt .gitignore
git commit -qm first
git branch other
git tag initial
git notes add -m 'test note'

bundle "$test_dir/first bundle.bundle" >/dev/null 2>&1
if bundle "$test_dir/first bundle.bundle" >/dev/null 2>&1; then
    printf 'FAIL: overwrote an existing backup\n' >&2; exit 1
fi
unbundle "$test_dir/first bundle.bundle" "$test_dir/receiver repo"
test "$(git rev-parse HEAD)" = "$(git -C "$test_dir/receiver repo" rev-parse HEAD)"
test ! -e "$test_dir/receiver repo/.env"
test "$(git -C "$test_dir/receiver repo" notes show)" = 'test note'
git -C "$test_dir/receiver repo" rev-parse --verify refs/remotes/bundle/other >/dev/null
git -C "$test_dir/receiver repo" rev-parse --verify refs/tags/initial >/dev/null

printf 'second\n' >> code.txt
if bundle "$test_dir/dirty.bundle" >/dev/null 2>&1; then
    printf 'FAIL: accepted uncommitted changes\n' >&2; exit 1
fi
git add code.txt
git commit -qm second
bundle "$test_dir/second.bundle" >/dev/null 2>&1
unbundle "$test_dir/second.bundle" "$test_dir/receiver repo"
test "$(git rev-parse HEAD)" = "$(git -C "$test_dir/receiver repo" rev-parse HEAD)"
cmp code.txt "$test_dir/receiver repo/code.txt"

printf 'local edit\n' >> "$test_dir/receiver repo/code.txt"
before=$(git -C "$test_dir/receiver repo" rev-parse HEAD)
if unbundle "$test_dir/second.bundle" "$test_dir/receiver repo" >/dev/null 2>&1; then
    printf 'FAIL: accepted a dirty destination\n' >&2; exit 1
fi
test "$before" = "$(git -C "$test_dir/receiver repo" rev-parse HEAD)"
git -C "$test_dir/receiver repo" add code.txt
git -C "$test_dir/receiver repo" commit -qm 'receiver edit'
printf 'source edit\n' >> code.txt
git add code.txt
git commit -qm 'source edit'
bundle "$test_dir/divergent.bundle" >/dev/null 2>&1
before=$(git -C "$test_dir/receiver repo" rev-parse HEAD)
if unbundle "$test_dir/divergent.bundle" "$test_dir/receiver repo" >/dev/null 2>&1; then
    printf 'FAIL: accepted divergent histories\n' >&2; exit 1
fi
test "$before" = "$(git -C "$test_dir/receiver repo" rev-parse HEAD)"

# Explicit merges preserve a real conflict for the user to resolve.
incoming=$(git rev-parse HEAD)
if unbundle --merge "$test_dir/divergent.bundle" "$test_dir/receiver repo" >/dev/null 2>&1; then
    printf 'FAIL: a conflicting merge unexpectedly succeeded\n' >&2; exit 1
fi
test "$incoming" = "$(git -C "$test_dir/receiver repo" rev-parse MERGE_HEAD)"
test "$before" = "$(git -C "$test_dir/receiver repo" rev-parse HEAD)"
# Even after staging an all-ours resolution, a pending merge must not be bundled.
git -C "$test_dir/receiver repo" checkout --ours -- code.txt
git -C "$test_dir/receiver repo" add code.txt
if (cd "$test_dir/receiver repo" && bundle "$test_dir/unfinished.bundle") >/dev/null 2>&1; then
    printf 'FAIL: bundled an unfinished merge\n' >&2; exit 1
fi
if unbundle --merge "$test_dir/divergent.bundle" "$test_dir/receiver repo" >/dev/null 2>&1; then
    printf 'FAIL: imported during an unfinished merge\n' >&2; exit 1
fi
printf 'first\nsecond\nlocal edit\nsource edit\n' > "$test_dir/receiver repo/code.txt"
git -C "$test_dir/receiver repo" add code.txt
git -C "$test_dir/receiver repo" commit -qm 'resolve both edits'
git -C "$test_dir/receiver repo" merge-base --is-ancestor "$before" HEAD
git -C "$test_dir/receiver repo" merge-base --is-ancestor "$incoming" HEAD
(cd "$test_dir/receiver repo" && bundle "$test_dir/merged.bundle") >/dev/null 2>&1
unbundle "$test_dir/merged.bundle" "$test_dir/source repo" >/dev/null 2>&1
test "$(git rev-parse HEAD)" = "$(git -C "$test_dir/receiver repo" rev-parse HEAD)"
cmp code.txt "$test_dir/receiver repo/code.txt"

# Independent file changes merge automatically, even with merge.ff=only configured.
printf 'source only\n' > source-only.txt
git add source-only.txt
git commit -qm 'independent source edit'
incoming=$(git rev-parse HEAD)
printf 'receiver only\n' > "$test_dir/receiver repo/receiver-only.txt"
git -C "$test_dir/receiver repo" add receiver-only.txt
git -C "$test_dir/receiver repo" commit -qm 'independent receiver edit'
before=$(git -C "$test_dir/receiver repo" rev-parse HEAD)
git -C "$test_dir/receiver repo" config merge.ff only
bundle "$test_dir/independent.bundle" >/dev/null 2>&1
unbundle --merge "$test_dir/independent.bundle" "$test_dir/receiver repo" >/dev/null 2>&1
git -C "$test_dir/receiver repo" merge-base --is-ancestor "$before" HEAD
git -C "$test_dir/receiver repo" merge-base --is-ancestor "$incoming" HEAD
test -f "$test_dir/receiver repo/source-only.txt"
test -f "$test_dir/receiver repo/receiver-only.txt"
printf 'PASS: restore, updates, refs, guards, divergence, merge conflicts, merged bundle round-trip, automatic merge\n'
