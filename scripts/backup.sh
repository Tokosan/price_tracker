#!/usr/bin/env bash
#
# Backup de la DB de SQLite con `.backup` (consistente aunque haya escrituras en
# WAL; copiar el archivo en caliente puede dar un backup corrupto).
# Rotación: 7 diarios y 4 semanales (el semanal se toma los domingos).
#
# Lo dispara tracker-backup.timer. Logs: journalctl -u tracker-backup
#
set -euo pipefail

REPO="${TRACKER_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
DB="$REPO/data/tracker.db"
DEST="${TRACKER_BACKUP_DIR:-$REPO/backups}"
KEEP_DAILY=7
KEEP_WEEKLY=4

[[ -f "$DB" ]] || { echo "no existe $DB; nada que respaldar"; exit 0; }
mkdir -p "$DEST/daily" "$DEST/weekly"
chmod 700 "$DEST"

stamp="$(date +%Y%m%d-%H%M%S)"
out="$DEST/daily/tracker-$stamp.db"
sqlite3 "$DB" ".backup '$out'"
# Si el backup no pasa el chequeo de integridad, se descarta y el timer falla.
if [[ "$(sqlite3 "$out" 'PRAGMA integrity_check;')" != "ok" ]]; then
	rm -f "$out"
	echo "ERROR: el backup no pasó integrity_check" >&2
	exit 1
fi
gzip -9 "$out"
echo "backup diario: $out.gz ($(du -h "$out.gz" | cut -f1))"

if [[ "$(date +%u)" == "7" ]]; then
	cp "$out.gz" "$DEST/weekly/"
	echo "copia semanal: $DEST/weekly/$(basename "$out.gz")"
fi

# Rotación: se conservan los N más nuevos de cada carpeta.
# (find en vez de ls: con la carpeta vacía ls sale con error y pipefail corta.)
prune() {
	local dir="$1" keep="$2"
	find "$dir" -maxdepth 1 -name 'tracker-*.db.gz' -printf '%T@ %p\n' \
		| sort -rn | tail -n +"$((keep + 1))" | cut -d' ' -f2- | xargs -r rm -f --
}
prune "$DEST/daily" "$KEEP_DAILY"
prune "$DEST/weekly" "$KEEP_WEEKLY"
