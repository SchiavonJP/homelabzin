# Hindsight knowledge pilot

> **Xereta integration:** the active source is SilverBullet's Nextcloud-backed `space/` vault on the Mini PC. Nextcloud Desktop on the notebook bridges it to Obsidian; CouchDB/LiveSync connects the Obsidian devices separately. See the [verified synchronization path and indexing repair](../../minipc/silverbullet/readme.md) and [Xereta deployment and gates](https://github.com/SchiavonJP/xereta/blob/main/README.md). The AFFiNE sections below describe the preserved earlier pilot.

This stack is an isolated acceptance environment on **sb-hermes / CT 107**.
It uses a separate `knowledge_pilot` PostgreSQL database on **sb-dados / CT 104**,
`ufsc-vision` through LiteLLM, and the existing multilingual BGE-M3 `embed` route.
Hermes's active memory provider and the existing MCP container remain unchanged.

The application is Hindsight **1.1.0-slim**, pinned by registry digest. API and UI
ports bind to the Hermes host's loopback interface. The 1 GiB memory limit, five
database connections, one concurrent LLM request, and explicit consolidation are
for bounded acceptance work. RRF ranking is the retrieval baseline; neural
reranking quality is not qualified by these checks.

## Continuous service policy

The accepted runtime now uses `restart: unless-stopped`, matching its Compose file. This changes restart behavior without upgrading Hindsight. A real restart preserved all 70 production bank documents and returned healthy with the database connected. Stop it explicitly for maintenance; normal Xereta ingestion depends on its availability. AFFiNE regular ingestion is documented in the [Xereta reader runbook](https://github.com/SchiavonJP/xereta/blob/main/ops/AFFINE.md); the isolated proof below records the earlier qualification boundary.

## AFFiNE isolated ingestion proof — 2026-11-08

The current Xereta source remains SilverBullet. A separate AFFiNE proof read
**Comandos**, **Ideas**, and **Agentics models** on version 0.27.4 and generated
two provisional findings and three questions with five validated citations.
No original note was edited, and no proposal was added to the live review queue
or published to AFFiNE. See the [sanitized evidence](evidence/2026-11-08-affine-proof.json).

Fresh Markdown matches the earlier independently export-verified captures.
A second capture preserved both binary snapshots and Markdown byte for byte;
rerunning kept three source versions, three documents, and seven operations,
without another model draft call. Invalid authentication produced three HTTP
403 incomplete captures; a separate test ledger retained all last good versions.
Imported Obsidian copies were not combined with SilverBullet as corroboration.

The reader now compares full Yjs block IDs when qualifying note containers and
empty surfaces. Imported IDs contain colons; retaining only their suffix caused
valid captures to be rejected. All 13 reader tests passed in the pinned AFFiNE
image, including a real Yjs empty/nonempty-canvas fixture. That fixture requires
`AFFINE_READER_REAL_YJS=1` and the image's `/app/package.json` dependencies; the
other 12 tests also pass locally. All 40 curator tests passed, including body-edit
versioning that preserves both archived captures.

Private artifacts are on CT 107 at
`/root/knowledge-affine-proof/20261108-76a987fcfc`, including `state/`, captures,
verification reports, and `affine-proof-preview.zip`. The isolated bank is
`knowledge-affine-proof-20261108-76a987fcfc`. The archive contains `Preview.md`
and its relative evidence links. The corrected `reader.cjs` is archived in that
proof directory on CT 106 and CT 107; the old standalone reader deployment was
not replaced. Its temporary container session copy was removed after testing.

Repeat processing of the existing captures directly on **sb-hermes**:

```bash
python3 /root/knowledge-curator-app/scripts/knowledge-curator.py \
  --state /root/knowledge-affine-proof/20261108-76a987fcfc/state \
  run --bank knowledge-affine-proof-20261108-76a987fcfc \
  --draft-engine gateway --limit 3 --seconds 1200
```

This command does not refresh AFFiNE. Fresh reads require the corrected reader
and private, origin-bound session on CT 106; expiry requires the existing login
helper. Automatic refresh, unattended transport, media/canvas understanding,
cross-source identity mapping, and the current Xereta source UI adapter remain
unqualified. No AFFiNE schedule is enabled. Xereta's source/review/configuration
records, all 19 generated review files, and its 70 production Hindsight documents
stayed unchanged; only the worker's normal heartbeat table advanced.

## Gate evidence

Evidence timestamps use UTC; the session crossed midnight in São Paulo.

| Check | Result | Boundary |
|---|---|---|
| Authenticated host access | Passed through the existing Proxmox SSH control connection | Direct workstation LAN access still fails in the agent session |
| Obsidian pilot identity | All 30 captured note hashes match the verified live notebook source | 30 of 101 notes; media excluded |
| Notebook-independent source | ZIP CRC, archive hash, index hash and every note hash pass | This is a persistent snapshot; refresh still needs the notebook |
| Pilot file restore | All 30 notes restored and verified on the Mac | Covers this pilot, not a full machine backup |
| Hermes transport | SSE initialization and tools/list succeed; 13 tools advertised | Existing MCP vault bind still lists zero notes |
| Hermes memory | Active volume has zero Markdown memories and zero SQLite sessions/messages | Older volume has 2 sessions and 5 messages; preserved, not ingested |
| AFFiNE | Three originals exported; five review and three evidence pages created through the signed-in editor; authenticated snapshot reading passes for qualified notes | Owner feedback round trip, unattended operation and automatic publishing remain gated; native MCP is disabled |
| SilverBullet alternative | Unreachable from Hermes on port 3011 | Human read/write capabilities remain unverified |
| PostgreSQL prerequisites | 17.10; pgvector 0.8.6 and pg_trgm available and tested in disposable databases | New pilot database has its own non-superuser owner |
| Database recovery tooling | Synthetic pg_dump/pg_restore round trip and vector query pass | No existing production database was restored or modified |
| Embeddings | English and Portuguese requests return finite 1024-dimensional vectors | Retrieval relevance still needs a corpus test |
| LLM smoke, fixture 3 | Nine assertions pass in each language; questions manually reviewed | English 12.829 s, Portuguese 13.533 s; warm-path smoke, not an availability guarantee |
| Hindsight operations, English | Retain, recall, graph and reflection semantics pass | Five facts from three documents; model-generated citation IDs fail validation |
| Document lifecycle | Create, replace and delete pass | Replacing a port removes the previous value; deletion removes source, facts, graph and recall results |
| Consolidation | Default policy fails; explicit policy passes English and Portuguese | Both 14 and 30 days remain visible and unresolved; limited to these fixtures |
| Hindsight database restore | All six checked tables match, including vectors | Restored into a disposable database as the pilot role; original database retained |
| Portuguese integration | Retain, consolidation and reflection pass all nine fixture assertions | Includes exact quotes from all three source documents and valid server provenance |
| Derived deletion and isolation | Deleting source-c removes its two facts and dependent observation | The other bank's identically named source remains intact; deleted memory endpoints return 404 |
| Restart persistence | Both banks preserve memories, graph state and all three policy missions | Checked after the deliberate English source-c deletion |
| Official Hindsight MCP | Disposable-bank initialization, allowlisted reads and denial of retain/update-bank pass | Remote authenticated access and individual agent configuration remain gated |
| Real-note pilot | Three source documents, ten extracted facts; explicit consolidation completes; unchanged reruns keep three documents and seven operations | The bounded model draft passed citations but needed editorial correction for unsupported interpretations |
| Live AFFiNE readback | Source text matches native exports; generated index/evidence links and stable answer headings read back; invalid session returns incomplete 403 captures | Note layout and independently empty canvas warnings are explicitly qualified; other unsupported content still fails closed |
| Agent integration and nightly digest | Pending | Do not enable ingestion hooks or schedules before acceptance |

The pilot is running and healthy on Hermes. Synthetic acceptance preceded the
separate three-note AFFiNE bank described below. The synthetic database backup restores all 13 remaining memory rows,
1024-dimensional vectors, graph records and bank policies into an isolated
database as the pilot role; checked row digests match. Its off-host copy was
checksum-verified. Durable recurring backups and recovery for the full homelab
remain separate work.

English bank `knowledge-gate-en-20261105-f0441d58` intentionally lacks source-c
after the forgetting test. Portuguese bank `knowledge-gate-pt-86c4fe58c7` keeps
the complete three-document fixture for inspection. The CRUD test bank is empty.

The exact successful model report is in
[evidence/2026-11-05-model-smoke.json](evidence/2026-11-05-model-smoke.json).
`language_review_required` remains true because the runner does not implement a
language detector. Both questions in this report were reviewed and match their
requested languages. A prior diagnostic produced a German question for the
English fixture despite passing the original automatic assertions; fixture 3
therefore names the required output language explicitly.

## LiteLLM compatibility

Baseline `ufsc-vision` English requests timed out twice (HTTP 408). Passing
`reasoning_effort=none` alone was rejected by LiteLLM (HTTP 400). A request-specific
`allowed_openai_params: [reasoning_effort]` allows that setting to reach Ollama.
The successful fixture uses both settings. The responding deployment ID maps to
VLAB's `qwen3.8:27b`; this does not establish any preceding fallback attempts.

Reproduce on **sb-litellm / CT 105**, with the current repository script:

```bash
docker exec -i sb_litellm python3 - model --inside-container \
  --languages en pt --reasoning-effort none < scripts/knowledge-gates.py
```

The Hindsight client uses the same reasoning setting and allowlist in
`HINDSIGHT_API_LLM_EXTRA_BODY`. Real retain calls also need a request-specific
backend timeout: the first retain failed at the existing 50-second route limit.
The pilot requests 120 seconds per backend call with a 150-second client deadline.
The installed router gives the request's `timeout` precedence over deployment
defaults. The shared router configuration is unchanged.

Do not set `HINDSIGHT_API_EMBEDDINGS_OPENAI_DIMENSIONS` for this BGE route: it asks
LiteLLM to send an unsupported dimensions override and makes retain fail. Hindsight
autodetects the verified 1024 dimensions by probing the `embed` alias at startup.
The existing `local-fast` alias was also compared: both structured-output
requests returned HTTP 500, so it was not selected as a replacement.

## Run the isolated stack

Runtime directory: `/root/knowledge-hindsight-pilot` on Hermes. The private `.env`
contains the separate database login and existing gateway credential. It is mode
0600 and must remain outside Git and evidence reports. The repository's
`.env.example` contains placeholders only.

```bash
cd /root/knowledge-hindsight-pilot
docker compose config --quiet
docker compose up -d --pull never
docker compose ps
curl --fail --max-time 10 http://127.0.0.1:8888/health
```

Use an isolated bank named `knowledge-gate-*` for synthetic Cedar/Cedro documents
first. Verify explicit decisions, unapproved proposals, source attribution and
conflicts through actual retain/recall/reflect. Test document replacement,
deletion, graph links, on-demand consolidation, process restart and a database
backup/restore before creating the real 30-note bank. Synthetic gate documents
must not be mixed into the real corpus.

Stopping the test instance preserves its PostgreSQL data:

```bash
cd /root/knowledge-hindsight-pilot
docker compose stop
```

The stack deliberately has no automatic restart or recurring ingestion until
acceptance. Do not remove either existing Hermes volume, switch the existing
memory provider, upgrade the legacy MCP server, or change LiveSync as part of
this pilot.

## Consolidation and provenance gates

The default consolidation run produced **“Project Cedar keeps snapshots for
14 days”** with both the 14-day and conflicting 30-day facts listed as evidence.
That fails this system's conflict-preservation requirement. Clearing only the
synthetic bank's observations and rebuilding with
[bank-policy.json](bank-policy.json) produced an observation containing **both
14 and 30 days**, explicitly marked unresolved. The policy contains no fixture
values: it requires preserving contradictory claims without using ingestion order
as authority. The raw source documents and five facts stayed intact throughout.
Automatic consolidation remains off during qualification.

The reflection answer preserved the owner decision and unapproved proposal, but
its generated `supporting_memory_ids` contained document names instead of memory
UUIDs and omitted the third document. Those generated strings fail validation.
The server's `based_on.memories` metadata contains valid IDs for all three source
documents, and expanded raw chunks match the original fixtures. A publishing
adapter must validate references and literal quotes against original source
versions; it must not trust model-authored IDs. The curator below implements
these checks; literal quotation validation alone does not prove a model's
interpretation, so findings remain reviewable proposals.
The Portuguese retest used the original grounded-quote response schema instead:
all nine assertions passed after consolidation, including exact original quotes
and coverage of source IDs a, b and c. The actual curation adapter must perform
equivalent checks on real source manifests before publishing.

`proof_count` counts supporting **facts**, not independent documents: two facts
from source-c yield a proof count of two while representing one source. Count
distinct original documents when presenting corroboration. Graph entity labels
also require review; one extraction labels Cedar as an owner. The graph checks
establish stored links, not perfect entity classification. Likewise, a
`world`/`experience` classification does not establish owner authority.

The first 30-note snapshot contains 707,651 Markdown bytes; one note is 526,901
bytes. A real ingestion pilot should start with a few small notes and explicitly
queue the large note for bounded chunk processing. It must not silently truncate
that note or treat an unfinished capture as completely digested.

The exact synthetic inputs used for retain are in
[fixtures/retention-en.json](fixtures/retention-en.json) and
[fixtures/retention-pt.json](fixtures/retention-pt.json). To replay on Hermes after
copying the runbook assets into its runtime directory, choose a fresh test bank:

```bash
knowledge_probe_bank="knowledge-gate-manual-$(date +%s)"
curl --fail --max-time 20 -X PUT --json @bank-policy.json \
  "http://127.0.0.1:8888/v1/default/banks/$knowledge_probe_bank"
curl --fail --max-time 240 --json @fixtures/retention-en.json \
  "http://127.0.0.1:8888/v1/default/banks/$knowledge_probe_bank/memories"
curl --fail --max-time 20 \
  "http://127.0.0.1:8888/v1/default/banks/$knowledge_probe_bank/memories/list?limit=50"
```

Validate completion from operation responses and actual documents/memories.
Immediately after retain, `/stats` returned cached zero counts while the list,
graph and recall already contained the five facts. Statistics subsequently caught
up; they are not a commit or digestion-completion signal.

## Authoritative sources and curator

**AFFiNE is the authoritative editing location**, as selected by the owner.
Obsidian, its notebook mount and the previous 30-note snapshot are backups.
An imported mirror is an alias of an original, never extra corroboration.
The older snapshot's import flag describes that archive only, not the current
self-hosted workspace; do not infer a 31-document count for the full import.

The curator is independent of Hermes. Its CLI lives in
[`scripts/knowledge-curator.py`](../../scripts/knowledge-curator.py), deployed
under `/root/knowledge-curator-app` on **sb-hermes**. Private state is under
`/root/knowledge-curator`, outside Git. Source exports are under
`/root/knowledge-curator-input`. Fresh native exports of **Comandos**, **Ideas**
and **Agentics models** are the initial corpus in `knowledge-affine-pilot`.

Each original has a stable server/workspace/document identity and a hash of its
title and LF-normalized Markdown. Raw exports and raw hashes are retained.
Captures are not event dates. Generated pages are excluded; exact duplicate
imports require explicit alias registration. Unchanged versions are skipped.
Changed versions replace the active Hindsight document while keeping archives.
The small-note processing limit is 24,000 characters; larger notes stay pending
without truncation until a separate bounded-chunk gate is implemented.

Run directly on **sb-hermes**, not the LiteLLM machine:

```bash
cd /root/knowledge-curator-app
python3 scripts/knowledge-curator.py status
python3 scripts/knowledge-curator.py run --dry-run
python3 scripts/knowledge-curator.py run
```

`run` processes up to three source versions, with a 20-minute budget. It journals
client operation UUIDs before async submission, reconciles acknowledgements,
checks document text and version metadata after completion, then explicitly
consolidates under the tested policy. A missing consolidation acknowledgement
requires operation reconciliation; it is not blindly submitted again. A file
lock prevents overlap while `status` remains readable. Failed operations are
held for inspection; HTTP errors never include provider bodies or credentials.

The real-note multi-step Hindsight reflection gate encountered an upstream
connection failure during a LiteLLM restart, a client timeout, and an upstream
504 after increasing its deadline. It remains unqualified for unattended review.
The default draft engine therefore makes **one `ufsc-vision` request** over
source captures whose documents and raw memory provenance were independently
verified in Hindsight. Citation validation is identical for both engines.
`--draft-engine hindsight` retains the multi-step path for further qualification.
The bounded gateway engine reads `LITELLM_API_KEY` or the existing private runtime
file specified by `--gateway-env`; it never saves that credential in the ledger.

The output is a private, versioned proposal directory with **Knowledge Index**,
**Pending Digest**, **Open Questions**, **Decisions**, **Recent Changes**, and
versioned **Evidence** pages. English prose retains original-language quotations.
Every finding's source ID must be present in server-resolved Hindsight memory
provenance, and each quotation must match the archived version exactly. Invalid
results are held rather than published. Decisions extracted by the model are
labelled source-reported and require review before action. No original is rewritten.

The first model draft speculated beyond the sources about unfamiliar tool names
and music licensing. Editorial review replaced those interpretations with three
neutral summaries and two questions about deployment status and intended agent
use. `edit-review --file PRIVATE_JSON` revalidates edited candidates against
current captures and Hindsight provenance. Superseded unanswered draft questions
are **withdrawn**, not resolved; answered questions and owner text survive.
The accepted editorial review is reused until its source versions change.

## Manual review and owner feedback

The initial review pages are already created with `_AgentKnowledge / …` titles
in the self-hosted workspace. Source/evidence links were read back from the
server. `bind-review --file PRIVATE_JSON` records their stable page URLs and the
designated feedback page in the private ledger. Do not reimport the prepared ZIP
over this pilot: import is not an upsert. Subsequent outputs are proposals for
generated sections in these existing pages. Preserve **Human notes**.

On **Open Questions**, write under `### Answer q-…`. Leave the corresponding
`### Disposition q-…` as `tentative` unless confirming the answer; use `confirmed`
to resolve a factual question and `decision-approved` only for an explicit owner
decision. Preserve those headings and `### End q-…` when editing/exporting.
Do not use an agent's response as an owner answer. Initial questions are capped
at three unresolved items and retain stable issue IDs.

Export the edited page as Markdown and copy it to Hermes, then run:

```bash
python3 scripts/knowledge-curator.py feedback \
  --page-url 'https://affine.joaopaulo.me/workspace/WORKSPACE/DOCUMENT' \
  --file /root/knowledge-curator-input/answered-questions.md
python3 scripts/knowledge-curator.py run
```

Only recognized answer sections become a separate feedback source. The entire
edited export is archived; generated text and unrelated notes are not ingested.
Repeated answers are idempotent. Tentative answers move to **answered**; explicit
confirmation moves to **resolved**. Confirming a fact does not approve an action.
Apply proposed generated-section changes manually and export again to verify
that owner answers and unrelated edits survived. This live owner round trip is
a required gate before changing Hermes's production provider.

## Official MCP and Hermes

Use **Hindsight's built-in MCP**, not a new custom memory MCP. The shared bank
exposes recall/reflect and document/memory/operation reads only. The operator's
local REST API remains available to the curator. Tool-list filtering and actual
denial of `retain` and `update_bank` are tested by
[`knowledge-mcp-gate.py`](../../scripts/knowledge-mcp-gate.py) in a disposable
synthetic bank. Keep the deployment on loopback until remote authenticated
access is qualified; a bank URL is not an authorization boundary by itself.

The inspected Hermes image is
`nousresearch/hermes-agent@sha256:24085416ae93204f29d3a01eae226e615fe989e8a0a1529fce5c4bc1eb42dc1c`,
with `hindsight-client` 0.6.1 and MCP 1.26.0. It has a **single-bank** contract; it does not implement
`recall_additional_banks`. Keep its native provider on `hermes-experience-pilot`
and configure the official read-only shared MCP separately. Explicitly include
`observation`, `world`, and `experience` in recall types. Do not silently set an
unsupported config key, write experiences into the canonical bank, backfill
history, or remove either legacy volume. Preserve image/config/volume rollback
before switching; start auto-retain off and prove two-session retrieval plus an
explicit experience write before enabling new-turn retention.
The staged [provider configuration](hermes-provider.example.json) is not applied
to the running agent. Its container service URL requires an explicitly tested
private Docker network connection first; host loopback is not container localhost.
No unsupported `retain_cron` setting is added to this provider version.

## Live reader, recovery and scheduling gates

[`knowledge-affine-reader.cjs`](../../scripts/knowledge-affine-reader.cjs)
runs inside AFFiNE's pinned image with the matching native decoder. It accepts
a private JSON allowlist of one to three document IDs, `AFFINE_AUTH_FILE`,
`AFFINE_TOKEN` or `AFFINE_COOKIE`, and a private output directory. It reads
authenticated binary snapshots, archives them, and emits Markdown plus checksums.
It refuses version drift from 0.27.4. Unsupported blocks, failed authentication,
or unavailable documents produce incomplete captures, never inferred deletion.
The authenticated reader now passes for the three originals and the generated
feedback/index/test pages. Original text was compared with native exports,
accounting for the separate title, URL punctuation escaping, heading whitespace
and equivalent nested-list indentation; fenced code stays exact.

The codec flags `affine:note` layout even when it preserves the text children.
Only export-compared documents opt into `acceptNoteContainer`. Generated pages
also have a surface: `acceptEmptySurface` accepts it only after independently
decoding Yjs and proving there are no canvas elements or child blocks. Original
warnings remain in the manifest. Unknown content and non-empty canvases are
never waived. Media/diagram understanding is not qualified by this text gate.

[`knowledge-affine-login.py`](../../scripts/knowledge-affine-login.py) uses the
normal password sign-in and session endpoints, saves a mode-0600 cookie file and
never saves the password. A session is provisioned privately on CT 106. The
reader's auth file must match its origin and be inaccessible to other users.
Invalid-cookie testing returns incomplete 403 captures. Reauthenticate with a
new private file when the session expires; automatic refresh is not implemented.
Reader evidence is archived outside Git at `/root/knowledge-reader-evidence` on
CT 106. No service credential is copied to the workstation or repository.

```bash
# Inside the AFFiNE container, with credentials supplied privately:
node /private/path/knowledge-affine-reader.cjs /private/path/allowlist.json /private/path/captures
# Transfer the capture batch to Hermes, then:
python3 scripts/knowledge-curator.py register-batch --manifest /private/path/captures/BATCH/manifest.json
```

`register-batch` validates Markdown checksums and filenames. Incomplete captures
keep the last good version and appear in **Pending Digest**. They block a new
digest from being presented as current. No unattended reader or timer is enabled.

Initial editor create/paste and server readback passed. A click-and-type update
on a disposable page preserved a separate Human notes paragraph. Direct
contenteditable `fill` did not reliably target BlockSuite's active selection;
do not use it for publishing. A fully automated merge/concurrent-edit adapter
and the real owner-answer round trip remain separate gates.

```bash
python3 scripts/knowledge-curator.py backup
python3 scripts/knowledge-curator.py verify-backup \
  --archive /private/path/curator.tar.gz --manifest /private/path/manifest.json \
  --output /private/path/new-restore-directory
```

The curator backup includes the ledger, captures, feedback, raw responses and
review proposals, with file checksums and a verified SQLite copy. Hindsight's
database needs its own backup. Verify both restoration and an off-host copy.
On 2026-11-05 the three-note ledger archive restored successfully and its Mac
copy matched SHA-256. A subsequent Hindsight dump (including the real-note bank)
restored into `knowledge_curator_restore_20261105` as `knowledge_pilot`; all six
checked content-table row digests matched. Precreate `vector` and `pg_trgm` in a
new disposable restore database using its administrator, then use
`pg_restore --no-owner --no-privileges --no-comments --exit-on-error` as the pilot
role. These are acceptance backups; recurring backups remain gated.

Only after the manual feedback cycle, Hermes integration, authenticated live
reader and recovery gates pass: install a **02:30 America/Sao_Paulo** timer,
one run at a time, at most one catch-up run, three source versions, three open
questions, one concurrent model request, and a 20-minute foreground budget.
Verify notebook-offline operation and interruption recovery before activation.
Automatic publishing remains a separate disposable-page gate (create/update/
readback/answer capture/concurrent-edit preservation); manual publishing can
continue after nightly processing is qualified.

Offline checks:

```bash
python3 -m unittest discover -s scripts -p 'test_knowledge_*.py'
node --test scripts/test_knowledge_affine_reader.cjs
```

Sources for the deployment configuration:

- [Release 1.1.0](https://github.com/vectorize-io/hindsight/releases/tag/v1.1.0)
- [Pinned configuration source](https://github.com/vectorize-io/hindsight/blob/a5a619b5ca59c5c39e0f96be6f7a31fabd136bd5/hindsight-api-slim/hindsight_api/config.py)
- [External PostgreSQL example](https://github.com/vectorize-io/hindsight/blob/v1.1.0/docker/docker-compose/external-pg/docker-compose.yaml)
