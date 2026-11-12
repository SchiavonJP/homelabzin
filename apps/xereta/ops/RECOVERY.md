# Recovery qualification

`recovery_gate.py` runs as root on **Proxmox**, using `pct exec` to reach CT107
(Xereta) and CT104 (PostgreSQL). It prints checks and opaque IDs, never credentials
or note contents. Do not expose it through HTTP, MCP, or a scheduled task.

## Preparation

Stage the candidate Xereta checkout at `/root/xereta-recovery-src` on CT107 and
copy this operator script to `/root/xereta-recovery-gate.py` on Proxmox. Exclude
`.venv`, `node_modules`, `__pycache__`, and macOS `._*` metadata when transferring.
Keep `/root/xereta/.env` private and outside both checkouts.

The operator creates a dedicated `xereta_recovery_<id>` PostgreSQL role and
database, a `knowledge-vault-recovery-<id>` Hindsight bank, and private test state.
The role owns only the disposable database and cannot create databases or roles.
Both worker scheduling gates must remain disabled. The live phase requires no
active job, no pending feedback, three unchanged approved notes, a complete
publication, and an already cached review.

When the nightly pilot is enabled, let active work finish and pause the schedule
in **Agenda** before qualification. Close the runtime acceptance gate
(`XERETA_ACCEPTANCE_PASSED=false`) and reload the app/worker first. Re-enabling
the pilot afterward is a separate owner action; confirm its next slot through
authenticated schedule readback.

## Run

Choose a new ID for each qualification. All commands below run on Proxmox:

```sh
xereta_recovery_id=$(python3 -c 'import secrets; print(secrets.token_hex(6))')
python3 /root/xereta-recovery-gate.py isolated --id "$xereta_recovery_id"
python3 /root/xereta-recovery-gate.py canary --id "$xereta_recovery_id"
```

The `--image` option accepts `xereta:0.2.2` or `xereta:0.2.3`; the earlier image
may supply dependencies while the candidate backend and operator code are
mounted read-only. The isolated phase requires every PostgreSQL case to pass,
including the advisory-lock check, with no skips. It rejects production database
names and SQLite paths outside the disposable test directory.

Build the candidate image from the staged checkout on CT107. The Docker build
runs all backend tests, generates the frontend client, typechecks, and builds the
frontend. The PostgreSQL-only test is separately qualified by the isolated gate.

```sh
pct exec 107 -- docker compose --project-directory /root/xereta-recovery-src \
  -f /root/xereta-recovery-src/compose.yml build app
python3 /root/xereta-recovery-gate.py live --id "$xereta_recovery_id"
python3 /root/xereta-recovery-gate.py verify --id "$xereta_recovery_id"
python3 /root/xereta-recovery-gate.py cleanup --id "$xereta_recovery_id"
```

A source digest binds the isolated and canary results to the staged code; changed
code requires qualification again. The live phase installs `xereta:0.2.3`,
preserves the previous image, and starts an unchanged queued job after restarting
only the Xereta worker. It qualifies deployment/queued-job recovery; process
crashes during work are covered in isolation and by the real Hindsight canary.

## What is checked

- Worker processes are killed at deterministic barriers, rather than merely
  raising exceptions. Replacement processes use the same PostgreSQL state and
  the real worker loop. Test transports and synthetic model output are injected
  only in those child processes; production adapters and destination validation
  are unchanged.
- A saved retention operation ID is reused. Real Hindsight creates one
  `batch_retain` operation using that ID and one internal `retain` operation for
  the single item. That expected pair must not be mistaken for duplication.
- An ambiguous consolidation request stops with
  `consolidation_requires_reconciliation`; it is not blindly resubmitted.
- A journaled first publication with no remote file can be created conditionally.
  A write accepted before a crash is reconciled by readback. A later human edit
  is preserved and flagged; a deleted previously published file is not recreated.
- PostgreSQL permits one active worker and transfers the lock after its process
  dies. A restart keeps the original start timestamp and the remaining portion
  of the twenty-minute budget, including downtime.
- The live test preserves source versions, operation IDs, answers, approvals,
  feedback, and file hashes. Exactly one test run is added. No new model work is
  required by the cached review.

## Evidence, failure, and cleanup

Private reports, command logs, the database dump and volume backup are under
`/root/xereta-recovery/<id>/` on Proxmox. CT107 keeps state/checkout backups under
`/root/xereta/recovery/<id>/`, plus application evidence under
`/data/gates/recovery/<id>/` in the Xereta state volume. Private files use 0600 and
directories use 0700. Copy only the safe JSON result files into repository evidence.

The live backup is restored into a disposable database before deployment. All
application data tables require matching row digests. The live heartbeat's row
count is compared because its timestamp continues advancing during verification;
the backup still contains its transactionally captured row.

Failed checks stop the gate. The worker is started again even if queueing fails.
If the new deployment does not become ready, the prior code/image is restored;
the production database is never automatically restored over newer owner edits.
A timed-out live test requests a stop only for its recorded recovery job. Inspect
its actual final state before retrying. A started live phase is not blindly
replayed: use `verify` for its saved run or investigate and choose a new ID.

`cleanup` deletes only the named recovery bank, test database, disposable restore
database, dedicated role, test state and temporary database environment file.
Evidence, private backups and the rollback image are retained. It does not reset
CouchDB, Nextcloud, SilverBullet, Hermes, or the production Hindsight bank.
Cleanup should also be run after a failed isolated/canary test once its evidence
has been inspected. Nightly processing remains a separate gate.
