#!/usr/bin/env sh
set -eu

compose_file="$(dirname "$0")/docker-compose.yml"
project_dir="$(cd "$(dirname "$0")/.." && pwd)"
dataset_version="${1:-2026-07-11-baseline}"

cd "$project_dir"
docker compose -f "$compose_file" up -d postgres
docker compose -f "$compose_file" exec -T postgres pg_isready -U product_finder -d product_finder
docker compose -f "$compose_file" run --rm --no-deps app alembic upgrade head
docker compose -f "$compose_file" run --rm --no-deps app python -m scripts.validate_source_hashes --manifest data/manifests/source_manifest.json --source-dir /data/source
docker compose -f "$compose_file" run --rm --no-deps app python -m scripts.ingest_excel --manifest data/manifests/source_manifest.json --source-dir /data/source
docker compose -f "$compose_file" run --rm --no-deps app python -m scripts.build_curated --dataset-version "$dataset_version"
docker compose -f "$compose_file" run --rm --no-deps app python -m scripts.validate_curated --dataset-version "$dataset_version"
docker compose -f "$compose_file" run --rm --no-deps app python -m scripts.ingest_external
