# Offline Git updates

Load the two Bash functions on each computer:

```bash
source /path/to/homelabzin/scripts/git-bundle-aliases.sh
```

Add that line to `~/.bashrc` for Bash or `~/.zshrc` for Zsh to load the functions
in future sessions. Run the `source` line in any already-open terminal too;
editing a startup file does not update existing shells. Use the absolute path
or a path beginning with `~/`, so loading works from any repository.

These are functions rather than literal aliases because they accept arguments.
Git, `mktemp`, and standard shell utilities must be installed.

If `bundle` reports `Could not locate Gemfile`, your shell is running Ruby's
Bundler instead of this function. Load this script, then run `type bundle`:
it must identify a function. Ruby's command remains available as `command bundle`.

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

Later imports fast-forward the current branch with the same name by default.
If both computers have new commits, explicitly allow a merge:

```bash
unbundle --merge ~/Downloads/homelabzin.bundle
```

This fast-forwards when possible and otherwise creates a merge commit preserving
both histories. If conflicts occur, the command stops with the merge in progress.
Run `git status`, edit the conflicting files, `git add` those files, and run
`git commit`. To cancel the pending merge instead, run `git merge --abort`.
After completing the merge, run `bundle` to export the combined history back to
the other computer. Never bundle an unfinished merge; both commands reject it.
Merge commits require your Git user name and email to be configured locally.

If an earlier import already fetched the bundle and then failed to fast-forward,
you can merge those fetched commits immediately with the original functions:

```bash
git merge --ff --no-edit refs/remotes/bundle/main
# After the merge succeeds (and any conflicts are resolved and committed):
bundle
```

Use your current branch name instead of `main` when applicable. Other branches
are available as `bundle/<branch>`; tags and
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

## Knowledge system feasibility gates

`knowledge-gates.py` collects JSON evidence using Python 3.9+ and the standard
library. Run inventory probes on the named Docker host, from this repository.
It does not change containers, install plugins, write notes, or retain memories.
The model probe sends synthetic English/Portuguese notes and consumes inference.

```bash
# Workstation: connectivity only. Exit 1 means blocked or failed.
python3 scripts/knowledge-gates.py network > /tmp/knowledge-network.json

# LXC 2: Hermes mounts, memory-file metadata, and vault sample hashes.
python3 scripts/knowledge-gates.py inventory --role hermes > /tmp/knowledge-hermes.json

# LXC 4: router inventory, then ufsc-vision through the actual LiteLLM gateway.
python3 scripts/knowledge-gates.py inventory --role router > /tmp/knowledge-router.json
python3 scripts/knowledge-gates.py model > /tmp/knowledge-model.json

# Optional comparison: six sequential requests total, two per model.
python3 scripts/knowledge-gates.py model --models ufsc-vision extraction writer > /tmp/knowledge-comparison.json

# LXC 12 and LXC 5, respectively.
python3 scripts/knowledge-gates.py inventory --role affine > /tmp/knowledge-affine-inventory.json
python3 scripts/knowledge-gates.py inventory --role data > /tmp/knowledge-data.json
```

The model probe streams its own source into the existing `sb_litellm` container,
using its existing `LITELLM_MASTER_KEY`. No credentials need to be copied to the
workstation or added to command arguments. Each request has a 120-second client
deadline; the shared alias retains its existing per-backend timeout. Output records
the returned model and deployment ID when available. Correlate router logs to
establish which backend/fallback actually answered; absent headers mean attribution
is unverified. The smoke test does not claim to validate Hindsight itself.

Probe version 2 also reports the actual `observed_output` for these synthetic
fixtures. In particular, `cloud_backup_status` must be `suggested`: a failed check
can mean `unknown`, an invalid enum, or `approved`, so inspect the value before
diagnosing an invented decision. The fixture, prompt, and acceptance criteria are
unchanged. Use `model --languages en` for a single-request diagnostic rerun.

The `deployments` command reads `/model/info` without running inference. It emits
only the selected alias, deployment ID, provider model, backend hostname, priority,
and timeout. It does not print API keys, headers, URL credentials, or query strings.
Match the returned ID to a smoke-test report; it identifies the responding route,
not any earlier failed attempts.

If your terminal can reach the lab but this agent session cannot, stream probes
over your existing SSH access without installing or copying files to the LXCs:

```bash
# From this repository on your workstation; adjust SSH user/host if needed.
ssh root@192.168.0.211 'python3 - inventory --role router' < scripts/knowledge-gates.py
ssh root@192.168.0.211 'docker exec -i sb_litellm python3 - model --inside-container' < scripts/knowledge-gates.py
ssh root@192.168.0.213 'python3 - inventory --role hermes' < scripts/knowledge-gates.py
ssh root@192.168.0.221 'python3 - inventory --role affine' < scripts/knowledge-gates.py
```

For the current UFSC pilot, these commands use the explicit personal SSH key:

```bash
# First map the existing report's deployment ID; no generation request.
ssh -o IdentitiesOnly=yes -i ~/.ssh/id_ed25519_personal root@192.168.0.211 \
  'docker exec -i sb_litellm python3 - deployments --inside-container' < scripts/knowledge-gates.py

# Then inspect one synthetic result with the original acceptance criteria.
ssh -o IdentitiesOnly=yes -i ~/.ssh/id_ed25519_personal root@192.168.0.211 \
  'docker exec -i sb_litellm python3 - model --inside-container --languages en' < scripts/knowledge-gates.py
```

For AFFiNE's read-only MCP probe, create a scoped credential through its normal
settings UI, and supply it through `AFFINE_MCP_TOKEN` in the invoking shell's
environment. Supply `AFFINE_WORKSPACE_ID` the same way. Do not put tokens in command
arguments, commit evidence reports, or paste `.env`/full Docker inspect output.

```bash
# On LXC 12; credentials are read from environment variables.
python3 scripts/knowledge-gates.py affine > /tmp/knowledge-affine-capabilities.json
# Optionally verify one selected source document. Only its hash/length is reported.
python3 scripts/knowledge-gates.py affine --doc-id DOCUMENT_ID > /tmp/knowledge-affine-read.json

# Offline safety and validation checks; no real inference or Docker access.
python3 -m unittest discover -s scripts -p 'test_knowledge_gates.py' -v
```

Reports distinguish **blocked**, **failed**, and **partial**. Exit 0 on a partial
result means the probe ran; it does not qualify a full gate. AFFiNE advertised write
tools do not prove working writes: create/update, human feedback, conflict handling,
and enumeration/change tracking still need a disposable-workspace test. Do not
switch to canary just to expose MCP writes.

The vault probe refuses to scan an underlying local directory when SSHFS is absent.
Its sample hashes still need comparison against the active notebook, especially
during the notebook/VM migration. It never modifies LiveSync or CouchDB. Snapshot
collection and freshness checks are subsequent G1 work, not implemented here.
