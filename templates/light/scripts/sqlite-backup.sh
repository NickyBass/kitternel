#!/bin/sh
# Make a consistent standalone snapshot in an independently mounted backup volume.
set -eu
umask 077
fail() { printf '%s\n' "$1" >&2; exit 1; }
[ "$#" -eq 1 ] || fail 'Usage: sqlite-backup SNAPSHOT.sqlite'
snapshot=$1
case "$snapshot" in ''|[!A-Za-z0-9]*|*[!A-Za-z0-9._-]*) fail 'Snapshot name must start with an alphanumeric character and contain only letters, digits, dots, underscores, or hyphens.' ;; esac
database=${SQLITE_PATH:-/data/kitternel.db}
case "$database" in /data/*) ;; *) fail 'SQLITE_PATH must be an absolute ordinary file path below /data.' ;; esac
case "$database" in *'/../'*|*'/./'*|*/..|*/.) fail 'SQLITE_PATH must not contain dot path components.' ;; esac
[ -f "$database" ] && [ ! -L "$database" ] || fail 'Source database must be an existing regular file, not a symlink.'
[ -d /backups ] && [ -w /backups ] || fail 'Mount an independently managed writable backup volume at /backups.'
destination=/backups/$snapshot
[ ! -e "$destination" ] && [ ! -L "$destination" ] || fail 'Snapshot already exists; refusing to overwrite it.'
temporary=$(mktemp "/backups/.${snapshot}.XXXXXX")
cleanup() { rm -f "$temporary" "$temporary-wal" "$temporary-shm" "$temporary-journal"; }
trap cleanup 0
trap 'exit 1' HUP INT TERM
sqlite3 -readonly -bail "$database" '.timeout 5000' ".backup '$temporary'"
# The snapshot must remain usable as one file after export, without WAL sidecars.
[ "$(sqlite3 -bail "$temporary" 'PRAGMA journal_mode=DELETE;')" = delete ] || fail 'Could not finalize the snapshot journal.'
[ "$(sqlite3 -readonly -bail "$temporary" 'PRAGMA integrity_check;')" = ok ] || fail 'Snapshot integrity check failed.'
[ -z "$(sqlite3 -readonly -bail "$temporary" 'SELECT 1 FROM pragma_foreign_key_check LIMIT 1;')" ] || fail 'Snapshot foreign key check failed.'
sync -f "$temporary"
# Atomic no-clobber publication, including concurrent backup invocations.
ln "$temporary" "$destination"
sync -f /backups
printf 'Snapshot created: /backups/%s\n' "$snapshot"
