# Xereta

Xereta is the Portuguese review application and agent gateway for the shared Obsidian / SilverBullet vault and read-only AFFiNE sources. Answer and review in the frontend. The vault contains one file per question or knowledge item, plus a small linked index. SilverBullet mounts Nextcloud's local vault directory; Nextcloud Desktop on the notebook bridges it to Obsidian. CouchDB / LiveSync separately connects Obsidian devices. See the [verified mounts and indexing repair](../../minipc/silverbullet/readme.md). The notebook's client must be running to deliver changes between these two synchronization systems.

Hindsight 1.1.0 handles extraction, retention and consolidation. Xereta owns bounded jobs, questions, owner feedback, publication, review and scheduling. Hindsight is not the nightly workflow scheduler.

## Reference library release — 2026-11-09

Version `0.6.0` adds **Referências** for saved links, reading status, tags, projects and reviewed relationship suggestions. **Fontes → Integrações** manages library/journal folders, topic vocabulary, Karakeep lists and portable configuration JSON. Runtime credentials stay on the server. See the [library operator runbook](ops/LIBRARY.md).

Saving or marking a reference as read does not authorize digestion. Review the captured version and explicitly authorize its hash, or use the dedicated private Karakeep readiness list. New library organization and ingestion start paused. Existing SilverBullet/AFFiNE approvals, Automatic mode, the 03:00 São Paulo schedule and the ten-version/twenty-minute daily budget were preserved.

Xereta and its dedicated Hindsight instance now use LiteLLM `generalist`; embeddings remain `embed`. Qualification passed 135 backend tests, 15 real PostgreSQL recovery/concurrency checks, 11 browser tests and a real isolated Hindsight canary. The canary retained only the authorized reference, verified grounded quotations and created no duplicate work on rerun. The live schema migration preserved nineteen original table projections and 42 protected source/review files.

The production ReadItLater preview contains 72 notes: 50 suggested reading-queue items and 22 references. A three-repository pilot created native reference notes, preserved all 72 originals and passed a duplicate-free rerun without authorizing digestion. The remaining migration awaits classification and the Karakeep API token. Original Markdown and assets remain in place. Native link targets were checked programmatically; navigation and backlinks in the owner's editors remain a human verification step. See [release evidence](evidence/2026-11-09-library-release.json).

## Review workflow

1. Open **Perguntas → A responder**. Consult the source/version, write an answer, and select **Salvar resposta**.
2. Use **Esta resposta registra uma decisão explícita minha** only when the answer is an explicit decision. An ordinary save confirms information. **Salvar rascunho** and **Adiar** remain available.
3. Find completed replies under **Respondidas** and edit them there. Unsaved drafts stay in the current browser tab; revision conflicts preserve them for review.
4. The worker updates the corresponding note automatically when it is free. This publication does not invoke an LLM. A later digest incorporates the response into Hindsight.
5. If you prefer the vault, edit the response in its individual note and use the Markdown checkboxes. Select **Atualizar notas** in Xereta, or run a digest, to collect those edits.

```text
space/_AgentKnowledge/
├── Index.md                         # links and status only
├── Perguntas/<issue>-<id>.md         # one question, response, sources and checkboxes
├── Conhecimento/<title>-<id>.md      # one finding or reported decision
├── Sync/obsidian-<id>.md             # dedicated checkbox sync test
└── Inbox.md                         # preserved history; no longer updated
```

No `Minhas notas` block, copied phrase, or hand-edited confirmation enum is required. The frontend is the primary review interface; the Markdown notes are optional editable views.

Each file has its own ETag journal and conflict boundary. A changed context is held instead of overwritten, while other files continue to publish. Answers, citations, source versions and existing human annotations are preserved. The migration archives a private copy of the old Inbox under `/data/legacy-review`; its original file remains intact. An unparsed old edit is flagged for review rather than discarded.

## Automatic mode

Open **Fontes**, choose **Processar pastas automaticamente**, select folders and optional exclusions, then **Conferir escopo** and **Aprovar e salvar configuração**. Preview reads metadata only. Folder approval includes subfolders and future notes. Exclusions are literal full paths; end folders with `/`. Mandatory generated/configuration/conflict exclusions always apply.

Saving leaves intake paused. **Ativar agora** starts one bounded run; later runs use the existing Agenda schedule, currently 03:00 America/Sao_Paulo. **Pausar automático** saves the current checkpoint before stopping. **Retomar agora** starts immediately with the remaining daily allowance. Answers and generated review-file synchronization continue while intake is paused. Switch back to manual selection to use the previous saved batch.

The initial allowance is ten distinct original note-version attempts and twenty minutes per local calendar day, shared by scheduled runs, Digerir agora, retries, and resume. Limits can be lowered in Fontes; configuration changes do not erase daily usage. An in-flight service request can finish after the checkpoint deadline; no additional processing request starts after it. Paused time is excluded. A crashed running job keeps its original deadline, including downtime. Completion and the final usage charge commit atomically.

The worker discovers files using SilverBullet metadata, verifies content hashes before ingestion, and audits unchanged metadata weekly within the same budget. It reads only approved folders. A file-specific error remains visible with backoff while other notes continue; missing files retain their captured history. Scope changes stop future reads and keep previous memories/citations. The notebook can remain offline: processing uses the versions available on the server, independently of desktop synchronization.

Long notes retain their full immutable capture and are processed in deterministic sections of at most 12,000 characters, with exact original offsets and versioned Hindsight document IDs. Every quotation is verified against the actual section and mapped back to the original note/version. Sections do not count as independent sources. The existing eight-MiB capture limit remains an explicit exception, with no silent truncation. Review prompts use at most three sections plus 12,000 characters of relevant owner feedback; overflow feedback has its own durable section work.

Progress separates unread, changed, partial, processed, excluded, missing and failed notes. **Processed** means every section has completed retention and saved review output; human confirmation and successful publication are separate. Original notes are never edited. Failed conditional writes preserve human edits. Excess questions remain queued and are promoted without an LLM call as active questions are resolved/deferred; at most three stay active, and unanswered reviews never stop intake. Review lists are paginated.

Automatic mode is **off by default after migration**, with no approved folders. The existing manual batch and schedule are preserved until the owner changes mode. Runtime acceptance gates still apply. There is no automatic vault-wide approval.

Owner-only endpoints are `/api/v1/xereta/automation` (GET/PUT), `/automation/preview` (POST), `/automation/pause` and `/automation/resume` (POST), `/automation/queue` (GET), and `/review-queue` (GET). Saves and controls use optimistic revisions; resume also accepts an idempotency key. Existing run requests and MCP status remain compatible. Mutations never use GET.

## AFFiNE alongside SilverBullet

Version 0.5.0 adds a read-only AFFiNE connection. In **Fontes**, choose an available AFFiNE workspace, preview the scope and exclusions, and explicitly approve/save it. Approval includes future documents in that workspace. Saving leaves its automatic scope paused; activate it separately. No migration approves or activates AFFiNE. Existing SilverBullet folders, schedule and daily usage are preserved.

Both providers share the existing ten document-version attempts and twenty minutes per day. Selection alternates providers when both have eligible work. Each connection shows health and progress. An unavailable provider does not block the other; authentication failures require reconnecting the reader. Pause stops new processing at the next checkpoint; an in-flight service request can finish. Manual explicit selections remain independent of automatic scope pause.

Documents keep provider/workspace/document identities, original links and immutable title/body versions. AFFiNE also archives its binary snapshot. Renaming a document retains its identity. Incomplete inventory scans resume without marking unseen documents missing. Empty or unsupported captures are visible errors, without silent truncation.

Verified imports and exact copies share an evidence family. Similar titles suggest a possible relationship; suspected copies are counted conservatively until the owner separates them. Divergent content remains preserved. Relationships can be linked or separated in Fontes; reused extraction keeps its original provenance. Generated reviews are excluded. Findings and questions continue to be reviewed in Xereta and the existing vault files; AFFiNE source documents are never changed.

Reader deployment, session renewal and rollback are documented in the [AFFiNE operator runbook](ops/AFFINE.md). The account/session and separate reader bearer key stay on the servers; frontend responses contain neither.

## Choose the next batch

Open **Fontes** to search the SilverBullet catalogue. Listing reads metadata only. Remove a selected note before selecting a fourth; choose one to three notes, then **Aprovar e salvar lote**. Saving explicitly approves those notes for processing but does not enqueue a run. Click **Digerir agora** or leave them for the existing nightly schedule. Notes must be available, nonempty, eligible, and at most 24,000 characters.

The same saved batch serves manual and scheduled digests and stays selected until the owner changes it. There is no automatic rotation through the vault. Approval and ingestion history remain separate from the active batch. Old memories, immutable source versions, answers and reviews stay available; citations outside the current batch are labeled as last captured snapshots. Owner feedback remains part of each digest. Original notes outside the selected batch are not re-captured or added to the review prompt.

Batch changes use a revision check and the same PostgreSQL transaction lock as run enqueue. A queued or running digest prevents a change; a stale browser keeps its selection and asks the owner to reload. The read-only agent token cannot list the full catalogue or approve notes. The owner-only REST routes are `GET /api/v1/xereta/source-catalog` and `PUT /api/v1/xereta/source-selection`.

Manual and retry buttons use `crypto.getRandomValues` for request keys, which works on the LAN HTTP interface. They do not require `crypto.randomUUID`, which browsers restrict to secure contexts.

## Verify synchronization through the frontend

Open **Agenda → Obsidian e SilverBullet** and create a sync test. The app creates a dedicated note with two checkboxes:

1. In **Obsidian**, mark **Vi esta nota no Obsidian**, then click **Verificar sincronização** in Xereta.
2. Xereta writes a dated return message to the same note. After it appears in **Obsidian**, mark **Recebi a confirmação do Xereta no Obsidian**, then verify again.

The return checkbox cannot pass before the first step and server reply. The app observes file changes; which editor was used is attested by the owner following these instructions. Synthetic unit tests do not qualify the actual Obsidian roundtrip. The test note and all generated review files are excluded from knowledge evidence.

## Deployment

- Host: `sb-hermes`, Proxmox CT107 / `192.168.0.213`.
- LAN UI: <http://192.168.0.213:3101/>.
- Planned public UI: `https://xereta.joaopaulo.me` (DNS/tunnel gate pending).
- Checkout: `/root/xereta-app`; private runtime: `/root/xereta`.
- Containers: `sb_xereta`, `sb_xereta_worker`; Compose project `xereta`, image `xereta:0.5.0`.
- PostgreSQL: existing CT104, isolated database `knowledge_curator`, role `xereta`. The database keeps its pilot name.
- Hindsight bank: `knowledge-vault-pilot`; AFFiNE's old bank/state remain separate.
- Captures and private migration snapshots: persistent `xereta_xereta_state` volume.
- Health: `/health/live`, `/health/ready` (worker heartbeat required).

Host networking reuses Hindsight's accepted loopback endpoint. Existing Hermes, MCP, Hindsight, LiveSync, and CouchDB services are not replaced. Compose is the deployment path; Dokploy can adopt it later.

```sh
cd /root/xereta-app
docker compose build
docker compose up -d --no-build app worker
docker exec sb_xereta python -m app.cli status
docker exec sb_xereta python -m app.cli run
```

Owner credentials are in `/root/xereta/owner-login.json` (0600); runtime secrets are in `/root/xereta/.env` (0600), outside the checkout. Read them privately on the server. Change the password with `docker exec -it sb_xereta python -m app.cli set-password`; the bootstrap login file is not updated by that command. Login is required for knowledge APIs. There is no public signup.

## Source and authority rules

- Manual batches contain up to three approved notes. Automatic intake reads only approved provider scopes, within the shared daily budget.
- A source has a stable ID, SHA256 version, immutable captured body and timestamp. Missing or renamed notes are held for reconciliation.
- Generated files, executable configuration, hidden paths, libraries and sync conflicts are excluded. AFFiNE copies are not additional evidence.
- Quotations must be literal and identify a verified Hindsight source/version. Summaries are Portuguese; quotations retain their original language.
- At most three useful open questions. Contradictions remain unresolved without an explicit resolution in evidence.
- Canonical API dispositions are `tentative`, `confirmed`, `decision-approved`, `deferred`. Checkbox inputs are validated server-side. A checked confirmation without an answer is rejected.
- Owner responses have their own source/version and invalidate the review cache. Superseded responses remain in history. Revising an answer back to previous wording safely reselects and re-retains that version when needed.
- Identical claim text and kind with current evidence reuse the existing reviewed record. Duplicate unreviewed proposals are retained as history with a link to the canonical item; owner reviews and stale/conflicting evidence are preserved. This is exact-text deduplication, not semantic merging.
- Reruns reuse operations and drafts. Unknown remote acknowledgements stop for reconciliation. Explicit retry allocates new operation IDs only for known terminal failures.
- Individual note writes use `If-Match`, or `If-None-Match: *` on creation, and verify readback. A pending write can be reconciled after interruption. Raw MCP file writes are disabled; use the structured review actions.

## Scheduling and recovery

The small nightly pilot is enabled at **03:00 America/Sao_Paulo**, starting **2026-11-07**. Both `XERETA_ACCEPTANCE_PASSED=true` and the owner-controlled schedule are enabled. Publication has its own `XERETA_PUBLISH_ENABLED` gate. The browser cannot override the runtime gates. Publishing replies through the outbox is separate from scheduling AI digests. Use **Agenda** to pause future scheduled jobs.

One worker holds a PostgreSQL advisory lock. Jobs, operations, review journals and the publication outbox persist across restarts. A replacement re-enters the pipeline and reuses persisted operation IDs, cached reviews and publication journals. Concurrent saves retain a pending outbox generation for another pass. Daily jobs use `America/Sao_Paulo` and catch up only the latest due slot. The pilot uses three notes and a twenty-minute checkpoint budget measured from its original persisted start, including downtime, with separate call timeouts.

Before nightly use, qualify the small-note run/rerun, real owner response, conditional writes, actual Obsidian roundtrip, notebook-offline server operation, interrupted-run recovery, database restores and authenticated MCP permissions. Never simulate an owner answer or Obsidian checkbox to pass a human-dependent gate.

Recovery qualification passed for `0.2.3`: eleven PostgreSQL cases with actual process deaths, a real Hindsight canary in a disposable bank, and an unchanged queued job surviving the deployed worker restart. A new note journaled before its first PUT can now be created conditionally after a crash; an already published note that disappears remains held for reconciliation. Unknown consolidation acknowledgements stop without blind resubmission. See the [operator recovery runbook](ops/RECOVERY.md) and [recorded evidence](evidence/2026-11-06-recovery.json). Synthetic fixtures are confined to test state and never count as owner approvals or production knowledge. Qualification kept scheduling disabled; the subsequent pilot activation is recorded below.

## Agent access

Use `http://192.168.0.213:3101/mcp/` and a private `Authorization: Bearer <XERETA_AGENT_READ_TOKEN>` configuration for reads. Run/answer actions require a current owner session. Tools include `xereta_status`, `xereta_request_run`, `xereta_answer_question` and vault/skills/legacy-memory reads. The old `:3100/mcp` SSE service and active Hermes provider remain unchanged pending compatibility qualification.

REST routes are `/api/v1/xereta/*`, with transitional `/api/v1/curator/*` aliases. New owner-only actions include `/review/sync`, `/sync-check` and `/sync-check/{id}/verify`. None use GET for mutation.

## Verification and history

Docker builds run backend tests, generate OpenAPI types, typecheck and build the frontend. Python and Bun dependencies and base image digests are pinned. See [UPSTREAM.md](UPSTREAM.md) for the template revision and attribution.

```sh
docker exec -i sb_xereta python - < ops/review_files_gate.py
docker exec -i sb_xereta python - < ops/mcp_gate.py
docker exec -i sb_xereta python - < ops/rerun_gate.py
```

[Evidence](evidence/) records the original three-note pilot, real owner response, restores, and the per-item migration. The updated release passed 34 backend tests, the production frontend build, browser review checks and the unchanged rerun. The migration preserves two questions, two findings and the existing owner response; five independent review files replace the single-file view. The legacy `feedback_gate.py` baseline/report describes the earlier owner-feedback qualification; new publication checks use `review_files_gate.py`.

## Backup and rollback

Before the file-layout migration, `ops/backup_hindsight.py --database knowledge_curator` restored all existing application tables into a fresh database and compared row digests. After migration, all 14 application tables were restored and compared again, and the off-host dump checksum matched. The same script supports `knowledge_pilot`. Retain encrypted/off-host dumps and the capture volume before unattended use.

The old code archive is `/root/xereta/rollback/code-before-review-files.tgz`, and the old image is tagged `xereta:before-review-files`. Migration `0002` adds review journals without dropping original tables. Do not blindly start the old image against a newer Alembic revision: restore the verified pre-migration database into a fresh database and select it with private runtime settings, or reconcile the additive migration explicitly. Restore comparisons must precede a connection change. Runtime inspection files under `/root/xereta/rollback` contain secrets and must stay private.

## Subsequent owner review — 2026-11-05

Two questions are resolved and both original knowledge items are accepted. The second answer and two validations were retained and verified in Hindsight, with the individual notes matching their owner states. The subsequent digest produced a new question and finding. An identical repeat of an accepted decision was reconciled to the reviewed record; its proposal file remains as linked history. That release passed 38 backend tests and the unchanged rerun. See [accepted feedback evidence](evidence/2026-11-05-accepted-feedback.json) and [claim reconciliation evidence](evidence/2026-11-05-reviewed-claim-dedupe.json).

The [Nextcloud bridge repair](evidence/2026-11-05-nextcloud-sync-repair.json) delivered all review files to the notebook and verified automatic creation/deletion propagation. Nextcloud Desktop was subsequently found paused; resuming it delivered the owner's untick to SilverBullet. Xereta's recorded reply was conditionally resent, preserving the previous copy, and reached the notebook with an identical SHA256 and the second checkbox still unchecked. The owner then checked the second box in Obsidian, and Xereta verified the generated text and recorded the roundtrip as **passed** at `2026-11-06T00:40:29Z` (November 5 locally). The notebook-offline digest and reconnection also passed, as recorded below. Qualify the remaining acceptance gates before enabling the schedule. The next recommended feature is a Sources screen to choose the next small batch from the 102 eligible notes, keeping per-run budgets bounded, followed by the staged Hermes reader connection.

## Notebook-offline digest — November 5 locally

Run `1c32cf4d-b0ff-456b-886e-02383c7b1e6b` completed at `2026-11-06T01:03:58Z` in about four minutes. Notebook SSH was unreachable over Tailscale and LAN before and after processing. Xereta captured the three approved Mini PC notes, retained the two pending owner-feedback records, consolidated Hindsight and generated the review. All nine current sources were verified in Hindsight. The original notes, owner answers, finding reviews, legacy Inbox and completed checkbox test were preserved. Six citations were checked against their versions and published source links; all eight review pages matched server readback. No new questions were created.

The server phase passed 25 checks. Because the review reused existing items, a dedicated generated receipt was conditionally written after the digest while the notebook was still unreachable: `space/_AgentKnowledge/Sync/notebook-offline-1c32cf4d.md`. It is excluded from knowledge ingestion. After the owner restored Nextcloud synchronization, read-only SFTP comparisons verified all 14 files: the receipt, eight review pages, three original notes, the legacy Inbox and the completed checkbox test. All hashes matched, owner answers and approvals were preserved, and the full test passed at `2026-11-06T01:11:26Z`. No notebook files were written by the verifier. Scheduling was kept disabled during this qualification. See the [offline digest evidence](evidence/2026-11-06-notebook-offline.json).

## Interrupted-run recovery — 2026-11-06

Release `0.2.3` passed 49 backend tests in its Docker build, plus frontend client generation, typechecking and the production build. The PostgreSQL-only case is skipped during that build and qualified separately: all eleven dedicated PostgreSQL cases passed with no skips. The real Hindsight canary was killed after a retention acknowledgement and resumed the same job/start timestamp/operation ID. Hindsight contained one document, one client batch and the expected internal item retention operation.

Before deployment, the database backup was restored into a disposable database and all 14 tables checked. Application data required exact row digests; the advancing live heartbeat used a row-count comparison. The state volume, checkout and previous image were preserved privately. The live worker restarted and completed run `83ac3a8d-4ebe-409c-b60d-813d289996fd`, preserving all source/version/feedback IDs, owner answers and approvals, and 13 protected file hashes. A separate verification passed afterward.

The disposable Hindsight bank, test database, restore database, role and synthetic state were removed. Evidence and private backups remain, including rollback image `xereta:before-recovery-56aee2b71c09`. Xereta was ready with no active runs or pending feedback. The acceptance flag and schedule were kept disabled; successful recovery qualification does not enable nightly processing automatically. Public interfaces and database schema are unchanged. See [recovery evidence](evidence/2026-11-06-recovery.json).

The runbook was repeated with fresh ID `c6b480b84b98` after an authorized owner credential reload. All eleven PostgreSQL cases, the real Hindsight canary, the live queued-job restart, follow-up verification and cleanup passed. All 13 protected file hashes and existing review records were preserved. HTTP login with the `.env` credentials was verified after recreation; the account ID was preserved and scheduling stayed disabled. The earlier `d4d3fac68947` attempt stopped during backup preparation before queueing its live job and was cleaned up. See the [repeat-run evidence](evidence/2026-11-06-recovery-rerun-c6b480b84b98.json).

## Small nightly pilot — enabled 2026-11-06

The owner authorized daily processing at **03:00 America/Sao_Paulo**. The first slot is **November 7 at 03:00** (`2026-11-07T06:00:00Z`); the first three slots are November 7, 8 and 9. Review those runs before expanding the source scope. The schedule continues daily until paused; three runs are a review checkpoint, not an automatic expiration.

The approved scope remains `space/Homelab/Comandos.md`, `space/Homelab/Ideas.md`, and `space/AI assets/models notes/Agentics models.md`, plus saved owner feedback. The existing limits remain twenty minutes per job and at most three unresolved questions. Unchanged source/feedback versions reuse the existing review. Generated review and sync-test files remain excluded from evidence.

The runtime environment was backed up privately under `/root/xereta/nightly-pilot-backups/20261106T105029Z/`. Only the acceptance flag changed; other runtime settings were verified unchanged. Both containers reloaded the gate, and activation used the authenticated owner schedule API with revision checking. Readback confirmed the correct timezone, future first slot, 11 preserved file hashes, preserved answers/reviews, nine verified Hindsight sources and healthy services. The run count stayed at 14: no immediate catch-up job was created. See [activation evidence](evidence/2026-11-06-nightly-pilot.json).

Use **Execuções** to review the first scheduled results and **Agenda** to pause future runs. Processing uses the Mini PC copy while the notebook is offline; delivery to and from Obsidian still depends on the notebook's unpaused Nextcloud client. No nightly completion has been observed yet; activation verification is separate from the three-run review.

An owner-requested manual preview completed on November 6 at 08:07 São Paulo time (run `80f21520-9a57-4809-ae2a-95a35741d64c`). It processed the nine current source records, reused the unchanged review and published successfully in about two seconds. It created no new questions/findings and left existing reviews, citations and the nightly schedule unchanged. This manual job does not count as the first scheduled night. See [manual preview evidence](evidence/2026-11-06-manual-preview.json).

The `0.3.0` Sources release passed 61 backend image tests, 12 PostgreSQL source-lock/recovery checks, two request-key unit tests and five browser tests on an actual insecure HTTP origin with synthetic API responses. Post-deployment verification authenticated the owner, denied catalogue access to the reader token, listed 102 eligible notes, and confirmed all 11 note files, review/database state and the existing 03:00 schedule were unchanged. No new batch or digest was authorized automatically. See [release evidence](evidence/2026-11-06-sources-release.json). Before expanding the pilot, complete one newly selected batch and its review/feedback loop, then review the first three scheduled nights.

To run the frontend regression checks after installing the locked dependencies:

```sh
cd frontend
bun run build
bun run test:unit
# Uses an isolated temporary browser profile and synthetic data.
# Set XERETA_CHROME_PATH if using an existing Chrome executable.
bun run test
```

For a normal code rollout, preserve the enabled schedule. The older recovery operator's live phase intentionally requires scheduling disabled and must not be used as a normal deployment script. `ops/sources_release_check.py` records a private before/after baseline; run it inside the app using stdin with `baseline` before deployment and `verify` after. It compares database state, source/review file hashes and the saved schedule without exposing note bodies or credentials.

Automatic mode `0.4.0` is deployed with schema `0003` and remains inactive until the owner approves folders and activates it. Qualification passed 85 backend image tests, 15 PostgreSQL locking/recovery checks, six HTTP browser tests, two request-key tests, desktop/mobile rendering, a restored-database migration with unchanged original rows, and a real Hindsight/ufsc-vision two-section canary with grounded original citations. The synthetic bank/database were deleted. Deployment preserved all 11 source/review files, the existing owner account, 15 previous runs and the enabled 03:00 schedule. See [Automatic mode release evidence](evidence/2026-11-06-automatic-release.json).

`ops/automatic_release_check.py` provides the private before/after rollout comparison for this release. Its `baseline` phase runs before deployment and `verify` after; pass it through stdin inside the app. The check compares original tables and source/review hashes, then verifies login and disabled Automatic mode. Database rollback requires restoring the verified backup; the migration intentionally provides no destructive downgrade. Synthetic build tests use a temporary in-memory filesystem for speed; PostgreSQL process-death qualification runs separately against a real disposable database.

## AFFiNE regular-ingestion release — 2026-11-08

Version `0.5.0` and schema `0004` are deployed. AFFiNE is configured and authenticated, with its automatic scope paused and unapproved. Existing SilverBullet Automatic mode remains active, sharing ten document-version attempts and twenty minutes per day with any subsequently approved AFFiNE scope. The enabled 03:00 America/Sao_Paulo schedule and its saved due slot were preserved; this release did not enqueue a production job.

Qualification passed 112 backend tests (three PostgreSQL-only skips were covered by the separate database suite), 15 real PostgreSQL recovery/concurrency tests, eight browser tests against the final compiled assets, two request-key unit tests, five reader service tests and thirteen codec tests. The final isolated UFSC canary processed three AFFiNE documents and their three SilverBullet counterparts as three source families, validating seven grounded citations. Its unchanged rerun created no duplicate work. Original binary captures and strict quotation/provenance checks were preserved.

A restored clone preserved all seventeen original table projections through migration. The live deployment preserved those same projections and all 37 protected source/review file hashes, both before and after normal service startup. The fresh final database backup also restored and migrated successfully. Private database, state, checkout and environment backups remain on the servers; the rollback image is `xereta:rollback-before-0.5.0`. Owner authentication, worker readiness, agent authorization denial and reader authentication passed. All four disposable databases, both restricted roles and the temporary Hindsight bank were removed; the earlier owner proof bank remains.

Hindsight's real restart preserved all seventy production documents; Docker and Compose now agree on `unless-stopped`. No source was edited or published to AFFiNE. Workspace-wide activation remains an explicit owner action in Fontes. See [sanitized release evidence](evidence/2026-11-08-affine-release.json) and the [reader runbook](ops/AFFINE.md). Scheduled-night observations and media/canvas interpretation are separate from this release qualification.
