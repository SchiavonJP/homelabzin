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

The probe reports `observed_output` for the synthetic fixtures. Probe version 4
uses fixture version 2: suggestion existence (`cloud_backup_suggested: true`) and
owner approval (`cloud_backup_approval: not_approved`) are separate, explicitly
defined fields. Returning `unknown` still fails when the source explicitly states
the owner has not approved the suggestion. Source text is unchanged; the schema
and system instruction changed, so compare runs by fixture version and request
hash, not source hash alone. Use `model --languages en` for one request.

Structured failure reports survive a nonzero Docker child exit. Earlier host-side
wrappers could replace a model assertion failure with `command_failed`, hiding the
diagnostic. To bypass an older wrapper on LXC 4, run directly in the container:

```bash
docker exec -i sb_litellm python3 - model --inside-container --languages en < scripts/knowledge-gates.py
```

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

# Then inspect one synthetic result using the explicitly defined approval fields.
ssh -o IdentitiesOnly=yes -i ~/.ssh/id_ed25519_personal root@192.168.0.211 \
  'docker exec -i sb_litellm python3 - model --inside-container --languages en' < scripts/knowledge-gates.py
```

Pilot evidence supplied on 2026-11-03 mapped the responding deployment
`17bcca4edf04d9c3046145467ab1658de8a10a6b862d68c7f0f18a0eb48f3c9d`
to VLAB's `qwen3.8:27b`. Fixture version 1 passed seven of eight checks in both
languages. The inspected English output preserved the local-backup decision and
quoted the unapproved suggestion, but returned `cloud_backup_status: unknown`.
This prompted the separate proposal/approval fields in fixture version 2; it does
not qualify the revised smoke test or the full Hindsight gate as passed. Reported
request times were 90.499 seconds (English), 12.252 seconds (Portuguese), and
32.291 seconds (English diagnostic); the source of that variation is unverified.

At 21:04 UTC, probes run on `sb-litellm` reached Proxmox SSH, Hermes MCP,
LiteLLM, Postgres, AFFiNE, and Mini PC SSH. Notebook SSH at `100.80.3.58:22`
timed out; its power, VPN, and SSH state remain unverified. Router inventory
identified LiteLLM image digest
`sha256:89ccaccfda9083f7693777597ca27f8ffca12045e4fa9277155fb7c5f06e68b2`,
about 4 GiB free on the working filesystem, and about 1.6 GiB reported available
memory. A separate health check returned HTTP 200; the running process started
at 20:54 UTC and reported one restart. These qualify reachability and local
liveness subchecks, not full G0: source identity, other-host capacity, and backup
restoration still require evidence. Notebook failure keeps Obsidian snapshot
availability and freshness open under G1.

Subsequent server-side requests confirmed AFFiNE `0.27.4`, `Selfhosted`, initialized,
with `Comment`, `LocalWorkspace`, and `CopilotEmbedding` features; `Copilot` was
absent. That release guards its native MCP controller with `copilot.enabled` and
restricts advertised write tools to development/canary environments. At 21:11 UTC,
the live MCP initialization probe returned HTTP 403 with `Copilot is disabled.`
Native MCP fails the access gate as configured. AFFiNE can remain a source through
a separately verified adapter or explicit exports. The user subsequently selected
a manual AFFiNE import for the pilot while deferring continuous-sync repairs.
Released `0.27.4` source confirms an Obsidian-folder importer (with wiki-link and
folder handling) and a Markdown ZIP importer, independent of Copilot. Manual import
still needs a live check; it does not qualify automated read/write publishing.
Hermes `/health` reported `/vault`, `/skills`, and `/opt/data` present;
this establishes directory existence, not a mounted/readable vault or working MCP
session. `/mcp/` redirected to `/mcp`, `/mcp/mcp` returned 404, and POST `/mcp`
returned 405 with `Allow: GET`. A subsequent GET returned HTTP 200,
`Content-Type: text/event-stream`, and an `endpoint` event pointing to
`/mcp/messages/?session_id=...`, confirming SSE endpoint availability. Its OpenAPI
reports app version `1.0.0` and REST routes for vault listing/reading, search, and
user/session memory. This differs from the repository's version `2.0.0` server;
the deployed service needs inventory before any transport migration. Full MCP
initialization and actual source access remain unverified; the read-only REST
routes can establish source access independently.
Subsequent REST probes returned zero notes from `/vault/notes` and no string
`content` from `/memory/user` or `/memory/session`. G1 remains blocked for the
pilot corpus until the mount and real memory-file locations are inspected on
Hermes. This does not establish an empty original vault or absent agent memory:
the API may be looking at an unmounted directory or different storage paths.
Inventory from the actual `sb-hermes` host subsequently confirmed its LAN address
`192.168.0.213` and Tailscale address `100.81.255.52`. `findmnt -T
/mnt/obsidian-vault` resolved to the LXC root ext4 filesystem, not SSHFS. The MCP
container binds that local path to `/vault`, establishing the missing live mount
as a source-access blocker. The fstab source matches the documented notebook
`schiva@100.80.3.58:/home/schiva/Documentos/Obsidian Vault`; its mount unit timed
out at 10:44 UTC. A subsequent Tailscale ping from Hermes reached
`schiva-g77588` directly in 1 ms, making a retry of the existing mount the next
recovery step. MCP reads `root_hermes_data` at `/opt/data`, while the running
agent writes to the different `lxc_2_hermes_mcp_hermes_data` volume at that path.
This is a confirmed data-volume mismatch; actual memory-file locations still
need inspection before replacing the MCP container's mapping.
SilverBullet `192.168.0.12:3011` timed out from LiteLLM, leaving G4 open. Notebook
SSH timeout from LiteLLM does not establish notebook downtime: the documented
Tailscale participant for the vault mount is Hermes, not the LiteLLM host.

After an AFFiNE deployment passes the MCP feature gate, its read-only probe uses
a scoped credential from the normal settings UI through `AFFINE_MCP_TOKEN` in
the invoking shell's environment. Supply `AFFINE_WORKSPACE_ID` the same way.
The currently tested deployment fails that feature gate; no credential is needed
to establish its present restriction. Do not put tokens in command
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
collection and freshness remain separate G1 checks. Use the snapshot helper below
for collection; the inventory probe itself does not create snapshots.

## Persistent pilot copy and AFFiNE import

`knowledge-snapshot.py` creates a server-side Markdown copy and a ZIP for the
agreed pilot of up to 30 notes. It reads the host's vault directly, avoiding the
MCP container's stale bind mount and mismatched memory volume. It does not copy
Hermes memory until the correct memory location is verified.

Run on **sb-hermes**, from the repository root, after synchronizing the new script
into that checkout and while the existing notebook SSHFS mount is working:

```bash
python3 scripts/knowledge-snapshot.py \
  --source /mnt/obsidian-vault \
  --output /root/knowledge-pilot \
  --limit 30
```

From `LXC_2_hermes_mcp/`, the script path is `../scripts/knowledge-snapshot.py`.
An existing output directory is never overwritten; choose a different output path
for another capture. A missing or different SSHFS mount, empty source, changed
file, or exceeded import limit stops the export. `--source-kind directory` is an
explicit alternative for a separately verified local copy; it does not verify
that copy's freshness.

The result contains:

- `vault/`: original Markdown bytes and folder paths, plus a generated linked index.
- `affine-pilot.zip`: a transport archive containing that folder.
- `manifest.json`: source identity, capture times, selection counts, per-note hashes,
  source modification times, and the archive hash. The index is marked as derived.

Selection uses relative path order. Hidden/configuration directories, generated
`_AgentKnowledge` content, symlinks, and non-Markdown files are excluded. Notes with
uppercase Markdown extensions get a lowercase `.md` extension in the copy for the
importer; original filenames remain in the manifest. Case/Unicode path collisions
are rejected. Media/attachments are excluded from this first pilot, and links to
notes outside the selected sample may remain unresolved.

The browser importer in AFFiNE 0.27.4 allows at most 32 MiB total, 8 MiB per file,
1000 files, and 250 documents. The exporter includes its generated index in these
limits and allows at most 249 selected notes. Outputs are private to the invoking
user. The raw folder remains readable when the notebook goes offline.

On the computer running AFFiNE, retrieve `affine-pilot.zip` using your existing
SFTP/SCP access, extract it, choose **Import → Obsidian**, and select the extracted
`vault` folder. The ZIP is for transport; the Obsidian importer takes a folder.
Validate the imported note count (selected notes plus one index), folder layout,
Portuguese accents, a wiki link between two included notes, and source content.
This is an initial copy into AFFiNE, not an automatic synchronization or upsert:
re-importing can create duplicate pages. Use a dedicated pilot workspace/area.
Human changes in AFFiNE do not flow back to Obsidian through this workflow.

The server manifest starts with `affine_import_verified: false`; only an actual
successful import establishes that gate. Nightly source reads can use the server
copy once it is captured and verified. The notebook's connection is needed for
refreshing this copy until the independent source-sync layer is addressed.

```bash
python3 -m unittest discover -s scripts -p 'test_knowledge_snapshot.py' -v
```
