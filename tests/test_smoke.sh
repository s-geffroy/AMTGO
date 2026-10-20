#!/usr/bin/env bash
# Test minimal : le worker fait-il un cycle, pose-t-il son battement, et
# s'arrete-t-il sur SIGTERM ?
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

WORKER_INTERVAL=1 WORKER_STATE="$tmp/state" WORKER_HEARTBEAT="$tmp/beat" \
  timeout --signal=TERM 3 python3 "$here/../src/worker.py" > "$tmp/out" 2>&1 || true

test -f "$tmp/beat"          || { echo "ECHEC : pas de battement"; exit 1; }
test -f "$tmp/state/cycles"  || { echo "ECHEC : aucun cycle effectue"; exit 1; }
grep -q "arrete" "$tmp/out"  || { echo "ECHEC : arret non propre"; cat "$tmp/out"; exit 1; }
echo "OK : cycle effectue, battement pose, arret propre"
