# Load with: source /path/to/homelabzin/scripts/git-bundle-aliases.sh
# Bash functions accept arguments; a plain alias cannot do this reliably.

bundle() (
    set -eu
    umask 077
    if [ "$#" -gt 1 ]; then
        printf 'Usage: bundle [output.bundle]\n' >&2
        exit 1
    fi
    local root output temporary
    root=$(git rev-parse --show-toplevel)
    if [ -f "$(git -C "$root" rev-parse --absolute-git-dir)/MERGE_HEAD" ]; then
        printf 'Finish or abort the current merge before bundling.\n' >&2
        exit 1
    fi
    if [ -n "$(git -C "$root" status --porcelain --untracked-files=all)" ]; then
        printf 'Commit or stash your changes, including untracked files, before bundling.\n' >&2
        exit 1
    fi
    if [ "$(git -C "$root" rev-parse --is-shallow-repository)" = true ]; then
        printf 'A complete backup requires a repository with full history.\n' >&2
        exit 1
    fi
    output=${1:-"$HOME/git-bundles/$(basename "$root")-$(date -u +%Y%m%dT%H%M%SZ).bundle"}
    if [ -e "$output" ] || [ -L "$output" ]; then
        printf 'Output already exists: %s\n' "$output" >&2
        exit 1
    fi
    mkdir -p "$(dirname "$output")"
    temporary=$(mktemp "${output}.tmp.XXXXXX")
    trap 'rm -f -- "$temporary"' EXIT
    git -C "$root" bundle create "$temporary" --all HEAD
    git -C "$root" bundle verify "$temporary"
    # Publishing with a hard link refuses to overwrite an existing backup.
    ln "$temporary" "$output"
    printf 'Created: %s\n' "$output"
)

unbundle() (
    set -eu
    local merge_mode=--ff-only
    if [ "${1:-}" = --merge ]; then
        merge_mode=--ff
        shift
    fi
    if [ "$#" -lt 1 ] || [ "$#" -gt 3 ]; then
        printf 'Usage: unbundle [--merge] input.bundle [destination] [branch]\n' >&2
        exit 1
    fi
    local archive destination branch
    archive="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
    destination=${2:-.}
    if [ ! -f "$archive" ]; then
        printf 'Bundle not found: %s\n' "$archive" >&2
        exit 1
    fi
    if [ ! -e "$destination" ]; then
        # Native Git bundles do not record HEAD's symbolic branch name.
        git clone --origin bundle --branch "${3:-main}" "$archive" "$destination"
    elif ! git -C "$destination" rev-parse --show-toplevel >/dev/null 2>&1; then
        printf 'Destination must be a Git checkout or a new directory.\n' >&2
        exit 1
    fi
    if [ -f "$(git -C "$destination" rev-parse --absolute-git-dir)/MERGE_HEAD" ]; then
        printf 'Finish or abort the current merge before importing another bundle.\n' >&2
        exit 1
    fi
    if [ -n "$(git -C "$destination" status --porcelain --untracked-files=all)" ]; then
        printf 'Commit or stash your local changes before unbundling.\n' >&2
        exit 1
    fi
    branch=$(git -C "$destination" symbolic-ref --quiet --short HEAD) || {
        printf 'Check out a branch before unbundling.\n' >&2
        exit 1
    }
    if [ "$#" -eq 3 ] && [ "$branch" != "$3" ]; then
        printf 'Check out branch %s before updating this checkout.\n' "$3" >&2
        exit 1
    fi
    git -C "$destination" bundle verify "$archive"
    if [ -z "$(git bundle list-heads "$archive" "refs/heads/$branch")" ]; then
        printf 'The bundle does not contain the current branch: %s\n' "$branch" >&2
        exit 1
    fi
    # Only bundle-tracking refs are replaced; local branches are never forced.
    git -C "$destination" fetch --atomic "$archive" \
        '+refs/heads/*:refs/remotes/bundle/*' \
        'refs/tags/*:refs/tags/*' \
        'refs/notes/*:refs/notes/*'
    if git -C "$destination" merge "$merge_mode" --no-edit "refs/remotes/bundle/$branch"; then
        return 0
    fi
    if [ "$merge_mode" = --ff-only ]; then
        printf 'For divergent histories, retry with: unbundle --merge <file> [destination] [branch]\n' >&2
    else
        printf 'Merge stopped. Run git status in the destination.\n' >&2
        printf 'Resolve conflicts, git add the resolved files, then git commit; or git merge --abort.\n' >&2
    fi
    exit 1
)
