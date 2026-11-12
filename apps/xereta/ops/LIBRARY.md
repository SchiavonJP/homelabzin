# Reference library, reading queue and model operations

Xereta 0.6.0 separates a reference catalogue from knowledge ingestion. Saved references, metadata tags and suggested links do not enter Hindsight. Karakeep holds reading tasks; the shared Obsidian/SilverBullet vault holds lasting references and journals. AFFiNE remains an independent source.

## Model

`XERETA_LITELLM_MODEL=generalist` selects Xereta's metadata/review model. The dedicated Hindsight runtime uses `HINDSIGHT_PILOT_MODEL=generalist`; its Compose environment exposes this as `HINDSIGHT_API_LLM_MODEL`. Embeddings continue using `embed`. Verify both runtime values at an idle worker boundary before replacing containers. No historical memory rewrite is necessary. Generalist and vision currently share the Qwen backend; routing is not a quality benchmark. Existing literal quotation and authority validators remain enforced.

## Configuration

Private runtime settings remain in `/root/xereta/.env` (0600):

- `XERETA_LIBRARY_ENABLED=true` enables catalogue maintenance, independently of the paused organization/digestion controls.
- `XERETA_KARAKEEP_URL=http://192.168.0.12:3000` is the fixed internal API origin.
- `XERETA_KARAKEEP_TOKEN` holds a private API token. Never put it in the checkout, import JSON or browser storage.
- `XERETA_PUBLIC_KARAKEEP_URL=https://keep.joaopaulo.me` is the human-facing link.
- `XERETA_ARTICLE_DOMAINS` is a JSON array of exact public HTTPS hostnames approved for direct article capture. The default empty array denies direct fetching. Redirect hosts must also be approved; DNS results must all be public and the connection is pinned to the verified address while retaining TLS hostname validation.

Fontes → Integrações controls reference/journal/legacy folders, topic vocabulary, aliases, owner-defined concepts and Karakeep list IDs. Folder changes pause ingestion. Organization and ingestion have separate controls; saving does not enqueue a digest. The existing Agenda and knowledge budget remain independent.

The database is the source of truth for operational configuration. `schema_version: 1` JSON exports include library, SilverBullet and AFFiNE scopes and no credentials. Import preview validates the entire document. Apply requires the three current revisions, uses the existing transaction lock, and pauses ingestion. No automatic file-watching or competing configuration source exists.

Operator equivalents, inside the application container:

```sh
python -m app.library_cli export
python -m app.library_cli preview --file /private/config.json
python -m app.library_cli apply --file /private/config.json \
  --library-revision CURRENT --automation-revision CURRENT --affine-revision CURRENT
```

Mount any operator JSON read-only for a one-off container; do not make private environment files downloadable.

## Reading and permission

For a reference from notes, select Preparar digestão. Xereta captures plain text into a candidate version without invoking an LLM. The owner reviews it, checks Li esta versão and explicitly authorizes the displayed hash. Capture alone does not authorize digestion. A changed candidate invalidates eligibility until the new version is confirmed.

In Karakeep, choose separate private, owner-controlled manual lists for Inbox and Pronto para o Xereta. Shared/public/smart lists are rejected for readiness. A list membership authorizes the first captured body; later body changes wait for owner confirmation in Xereta. Readiness is rechecked before processing checkpoints. Imports, favourites, tags and archive state do not grant permission. Removing readiness stops additional requests, preserves receipts and does not delete history.

Reference folders, the legacy collection, configured AFFiNE aliases and recognized clipped copies cannot pass through the ordinary note-ingestion route. Manual selection cannot bypass the boundary. External article records cannot establish an owner decision; owner confirmation belongs to the existing reviewed feedback workflow.

The reading adapter targets the version-qualified Karakeep 0.33.2 API. Catalogue pagination explicitly sends `includeContent=false`. Article capture explicitly requests content only for the capture/readiness path. Preserve this distinction on upgrades.

## Organization and navigation

The serialized worker synchronizes metadata every 15 minutes, independently of notebook availability. Organization uses only an explicit metadata allowlist and the configured topic vocabulary. URL query values are removed from model inputs. Attempts/time are durably reserved before requests, bounded to 50 items/five minutes daily; knowledge retains its separate ten-version/twenty-minute allowance.

Human classifications and rejected suggestions persist. Managed topic, project, concept and reference pages use relative internal Markdown links: SilverBullet's `/data` root and Obsidian's nested `/data/space` vault differ, so absolute `space/` wikilinks would break in Obsidian. Relative links resolve to the same physical files. Never rewrite original journals to manufacture backlinks.

Publication journals the intended hash before conditional writes, recognizes completed writes after interruption, and holds conflicting edits. Generated files are excluded from evidence. Inspect conflicts rather than overwriting edits. Verify native navigation/backlinks on both editors before considering the human navigation gate complete.

The new MCP tools `search_references` and `get_related_items` are read-only. Catalogue results retain their undigested status and relationship origin; search visibility is not factual endorsement.

## ReadItLater split migration

Use Fontes → Integrações → Migrar ReadItLater com prévia. Inventory archives captured originals privately under `/data/readitlater/<id>/files`. Complete the paginated preview, classify destinations and principal URLs, then apply batches of up to five. GitHub and existing read folders inform suggestions only; they never establish reading permission. Exceptions remain visible.

Destinations are Inbox in Karakeep, a new UUID-named reference note under `space/Referências/`, or the original pending manual review. Existing bookmarks are looked up before creation; their notes and tags are not patched. New reference files use conditional creation and original paths/hashes. Repeating completed rows creates no new work. Original Markdown and assets are never moved or deleted.

A migration HTTP write with an unknown acknowledgement is held as `unknown` for explicit reconciliation; do not blindly reset it. Inspect the remote bookmark/list state and private manifest before recording a receipt. Keep legacy originals and known copies excluded from normal ingestion. Unclassified items are not silently discarded.

## Release and rollback

Qualify restored schema migration, PostgreSQL recovery, no-retention catalogue tests, browser consent behavior and a real model/Hindsight canary in a disposable bank. Synthetic approvals must remain in isolated test state. Do not simulate an owner reading a production article.

At an idle worker boundary, stop app/worker briefly and back up the database, state volume, private environment, checkout and previous image. Compare original table projections and protected source/review file hashes before starting normal work. New scopes deploy paused. Back up Karakeep consistently before the first migration write and preserve a manifest of created destinations.

Schema 0005 has no destructive downgrade. Immediate rollback requires the matching verified database/state/config backup and saved image. If owner edits occurred after deployment, preserve and reconcile them before restoring; do not overwrite later edits. Migration rollback must not delete bookmarks that already existed or notes subsequently edited by the owner.
