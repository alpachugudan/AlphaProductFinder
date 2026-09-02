#!/usr/bin/env sh
set -eu

compose_file="$(dirname "$0")/docker-compose.yml"
project_dir="$(cd "$(dirname "$0")/.." && pwd)"
dataset_version="${1:-2026-07-11-baseline}"

cd "$project_dir"
docker compose -f "$compose_file" up -d postgres
for attempt in $(seq 1 30); do
  if docker compose -f "$compose_file" exec -T postgres pg_isready -U product_finder -d product_finder; then
    break
  fi
  if [ "$attempt" -eq 30 ]; then
    echo "PostgreSQL did not become ready within 60 seconds" >&2
    exit 1
  fi
  sleep 2
done
docker compose -f "$compose_file" run --rm --no-deps app alembic upgrade head
docker compose -f "$compose_file" run --rm --no-deps app python -m scripts.validate_source_hashes --manifest data/manifests/source_manifest.json --source-dir /data/source
docker compose -f "$compose_file" run --rm --no-deps app python -m scripts.ingest_excel --manifest data/manifests/source_manifest.json --source-dir /data/source
docker compose -f "$compose_file" run --rm --no-deps app python -m scripts.build_curated --dataset-version "$dataset_version"
docker compose -f "$compose_file" run --rm --no-deps app python -m scripts.validate_curated --dataset-version "$dataset_version"
docker compose -f "$compose_file" run --rm --no-deps app python -m scripts.ingest_external
