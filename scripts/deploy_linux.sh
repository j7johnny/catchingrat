#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE=""
RESTORE_DB=""
RESTORE_MEDIA=""

usage() {
    cat <<'EOF'
Usage:
  ./scripts/deploy_linux.sh --env-file /path/to/.env.production [--restore-db /path/to/postgres_dump.sql] [--restore-media /path/to/media.tar.gz]

What it does:
  1. Copies the provided env file to ./.env
  2. Runs docker compose up -d --build
  3. Optionally restores PostgreSQL and media backups
  4. Restarts app services after restore
  5. Prints docker compose status
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --env-file)
            ENV_FILE="${2:-}"
            shift 2
            ;;
        --restore-db)
            RESTORE_DB="${2:-}"
            shift 2
            ;;
        --restore-media)
            RESTORE_MEDIA="${2:-}"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage
            exit 1
            ;;
    esac
done

if [[ -z "$ENV_FILE" ]]; then
    echo "Missing required --env-file argument." >&2
    usage
    exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
    echo "Env file not found: $ENV_FILE" >&2
    exit 1
fi

if [[ -n "$RESTORE_DB" && ! -f "$RESTORE_DB" ]]; then
    echo "Database backup file not found: $RESTORE_DB" >&2
    exit 1
fi

if [[ -n "$RESTORE_MEDIA" && ! -f "$RESTORE_MEDIA" ]]; then
    echo "Media backup file not found: $RESTORE_MEDIA" >&2
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "docker is not installed." >&2
    exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
    echo "docker compose plugin is not installed." >&2
    exit 1
fi

cp "$ENV_FILE" "$ROOT_DIR/.env"

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

POSTGRES_DB="${POSTGRES_DB:-catchingrat}"
POSTGRES_USER="${POSTGRES_USER:-catchingrat}"

cd "$ROOT_DIR"

echo "[1/4] Building and starting services..."
docker compose up -d --build

if [[ -n "$RESTORE_DB" ]]; then
    echo "[2/4] Restoring PostgreSQL backup..."
    cat "$RESTORE_DB" | docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"
else
    echo "[2/4] PostgreSQL restore skipped."
fi

if [[ -n "$RESTORE_MEDIA" ]]; then
    echo "[3/4] Restoring media backup..."
    cat "$RESTORE_MEDIA" | docker compose exec -T web sh -c "mkdir -p /app/media && cd /app/media && tar xzf -"
else
    echo "[3/4] Media restore skipped."
fi

if [[ -n "$RESTORE_DB" || -n "$RESTORE_MEDIA" ]]; then
    echo "[4/4] Restarting app services after restore..."
    docker compose restart web worker beat nginx
else
    echo "[4/4] No restore requested. Restart skipped."
fi

echo
docker compose ps
echo
echo "Deployment finished."
echo "If this is a fresh deployment, create an admin account with:"
echo "  docker compose exec web python manage.py createsuperuser"
