#!/usr/bin/env bash
#
# Despliega price_tracker en el servidor.
#
# El servidor tiene su propio clon del repo con acceso a GitHub: el deploy
# actualiza ese clon a la ref pedida, construye el frontend ahí mismo, lo publica
# en TRACKER_WEB_ROOT (root que sirve el reverse proxy) y reconstruye el backend
# con Docker Compose (Alembic corre solo en el CMD del contenedor).
#
# Configuración: variables TRACKER_* del entorno o de deploy/deploy.env (ver
# deploy/deploy.env.example; ese archivo no se versiona).
#
# Uso:
#   ./scripts/deploy.sh                  # despliega main
#   ./scripts/deploy.sh --ref mi-rama    # otra rama/tag/commit
#   ./scripts/deploy.sh --frontend       # solo frontend
#   ./scripts/deploy.sh --backend        # solo backend
#   ./scripts/deploy.sh --no-pull        # usa el checkout del servidor tal cual
#
set -euo pipefail

ENV_FILE="${TRACKER_DEPLOY_ENV:-$(dirname "${BASH_SOURCE[0]}")/../deploy/deploy.env}"
if [[ -f "$ENV_FILE" ]]; then
	set -a
	# shellcheck source=/dev/null
	source "$ENV_FILE"
	set +a
fi

SSH_HOST="${TRACKER_SSH_HOST:-}"
if [[ -z "$SSH_HOST" ]]; then
	echo "Falta TRACKER_SSH_HOST (host SSH del servidor, o 'local'). Ver deploy/deploy.env.example." >&2
	exit 2
fi
if [[ "$SSH_HOST" == "local" ]]; then
	# En el servidor (auto-deploy): el clon es el repo desde donde se ejecuta.
	REMOTE_DIR="${TRACKER_REMOTE_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
else
	REMOTE_DIR="${TRACKER_REMOTE_DIR:-\$HOME/price_tracker}"
fi
WEB_ROOT="${TRACKER_WEB_ROOT:-/var/www/tracker}"
HEALTH_URL="${TRACKER_HEALTH_URL:-http://127.0.0.1:8910/api/health}"
COMPOSE_PROJECT="price_tracker"
PUBLIC_URL="${TRACKER_PUBLIC_URL:-}"

REF="main"
DO_FRONTEND=1
DO_BACKEND=1
DO_PULL=1

usage() {
	sed -n '3,17p' "$0" | sed 's/^# \{0,1\}//'
	exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
	case "$1" in
		--ref)
			[[ $# -ge 2 ]] || { echo "error: --ref necesita un valor" >&2; exit 2; }
			REF="$2"
			shift 2
			;;
		--frontend) DO_BACKEND=0; shift ;;
		--backend)  DO_FRONTEND=0; shift ;;
		--no-pull)  DO_PULL=0; shift ;;
		-h|--help)  usage 0 ;;
		*) echo "error: opción desconocida: $1" >&2; usage 2 ;;
	esac
done

log() { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }

log "Desplegando en $SSH_HOST (ref: $REF, frontend: $DO_FRONTEND, backend: $DO_BACKEND)"

# Todo corre en el servidor en una sola sesión. Las variables van por el entorno
# del shell remoto; el heredoc queda sin expandir ('REMOTE' entre comillas).
# TRACKER_SSH_HOST=local corre lo mismo sin SSH (así lo usa auto-deploy.sh).
if [[ "$SSH_HOST" == "local" ]]; then
	RUNNER=(env)
else
	RUNNER=(ssh -o BatchMode=yes "$SSH_HOST")
fi
"${RUNNER[@]}" \
	REMOTE_DIR="$REMOTE_DIR" \
	COMPOSE_PROJECT="$COMPOSE_PROJECT" \
	WEB_ROOT="$WEB_ROOT" \
	HEALTH_URL="$HEALTH_URL" \
	REF="$REF" \
	DO_FRONTEND="$DO_FRONTEND" \
	DO_BACKEND="$DO_BACKEND" \
	DO_PULL="$DO_PULL" \
	bash -s <<'REMOTE'
set -euo pipefail

log() { printf '\n\033[1;32m--\033[0m %s\n' "$*"; }
fail() { printf '\n\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

REMOTE_DIR="$(eval echo "$REMOTE_DIR")"
dc() { docker compose -p "$COMPOSE_PROJECT" "$@"; }

cd "$REMOTE_DIR" || fail "no existe el checkout $REMOTE_DIR"

# --- Comprobaciones previas -------------------------------------------------
command -v docker >/dev/null || fail "docker no está disponible"
docker compose version >/dev/null 2>&1 || fail "docker compose (plugin v2) no está disponible"
[[ -f backend/.env ]] || fail "falta backend/.env en el servidor (no está versionado; ver backend/.env.example)"
# data/ guarda hashes de contraseñas y tokens: solo el dueño.
mkdir -p data && chmod 700 data

# Un checkout sucio son cambios hechos a mano: se aborta antes de pisarlos.
if [[ "$DO_PULL" == "1" ]] && [[ -n "$(git status --porcelain)" ]]; then
	git status --short
	fail "el checkout del servidor tiene cambios sin commitear; resuélvelos o usa --no-pull"
fi

# --- Código -----------------------------------------------------------------
if [[ "$DO_PULL" == "1" ]]; then
	log "Actualizando checkout a $REF"
	git fetch origin --prune --tags
	if git rev-parse --verify --quiet "origin/$REF^{commit}" >/dev/null; then
		TARGET="origin/$REF"
	elif git rev-parse --verify --quiet "$REF^{commit}" >/dev/null; then
		TARGET="$REF"
	else
		fail "la ref '$REF' no existe en el remoto ni localmente"
	fi
	git checkout --quiet --detach "$TARGET"
else
	log "Saltando pull (--no-pull)"
fi
echo "HEAD: $(git log --oneline -1)"

# --- Frontend ---------------------------------------------------------------
if [[ "$DO_FRONTEND" == "1" ]]; then
	log "Construyendo frontend"
	command -v npm >/dev/null || fail "npm no está disponible en el servidor"
	cd "$REMOTE_DIR/frontend"
	npm ci --no-audit --no-fund
	npm run build
	[[ -f dist/index.html ]] || fail "el build no generó dist/index.html"

	log "Publicando en $WEB_ROOT"
	# Publicación atómica: árbol nuevo al lado y cambio con mv.
	STAGING="${WEB_ROOT}.new"
	OLD="${WEB_ROOT}.old"
	sudo rm -rf "$STAGING" "$OLD"
	sudo mkdir -p "$STAGING"
	sudo cp -a dist/. "$STAGING/"
	sudo chown -R caddy:caddy "$STAGING"
	if [[ -d "$WEB_ROOT" ]]; then
		sudo mv "$WEB_ROOT" "$OLD"
	fi
	sudo mv "$STAGING" "$WEB_ROOT"
	sudo rm -rf "$OLD"
	cd "$REMOTE_DIR"
fi

# --- Backend ----------------------------------------------------------------
if [[ "$DO_BACKEND" == "1" ]]; then
	log "Reconstruyendo backend"
	export TRACKER_UID="$(id -u)" TRACKER_GID="$(id -g)"
	dc build backend
	dc up -d

	log "Esperando a que el backend responda"
	for i in $(seq 1 45); do
		if curl -fs --max-time 3 "$HEALTH_URL" >/dev/null 2>&1; then
			echo "backend OK tras ${i}s: $(curl -s --max-time 3 "$HEALTH_URL")"
			break
		fi
		if [[ "$i" == "45" ]]; then
			echo "--- últimas líneas del log ---"
			dc logs --tail 40 backend
			fail "el backend no respondió en $HEALTH_URL tras 45s"
		fi
		sleep 1
	done

	log "Migraciones aplicadas"
	dc exec -T backend alembic current 2>&1 | tail -1
fi

log "Estado final"
dc ps --format 'table {{.Service}}\t{{.Status}}'
REMOTE

log "Deploy completo${PUBLIC_URL:+ → $PUBLIC_URL}"
