#!/bin/sh
# Restore only to a fresh target path while the application is stopped.
set -eu
umask 077
fail() { printf '%s\n' "$1" >&2; exit 1; }
[ "$#" -eq 1 ] || fail 'Usage: sqlite-restore SNAPSHOT.sqlite'
snapshot=$1
case "$snapshot" in ''|[!A-Za-z0-9]*|*[!A-Za-z0-9._-]*) fail 'Invalid snapshot name.' ;; esac
database=${SQLITE_PATH:-/data/kitternel.db}
case "$database" in /data/*) ;; *) fail 'SQLITE_PATH must be an absolute ordinary file path below /data.' ;; esac
case "$database" in *'/../'*|*'/./'*|*/..|*/.) fail 'SQLITE_PATH must not contain dot path components.' ;; esac
source=/backups/$snapshot
[ -f "$source" ] && [ ! -L "$source" ] || fail 'Snapshot must be an existing regular file, not a symlink.'
for candidate in "$database" "$database-wal" "$database-shm" "$database-journal"; do
    [ ! -e "$candidate" ] && [ ! -L "$candidate" ] || fail 'Target database or sidecar exists; restore to a new empty volume.'
done
parent=$(dirname "$database")
[ -d "$parent" ] && [ -w "$parent" ] || fail 'Target directory must exist and be writable by the runtime UID.'
[ "$(sqlite3 -readonly -bail "$source" 'PRAGMA integrity_check;')" = ok ] || fail 'Snapshot integrity check failed.'
[ -z "$(sqlite3 -readonly -bail "$source" 'SELECT 1 FROM pragma_foreign_key_check LIMIT 1;')" ] || fail 'Snapshot foreign key check failed.'
temporary=$(mktemp "$parent/.kitternel-restore.XXXXXX")
cleanup() { rm -f "$temporary" "$temporary-wal" "$temporary-shm" "$temporary-journal"; }
trap cleanup 0
trap 'exit 1' HUP INT TERM
sqlite3 -bail "$temporary" ".restore '$source'"
[ "$(sqlite3 -bail "$temporary" 'PRAGMA journal_mode=DELETE;')" = delete ] || fail 'Could not finalize the restored journal.'
[ "$(sqlite3 -readonly -bail "$temporary" 'PRAGMA integrity_check;')" = ok ] || fail 'Restored database integrity check failed.'
[ -z "$(sqlite3 -readonly -bail "$temporary" 'SELECT 1 FROM pragma_foreign_key_check LIMIT 1;')" ] || fail 'Restored database foreign key check failed.'
sync -f "$temporary"
ln "$temporary" "$database"
sync -f "$parent"
printf 'Database restored to a fresh target. Validate using the matching application image before routing traffic.\n'
