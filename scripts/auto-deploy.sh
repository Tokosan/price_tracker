#!/usr/bin/env bash
#
# Auto-deploy: corre en el servidor cada minuto (tracker-autodeploy.timer). Si
# origin/main avanzó desde el último deploy exitoso, despliega ese commit con
# scripts/deploy.sh en modo local y avisa por Telegram del resultado al admin.
#
# Estado en ~/.local/state/price_tracker:
#   deployed-sha  último commit desplegado con éxito
#   failed-sha    último commit que falló; no se reintenta hasta que main avance
#                 (o hasta borrar este archivo a mano)
#
# Logs: journalctl -u tracker-autodeploy
#
set -euo pipefail

REPO="${TRACKER_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/price_tracker"
SCRIPT_TMP=""
trap 'rm -f "$SCRIPT_TMP"' EXIT

# Aviso por Telegram con el bot del tracker, al chat que el admin vinculó en la
# app. Sin token o sin admin vinculado, no avisa. El token nunca se imprime.
notify() {
	local token chat
	token="$(sed -n 's/^TELEGRAM_BOT_TOKEN=//p' "$REPO/backend/.env" 2>/dev/null | tr -d '"')"
	[[ -n "$token" && -f "$REPO/data/tracker.db" ]] || return 0
	chat="$(sqlite3 -readonly "$REPO/data/tracker.db" \
		"SELECT json_extract(c.config, '\$.chat_id') FROM channels c JOIN users u ON u.id = c.user_id
		 WHERE u.role = 'admin' AND u.active = 1 AND c.kind = 'telegram' AND c.enabled = 1 LIMIT 1" 2>/dev/null || true)"
	[[ -n "$chat" ]] || return 0
	curl -s -o /dev/null --max-time 10 \
		--data-urlencode "chat_id=$chat" \
		--data-urlencode "text=$1" \
		"https://api.telegram.org/bot$token/sendMessage" || true
}

# Todo dentro de main(): bash lee la función entera antes de ejecutarla, así que
# el deploy puede cambiar este mismo archivo (checkout) sin romper la corrida.
main() {
	mkdir -p "$STATE_DIR"
	exec 9>"$STATE_DIR/deploy.lock"
	flock -n 9 || { echo "hay otro deploy en curso; se salta esta vuelta"; return 0; }

	git -C "$REPO" fetch --quiet origin main
	local target deployed failed subject
	target="$(git -C "$REPO" rev-parse origin/main)"
	deployed="$(cat "$STATE_DIR/deployed-sha" 2>/dev/null || true)"
	failed="$(cat "$STATE_DIR/failed-sha" 2>/dev/null || true)"

	[[ "$target" != "$deployed" ]] || return 0
	[[ "$target" != "$failed" ]] || return 0

	subject="$(git -C "$REPO" log --format='%h %s' -1 "$target")"
	echo "main avanzó: desplegando $subject"

	# Se usa el deploy.sh del commit a desplegar, copiado fuera del checkout.
	local start
	SCRIPT_TMP="$(mktemp)"
	git -C "$REPO" show "$target:scripts/deploy.sh" >"$SCRIPT_TMP"

	start=$SECONDS
	if TRACKER_SSH_HOST=local TRACKER_REMOTE_DIR="$REPO" TRACKER_DEPLOY_ENV="$REPO/deploy/deploy.env" \
		bash "$SCRIPT_TMP" --ref "$target"; then
		echo "$target" >"$STATE_DIR/deployed-sha"
		rm -f "$STATE_DIR/failed-sha"
		notify "✅ tracker desplegado en $((SECONDS - start))s: $subject"
	else
		echo "$target" >"$STATE_DIR/failed-sha"
		notify "❌ Falló el deploy del tracker: $subject. Ver journalctl -u tracker-autodeploy en el servidor."
		return 1
	fi
}

main "$@"
