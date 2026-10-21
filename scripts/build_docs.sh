#!/bin/sh
# Construit le site : execute les runs publics, exporte la carte et les rapports,
# puis mkdocs build --strict. Usage : scripts/build_docs.sh <dossier_sortie>
# En CI, la sortie est publiee sur GitHub Pages ; localement, elle reste dans le
# conteneur (verification uniquement).
set -eu
out=${1:-site}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cp -r docs "$work/docs"
cp mkdocs.yml "$work/"
export AMTGO_STATE_DIR="${AMTGO_STATE_DIR_DOCS:-$work/state}" AMTGO_DB_HOST=""
mkdir -p "$work/docs/runs/generated" "$work/docs/assets/generated/map"

for run in synthetic_pilot synthetic_c_shallow pages_africa; do
  rid=$(amtgo run execute "configs/runs/$run.yaml" | tail -n1 | cut -d' ' -f1)
  amtgo export report "$rid" "$work/docs/runs/generated/$run.md"
  if [ "$run" = pages_africa ]; then
    amtgo export pages-map "$rid" "$work/docs/assets/generated/map"
  fi
done

# Coordination continentale (M14) : execute d'abord ses runs regionaux.
rid=$(amtgo run execute configs/continental/synthetic_continental.yaml | tail -n1 | cut -d' ' -f1)
amtgo export report "$rid" "$work/docs/runs/generated/synthetic_continental.md"

amtgo validate worlds --out "$work/docs/runs/generated/worlds.md" > /dev/null

mkdocs build --strict --config-file "$work/mkdocs.yml" --site-dir "$(realpath -m "$out")"
echo "site -> $out"
