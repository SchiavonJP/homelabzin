# AFFiNE reader operations

The 0.5.0 reader runs on CT106 at `192.168.0.221:3012`, alongside AFFiNE 0.27.4. Xereta on CT107 calls it over the LAN using a distinct bearer token. There is no public reverse proxy route. The reader permits the Xereta host, AFFiNE host and loopback, validates workspace IDs, and performs read-only source operations. Its native session can access what the AFFiNE account can read; the adapter exposes no source-writing operation.

## Deployment layout

- Public checkout: `/root/xereta-affine-app/apps/xereta` and `/root/xereta-affine-app/scripts`.
- Private directory: `/root/xereta-affine`, owner UID/GID 10001, mode 0700.
- Private files (0600): `reader-token`, `auth.json`, `config.json`, `image.env`.
- Container: `sb_xereta_affine_reader`, rootless with read-only root filesystem.
- Compose: `affine-reader.compose.yml`; `image.env` sets `XERETA_AFFINE_IMAGE` to the running AFFiNE image digest.

`config.json` contains `workspaces` and `generated` (workspace-to-generated-document-ID arrays). Keep generated reviews/evidence pages excluded. Pin the reader to the AFFiNE version it decodes; verify the codec before upgrading either image. No Docker socket, application database credentials or notebook mount is needed.

Start from the reader checkout:

```sh
docker compose --env-file /root/xereta-affine/image.env \
  -f affine-reader.compose.yml config --quiet
docker compose --env-file /root/xereta-affine/image.env \
  -f affine-reader.compose.yml up -d --pull never
```

Configure Xereta's four `XERETA_AFFINE_*` settings in `/root/xereta/.env` using the example. Compose parses the quoted JSON settings; do not pass that file verbatim with `docker run --env-file`. Preserve all existing settings. Reader configuration alone never approves a source scope.

## Session renewal

The reader durably rotates a native refresh token; it stores no password. It serializes capture/refresh and verifies the authenticated identity. If a refresh is interrupted ambiguously, it records `refreshPending` and requires reconnection instead of blindly replaying the one-use token.

When Fontes reports that authentication is required:

1. Obtain a current private AFFiNE cookie file using `scripts/knowledge-affine-login.py` on CT106. Credentials are entered there and are not stored. Keep the file 0600 and its origin `http://127.0.0.1:3010`.
2. Stop only `sb_xereta_affine_reader` to avoid concurrent session replacement.
3. Use the current cookie to create a **new** session file:

   ```sh
   python3 ops/affine_session.py \
     --cookie-auth-file /root/knowledge-affine-auth.json \
     --output /root/xereta-affine/auth-next.json
   ```

4. After `session_saved`, set owner `10001:10001` and mode 0600 on the new file, replace `auth.json` atomically, then start the reader. Keep the previous private file until verification, then remove obsolete session copies.
5. In Xereta Fontes, check the connection. Reconnection must not change approval, pause state, schedule or daily allowance.

Do not print session files, bearer keys, runtime environment or login responses in logs. The health endpoint checks process liveness; the authenticated connection check verifies AFFiNE access.

## Release and recovery

Before replacing Xereta, verify a restored database migration, PostgreSQL process-death recovery, and an isolated three-document canary. Keep a fresh PostgreSQL custom-format dump, a consistent state-volume backup, private environment/settings and the previous checkout/image. Stop app/worker while taking the final consistent backup. Record old table projections and source/review hashes; migration must preserve these before normal worker activity resumes.

Schema 0004 adds provider identities, captured titles, connection scopes and source relationships. It intentionally has no destructive downgrade. To roll back immediately, stop the app/worker, restore the verified pre-release database and matching state/config/code, then start the saved previous image. If owner edits or jobs occurred after release, preserve that later state and reconcile it before restoring; do not overwrite it blindly.

After deployment, verify readiness, worker heartbeat, owner login, reader-token denial on owner controls, existing schedule/usage, review hashes and unapproved/paused AFFiNE state. Test-bank and disposable database cleanup must use the exact guarded release metadata, never name patterns alone. The earlier owner proof bank is retained.

Enable AFFiNE only through Fontes: preview workspace/exclusions, approve/save, then activate. Observe a small bounded mixed-provider run and its reviews before increasing scope. Existing daily limits remain shared. Three successful scheduled nights are an observation gate, not implied by release tests.
