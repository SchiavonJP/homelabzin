# Offline Git updates

Load the two Bash functions on each computer:

```bash
source /path/to/homelabzin/scripts/git-bundle-aliases.sh
```

Add that line to `~/.bashrc` to load them in future Bash sessions. These are
functions rather than literal aliases because they accept arguments. They also
work in Zsh. Git, `mktemp`, and standard shell utilities must be installed.

From inside a repository, commit your changes and create a bundle:

```bash
bundle
```

The command prints the file's location under `~/git-bundles/`. An optional path
chooses the output instead: `bundle ~/Downloads/homelabzin.bundle`. Existing
files are never overwritten. Each bundle contains the complete history reachable
from all current refs and HEAD, so earlier bundles are not required.

On the receiving computer, inside an existing checkout:

```bash
unbundle ~/Downloads/homelabzin.bundle
```

For the first import, use a destination directory that does not exist yet:

```bash
unbundle ~/Downloads/homelabzin.bundle ~/Projects/homelabzin
```

The first import creates a checkout on `main`. For another branch, pass its
name as a third argument: `unbundle update.bundle ~/Projects/repo develop`.
Git bundles do not store the symbolic branch name of HEAD, so choosing the
initial branch explicitly avoids Git guessing incorrectly.

Later imports fast-forward the current
branch with the same name. Divergent histories are rejected; local commits are
not overwritten. Other branches are available as `bundle/<branch>`; tags and
Git notes are imported too. Conflicting tag/note updates are rejected. Your
existing GitHub remote is not changed. A new checkout has a local `bundle`
remote, which points at the input file; it does not automatically set up GitHub.

Both commands reject uncommitted or untracked changes. **A stash is not applied
by `unbundle`: commit work you want to transfer.** Ignored files such as `.env`,
Git LFS payloads, submodule repositories, hooks, and machine configuration are
not transferred by these commands. A receiver's ignored files are left to Git's
normal checkout handling; keep a separate backup of important local configuration.
Commit history can itself contain sensitive information, so keep bundles private.
These commands only create and read local files; they do not send files or
change endpoint-security settings.

Run the offline integration checks with:

```bash
bash scripts/test-git-bundle-aliases.sh
```
