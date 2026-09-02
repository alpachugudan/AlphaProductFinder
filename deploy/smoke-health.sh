#!/usr/bin/env sh
set -eu

base_url="${1:-http://127.0.0.1}"
curl --fail --silent --show-error "$base_url/health/live"
printf '\n'
curl --fail --silent --show-error "$base_url/health/ready"
printf '\n'
