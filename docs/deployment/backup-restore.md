# Consistent SQLite backup and recovery

Use the image's `/app/sqlite-backup` and `/app/sqlite-restore` helpers. They use SQLite's online backup API through its CLI, validate integrity/foreign keys, and publish a standalone DELETE-journal database file with restrictive permissions. No live `.db` file copy, database reset, or destructive migration is used. The backup helper may run while the app uses WAL; restore must target a separate empty volume, never a live database.

Requirements: the matching Kitternel image, a local POSIX filesystem supporting hard links, and operator access to Docker on the data host. The image has SQLite and the helpers already installed. Snapshot names must start with a letter/digit and contain only letters, digits, dots, underscores, and hyphens. Existing snapshots/target databases are never overwritten, including by concurrent invocations. Helpers do not encrypt data or upload it off-host; that remains an operator responsibility.

## Identify and record the actual source

Do not infer a data volume from a directory or service name. Compose adds a project prefix; platform-managed names can differ. From `templates/light`, inspect the running app:

```sh
kitternel_container=$(docker compose ps -q app)
docker inspect "$kitternel_container" --format '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Type}} {{.Name}} {{.Source}}{{end}}{{end}}'
```

Record the selected application image/commit, database path, migration versions, UTC backup time, host, and actual volume name in your backup inventory. Keep that inventory outside the database volume. Commands below use named volumes; a bind-mounted deployment needs the corresponding reviewed source directory mount instead. Never mount a clone/build directory as database storage.

Set these values to the actual source and matching built image before proceeding:

```sh
kitternel_image=kitternel-light:local
kitternel_data_volume=kitternel-light-data
kitternel_backup_volume=kitternel-light-backups
kitternel_snapshot="kitternel-$(date -u +%Y%m%dT%H%M%SZ).sqlite"
docker volume inspect "$kitternel_data_volume"
docker volume create "$kitternel_backup_volume"
```

The source volume must already exist. The backup volume is independent of `/data`, initialized from the image's `/backups` directory as UID/GID 10001. Populated volumes/bind mounts need explicitly verified ownership and permissions; never fix them with chmod 777. Use a stable image digest/release identifier in real backup inventories; a mutable `:local` tag is only convenient for the development example.

## Create and export a snapshot

```sh
docker run --rm --read-only --no-healthcheck --network none \
  --cap-drop ALL --security-opt no-new-privileges:true \
  --tmpfs /tmp:size=32m,mode=1777 \
  --mount "source=$kitternel_data_volume,target=/data" \
  --mount "source=$kitternel_backup_volume,target=/backups" \
  --entrypoint /app/sqlite-backup "$kitternel_image" "$kitternel_snapshot"
```

The one-off helper disables the application health check because it is not an HTTP server. The source connection is read-only, but the data directory mount permits SQLite's shared-memory/WAL coordination. The helper does not update application rows. It snapshots committed data, so ongoing changes after that point are not part of this backup. The snapshot is built on the backup volume, avoiding the application's bounded `/tmp` capacity. There must be enough free space for the database snapshot, source WAL activity, and temporary working files. A busy/error result is a failed backup, not permission to copy the live file instead.

The default database is `/data/kitternel.db`. For another supported path below `/data`, pass the same `-e SQLITE_PATH=/data/your-file.db` to backup, restore, and application commands. For a nested path, pre-provision its directory on the new restore volume with UID/GID 10001 permissions. Helpers reject SQLite URIs, dot-path components, symlink database files, and paths outside `/data`.

Export the finalized snapshot, not the live application database:

```sh
umask 077
install -d -m 0700 backups
test ! -e "backups/$kitternel_snapshot"
kitternel_export="kitternel-export-$(date -u +%Y%m%dT%H%M%SZ)"
docker create --name "$kitternel_export" --read-only --network none \
  --mount "source=$kitternel_backup_volume,target=/backups,readonly" \
  --entrypoint /bin/true "$kitternel_image"
docker cp "$kitternel_export:/backups/$kitternel_snapshot" "backups/$kitternel_snapshot"
docker rm "$kitternel_export"
```

Verify the exported file, record a checksum, then transfer it to your protected off-host storage using the site's approved encrypted transport/storage mechanism. A checksum detects accidental changes; it does not authenticate an untrusted backup. A second volume on the same server does not protect against host loss. Choose a backup schedule, retention, recovery point objective, and recovery time objective for the actual data; no scheduler, cloud credential, or retention service is supplied by this starter.

## Restore drill into a new volume

Keep the original database and volume intact. Select a snapshot you trust and an application image compatible with its migration history. Create a new named volume:

```sh
kitternel_restore_volume=kitternel-light-restored
docker volume create "$kitternel_restore_volume"
docker run --rm --read-only --no-healthcheck --network none \
  --cap-drop ALL --security-opt no-new-privileges:true \
  --tmpfs /tmp:size=32m,mode=1777 \
  --mount "source=$kitternel_restore_volume,target=/data" \
  --mount "source=$kitternel_backup_volume,target=/backups,readonly" \
  --entrypoint /app/sqlite-restore "$kitternel_image" "$kitternel_snapshot"
```

The helper validates the source and reconstructed database before atomically creating the target. It refuses existing database, WAL, SHM, or journal files. If it refuses, investigate the volume selection; do not delete those files to bypass the guard. Restoring an externally exported snapshot requires first importing that trusted single file into the protected backup volume with readable UID/GID 10001 permissions; verify its recorded checksum and integrity before use.

Verify the restored database directly:

```sh
docker run --rm --read-only --no-healthcheck --network none \
  --mount "source=$kitternel_restore_volume,target=/data" \
  --entrypoint sqlite3 "$kitternel_image" -readonly /data/kitternel.db \
  'PRAGMA integrity_check; PRAGMA foreign_key_check; SELECT version, success FROM _sqlx_migrations ORDER BY version;'
```

Require `ok` from integrity checking, no foreign-key violation rows, and the expected successful migration history. Run a temporary validation app against only the restored volume:

```sh
docker run -d --name kitternel-restored --read-only \
  --tmpfs /tmp:size=32m,mode=1777 --cap-drop ALL \
  --security-opt no-new-privileges:true --stop-timeout 15 \
  -p 127.0.0.1:8081:8080 \
  --mount "source=$kitternel_restore_volume,target=/data" "$kitternel_image"
curl --fail http://127.0.0.1:8081/health/ready
curl --fail http://127.0.0.1:8081/api/hello
docker logs kitternel-restored
```

Wait for readiness before concluding a failure or success. Compare actual application data with the snapshot inventory, not merely an HTTP 200 or the seed greeting. Startup may apply migrations from the chosen image; use the matching release first, then treat an upgrade as a separate reviewed operation.

## Cutover and rollback

A drill alone does not switch production traffic. Before a real recovery, stop the original app, stop/remove the validation container, and change the deployment to mount the new verified volume. Do not run two application instances against the restored volume. Preserve the original volume and image for investigation and a separately reviewed rollback decision.

```sh
docker stop kitternel-restored
docker rm kitternel-restored
```

For Compose, stop `app`, then use a reviewed local override that maps the existing `light-data` volume key to the restored external volume:

```yaml
volumes:
  light-data:
    external: true
    name: kitternel-light-restored
```

Use both the canonical Compose file and that override for subsequent commands so a later plain `up` does not switch back to the original volume. On Dokploy/Coolify, change the persistent mount on the existing single-instance application and verify stop-first behavior. Check readiness, expected application data, and HTTPS routing after cutover. Never use `down --volumes` as part of recovery. An older image is only a safe rollback when its schema expectations match the retained database; image rollback does not undo migrations.

## Automated evidence and limits

From the repository root, after building the image:

```sh
python3 scripts/sqlite-backup-smoke.py --image kitternel-light:local
```

The suite uses independent disposable source/backup/restore volumes. It writes a non-seed greeting into a live WAL database, creates a consistent snapshot, checks integrity/data/migration history, changes the source, restores to another volume, and confirms both databases through HTTP. It also tests existing-file refusal, invalid names, missing source, corrupt backups, and orphaned sidecars. This validates a local Docker recovery drill, not host-loss recovery, off-host encryption/upload, platform archives, or a production RPO/RTO. See the [verification record](../development/verification.md).
