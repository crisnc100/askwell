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
# The old volume is left in place, with every upload, the audit log and the day's spend
# out of reach of the sweep and "Delete my data". Once the new app is checked, remove it
# with the `docker volume rm` command the script prints.
set -euo pipefail

if [ "$#" -ne 2 ]; then
  sed -n '2,15p' "$0" >&2
  exit 2
fi

src="$1_ledgerline-data"
dst="$2_askwell-data"
image="alpine:3.20@sha256:d9e853e87e55526f6b2917df91a2115c36dd7c696a35be12163d44e6e2a4b6bc"

fail() {
  echo "$1" >&2
  exit 1
}

# Every check captures its docker call first: a failure inside $(...) or an if
# condition does not stop the script under set -e, and would read as "unused" or "empty".
docker volume inspect "$src" >/dev/null 2>&1 \
  || fail "refusing: volume $src does not exist (or docker could not be reached)"

users=$(docker ps -aq --filter "volume=$src") || fail "stopping: docker ps failed"
if [ -n "$users" ]; then
  fail "refusing: a container still uses $src; stop the old app first:
  docker compose -f compose.prod.yaml down   (in the old app's folder)"
fi

if ! docker volume inspect "$dst" >/dev/null 2>&1; then
  # Compose's own labels, so `up` adopts this volume instead of warning about it.
  docker volume create \
    --label "com.docker.compose.project=$2" \
    --label "com.docker.compose.volume=askwell-data" \
    "$dst" >/dev/null || fail "stopping: could not create volume $dst"
fi

contents=$(docker run --rm -v "$dst:/to" "$image" ls -A /to) \
  || fail "stopping: could not list volume $dst"
if [ -n "$contents" ]; then
  fail "refusing: volume $dst is not empty"
fi

docker run --rm -v "$src:/from:ro" -v "$dst:/to" "$image" cp -a /from/. /to/ \
  || fail "stopping: the copy into $dst failed; it may hold part of $src"
echo "copied $src to $dst:"
docker run --rm -v "$dst:/to:ro" "$image" ls -lan /to
echo
echo "Once the new app is up and checked, remove the old copy:"
echo "  docker volume rm $src"
