#!/usr/bin/env sh
set -eu

project_dir="$(cd "$(dirname "$0")/.." && pwd)"
compose_file="$project_dir/deploy/docker-compose.yml"
backup_dir="${BACKUP_DIR:-$project_dir/backups}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_file="$backup_dir/product-finder-$timestamp.dump"

umask 077
mkdir -p "$backup_dir"
docker compose -f "$compose_file" exec -T postgres \
  pg_dump -U product_finder -d product_finder --format=custom > "$backup_file"
sha256sum "$backup_file" > "$backup_file.sha256"
printf 'backup=%s\n' "$backup_file"
