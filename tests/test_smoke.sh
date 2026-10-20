#!/usr/bin/env bash
# Test minimal, DANS le conteneur (rien ne s'execute sur l'hote) :
#   sudo appctl run cli tests/test_smoke.sh
# Le worker prend un run synthetique dans sa file, l'execute etape par etape,
# pose son battement, et s'arrete proprement sur SIGTERM.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
tmp=$(mktemp -d)
pid=""
trap 'kill "$pid" 2>/dev/null || true; rm -rf "$tmp"' EXIT

export AMTGO_STATE_DIR="$tmp/state" AMTGO_DB_HOST="" WORKER_INTERVAL=1 \
       WORKER_STATE="$tmp/state" WORKER_HEARTBEAT="$tmp/beat"

run_id=$(amtgo run submit "$here/../configs/runs/synthetic_pilot.yaml" | tail -n1 | cut -d' ' -f1)

python3 -u "$here/../src/worker.py" > "$tmp/out" 2>&1 &
pid=$!

status=""
for _ in $(seq 1 120); do
  status=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['status'])" \
           "$tmp/state/runs/$run_id/state.json" 2>/dev/null || true)
  [ "$status" = "SUCCEEDED" ] || [ "$status" = "FAILED" ] && break
  sleep 1
done
kill -TERM "$pid"
wait "$pid" || true

test -f "$tmp/beat"                         || { echo "ECHEC : pas de battement"; cat "$tmp/out"; exit 1; }
[ "$status" = "SUCCEEDED" ]                 || { echo "ECHEC : run $status"; cat "$tmp/out"; exit 1; }
test -f "$tmp/state/runs/$run_id/report.md" || { echo "ECHEC : pas de rapport"; exit 1; }
grep -q '"event": "worker.stop"' "$tmp/out" || { echo "ECHEC : arret non propre"; cat "$tmp/out"; exit 1; }
echo "OK : run $run_id execute par le worker, battement pose, arret propre"
