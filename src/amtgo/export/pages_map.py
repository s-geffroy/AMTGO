"""Export des couches de la carte publique (GitHub Pages).

Couches :
- ``countries`` : pays actuels (Natural Earth, frontières de facto) ;
- ``boundaries`` : lignes de frontière, avec drapeau ``disputed`` (pointillé) ;
- ``mesh_<id>`` : maillages d'analyse, qui ne sont PAS des propositions ;
- ``candidates.json`` : index des découpages candidats publiables.

L'index des candidats ne référence que des solutions passées par tous les
gates applicables (05 §20) et par le privacy guard. Il est vide tant
qu'aucun run n'en produit : son statut est alors NOT_IDENTIFIABLE, et la page
l'affiche. Aucune géométrie candidate n'est jamais fabriquée ici.

Les géométries sont simplifiées pour l'affichage uniquement ; l'analyse utilise
toujours les géométries complètes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import shapely
from shapely.geometry import mapping
from shapely.geometry.base import BaseGeometry

from amtgo.core.enums import PrivacyClass, RecommendationStatus
from amtgo.data.ingestion import read_observations
from amtgo.errors import ConfigurationError, ForbiddenSourceRole
from amtgo.manifests.run import RunManifest
from amtgo.privacy.guard import ExportLayer, require_allowed
from amtgo.runs import artifacts
from amtgo.runs.queue import load_manifest
from amtgo.runs.state import write_json_atomic

# Tolérance de simplification d'affichage (degrés) : ~2 km à l'équateur.
DISPLAY_SIMPLIFY_DEG = 0.02
# Grille de précision des coordonnées publiées (degrés) : ~11 m, sans effet visible.
DISPLAY_PRECISION_DEG = 1e-4
ROLE_BASEMAP = "basemap_display"
_DISPUTED_CLASSES = ("Disputed", "Indefinite", "Indeterminant", "Line of control")


def _display(geom: BaseGeometry) -> BaseGeometry:
    return shapely.set_precision(geom, DISPLAY_PRECISION_DEG)


def _fc(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": features}


def _write(out: Path, name: str, payload: Any) -> None:
    write_json_atomic(out / name, json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def export_pages_map(run_dir: Path, out: Path, status_from: Path | None = None) -> dict[str, Any]:
    """``status_from`` : run dont la validation (05 §20) motive l'état de la couche candidats."""
    manifest = load_manifest(run_dir)
    if not isinstance(manifest, RunManifest):
        raise ConfigurationError("carte Pages : seul un run régional produit des couches ; un run "
                                 "continental ou un contre-factuel historique (Map-C-Deep) n'en exporte aucune")
    outputs = artifacts.read_json(run_dir, "outputs.json")
    out.mkdir(parents=True, exist_ok=True)
    layers: list[dict[str, Any]] = []

    ne = next((s for s in manifest.data_manifest if s.manifest.retrieval.adapter == "natural_earth"), None)
    if ne is None:
        raise ValueError("le run ne contient pas la source Natural Earth")
    obs = read_observations(run_dir / "artifacts" / f"observations__{ne.manifest.source_id}.parquet")
    # Usage public : rôle d'affichage déclaré dans le run, et licence redistribuable.
    if ROLE_BASEMAP not in ne.use.roles:
        raise ForbiddenSourceRole(f"{ne.manifest.source_id} : rôle {ROLE_BASEMAP!r} non déclaré dans le run")
    ne.manifest.require_role(ROLE_BASEMAP)
    ne.manifest.require_license(redistribute=True, commercial=False)

    countries = [o for o in obs if o.variable_id == "admin0_polygon"]
    lines = [o for o in obs if o.variable_id == "admin0_boundary_line"]
    require_allowed(ExportLayer("countries", ne.manifest.privacy_class, False, False, False, len(countries)))
    require_allowed(ExportLayer("boundaries", ne.manifest.privacy_class, False, False, False, len(lines)))

    def feat(o: Any, props: dict[str, Any]) -> dict[str, Any]:
        g = o.geometry().simplify(DISPLAY_SIMPLIFY_DEG, preserve_topology=True)
        return {"type": "Feature", "properties": props, "geometry": mapping(_display(g))}

    _write(out, "countries.geojson", _fc([
        feat(o, {"adm0_a3": o.attributes.get("adm0_a3"), "name": o.attributes.get("name"),
                 "name_fr": o.attributes.get("name_fr"), "type": o.attributes.get("type"),
                 "note": o.attributes.get("note_adm0") or o.attributes.get("note_brk")})
        for o in sorted(countries, key=lambda o: o.admin_code or "")
    ]))
    _write(out, "boundaries.geojson", _fc([
        feat(o, {"featurecla": o.attributes.get("featurecla"),
                 "disputed": any(str(o.attributes.get("featurecla", "")).startswith(c)
                                 for c in _DISPUTED_CLASSES)})
        for o in lines
    ]))
    layers += [{"id": "countries", "file": "countries.geojson", "count": len(countries)},
               {"id": "boundaries", "file": "boundaries.geojson", "count": len(lines)}]

    for definition in manifest.mesh_set:
        mesh = artifacts.read_mesh(run_dir, definition.mesh_id)
        require_allowed(ExportLayer(f"mesh_{mesh.mesh_id}", PrivacyClass.PUBLIC, False, False, False, len(mesh)))
        _write(out, f"mesh_{mesh.mesh_id}.geojson", _fc([
            {"type": "Feature", "properties": {"cell_id": c.cell_id, "clipped": c.clipped},
             "geometry": mapping(_display(c.geometry))}
            for c in mesh.cells.values()
        ]))
        layers.append({"id": f"mesh_{mesh.mesh_id}", "file": f"mesh_{mesh.mesh_id}.geojson",
                       "count": len(mesh), "family": definition.family.value,
                       "resolution": definition.resolution})

    candidates: dict[str, Any] = {
        "status": (RecommendationStatus.NOT_IDENTIFIABLE.value if status_from is None
                   else artifacts.read_json(status_from, "artifacts/validation.json")["publication_category"]),
        "message": candidates_message(status_from),
        "regime": None, "ontology": None, "scenario": None,
        "no_change_alternative": True,
        "candidates": [],
    }
    _write(out, "candidates.json", candidates)

    meta = {
        "run_id": str(manifest.run_id),
        "manifest_hash": manifest.manifest_hash,
        "outputs_hash": outputs["outputs_hash"],
        "code_version": manifest.code_version,
        # Couches derivees publiees sous CC BY 4.0 ; Natural Earth reste du domaine public.
        "license": "CC-BY-4.0",
        "attribution": [{"name": ne.manifest.name, "release": ne.manifest.release,
                         "license": ne.manifest.license.license_id, "citation": ne.manifest.citation}],
        "layers": layers,
    }
    _write(out, "index.json", meta)
    return meta


RULE = ("Une frontière candidate n'est publiée qu'en catégorie ROBUST ou CONDITIONAL, tous gates passés "
        "(05 §20) ; rester tel quel (NO_CHANGE) reste toujours une alternative.")


def candidates_message(status_from: Path | None) -> str:
    """Pourquoi la couche candidats est vide, lu sur la validation d'un run réel (jamais un texte figé)."""
    if status_from is None:
        return ("Aucune frontière candidate : aucun run sur données réelles n'existe pour l'Afrique, les runs "
                "actuels portent sur des mondes synthétiques. " + RULE)
    m = load_manifest(status_from)
    v = artifacts.read_json(status_from, "artifacts/validation.json")
    gates = ", ".join(f"{k} {g}" for k, g in v["gates"].items() if g != "PASSED")
    name = m.request.name
    return (f"Aucune frontière candidate publiable. Run de référence « {name} » (monde synthétique) : catégorie "
            f"{v['publication_category']}" + (f", gates non passés : {gates}" if gates else "") + ". " + RULE
            + " Aucun run sur données réelles n'existe pour l'Afrique.")
