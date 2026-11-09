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
# Require canonical parents: a lexical /data prefix does not exclude symlink escapes.
parent=$(dirname "$database")
resolved_parent=$(realpath -e -- "$parent") || fail 'Database parent directory must already exist.'
case "$resolved_parent" in /data|/data/*) ;; *) fail 'Database parent must resolve below /data.' ;; esac
[ "$resolved_parent" = "$parent" ] || fail 'Database parent must not contain symlinks or non-canonical components.'
source=/backups/$snapshot
[ -f "$source" ] && [ ! -L "$source" ] || fail 'Snapshot must be an existing regular file, not a symlink.'
for candidate in "$database" "$database-wal" "$database-shm" "$database-journal"; do
    [ ! -e "$candidate" ] && [ ! -L "$candidate" ] || fail 'Target database or sidecar exists; restore to a new empty volume.'
done
[ -d "$parent" ] && [ -w "$parent" ] || fail 'Target directory must exist and be writable by the runtime UID.'
integrity_result=$(sqlite3 -readonly -bail "$source" 'PRAGMA integrity_check;') || fail 'Snapshot integrity check failed.'
[ "$integrity_result" = ok ] || fail 'Snapshot integrity check failed.'
foreign_key_result=$(sqlite3 -readonly -bail "$source" 'SELECT 1 FROM pragma_foreign_key_check() LIMIT 1;') || fail 'Snapshot foreign key check could not be completed.'
[ -z "$foreign_key_result" ] || fail 'Snapshot foreign key check failed.'
temporary=$(mktemp "$parent/.kitternel-restore.XXXXXX")
cleanup() { rm -f "$temporary" "$temporary-wal" "$temporary-shm" "$temporary-journal"; }
trap cleanup 0
trap 'exit 1' HUP INT TERM
sqlite3 -bail "$temporary" ".restore '$source'"
journal_mode=$(sqlite3 -bail "$temporary" 'PRAGMA journal_mode=DELETE;') || fail 'Could not finalize the restored journal.'
[ "$journal_mode" = delete ] || fail 'Could not finalize the restored journal.'
integrity_result=$(sqlite3 -readonly -bail "$temporary" 'PRAGMA integrity_check;') || fail 'Restored database integrity check failed.'
[ "$integrity_result" = ok ] || fail 'Restored database integrity check failed.'
foreign_key_result=$(sqlite3 -readonly -bail "$temporary" 'SELECT 1 FROM pragma_foreign_key_check() LIMIT 1;') || fail 'Restored database foreign key check could not be completed.'
[ -z "$foreign_key_result" ] || fail 'Restored database foreign key check failed.'
sync -f "$temporary"
ln -T -- "$temporary" "$database"
sync -f "$parent"
printf 'Database restored to a fresh target. Validate using the matching application image before routing traffic.\n'
