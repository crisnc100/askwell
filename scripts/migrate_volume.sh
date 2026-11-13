#!/usr/bin/env bash
# Copies the hosted beta's data volume from its Ledgerline name to its Askwell name, once,
# before the first `docker compose -f compose.prod.yaml up` of the renamed app.
#
#   scripts/migrate_volume.sh <old compose project> <new compose project>
#   scripts/migrate_volume.sh ledgerline askwell
#
# A compose project is named after its folder unless -p says otherwise, so /opt/ledgerline
# is "ledgerline" and /opt/askwell is "askwell". The script copies
# <old>_ledgerline-data into <new>_askwell-data with owners, modes and times kept (the app
# runs as uid 10001). It refuses if the old volume is missing or still mounted by a
# container, or if the new volume already holds anything, so it can only copy once.
# The old volume is left in place; remove it once the new app is checked.
set -euo pipefail

if [ "$#" -ne 2 ]; then
  sed -n '2,13p' "$0" >&2
  exit 2
fi

src="$1_ledgerline-data"
dst="$2_askwell-data"
image="alpine:3.20"

if ! docker volume inspect "$src" >/dev/null 2>&1; then
  echo "refusing: volume $src does not exist" >&2
  exit 1
fi
if [ -n "$(docker ps -aq --filter "volume=$src")" ]; then
  echo "refusing: a container still uses $src; stop the old app first:" >&2
  echo "  (cd /opt/ledgerline && docker compose -f compose.prod.yaml down)" >&2
  exit 1
fi

if ! docker volume inspect "$dst" >/dev/null 2>&1; then
  # Compose's own labels, so `up` adopts this volume instead of warning about it.
  docker volume create \
    --label "com.docker.compose.project=$2" \
    --label "com.docker.compose.volume=askwell-data" \
    "$dst" >/dev/null
fi
if [ -n "$(docker run --rm -v "$dst:/to" "$image" ls -A /to)" ]; then
  echo "refusing: volume $dst is not empty" >&2
  exit 1
fi

docker run --rm -v "$src:/from:ro" -v "$dst:/to" "$image" cp -a /from/. /to/
echo "copied $src to $dst:"
docker run --rm -v "$dst:/to:ro" "$image" ls -lan /to
