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
printf 'PASS: restore, updates, branches, tags, notes, ignored files, no overwrite, dirty checks, divergence\n'
