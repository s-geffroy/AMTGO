"""Étapes M9 : ``compose:<mesh>`` puis ``compose_ensemble``.

Le composeur travaille sur la géométrie des baselines (statu quo), sous chaque
ontologie et sur chaque maillage, avec les efficacités de la bibliothèque gelée.
La conclusion n'est retenue que si elle est la même partout ; sinon elle est
CONDITIONAL (dépend de l'ontologie ou du maillage). Aucune frontière n'est proposée.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

from amtgo.core.provenance import ProvenanceRecord
from amtgo.errors import ConfigurationError
from amtgo.institutions.composer import compose
from amtgo.institutions.status_quo import build_institutions
from amtgo.measurement import fields as fields_mod
from amtgo.runs import artifacts
from amtgo.runs.candidate_stages import cell_adjacency
from amtgo.runs.causal_stages import frozen_library
from amtgo.runs.dfi_stages import cached_kernel, social_state, status_quo_partition
from amtgo.utils.canonical import content_hash

if TYPE_CHECKING:
    from amtgo.runs.stages import StageContext


def compose_mesh(ctx: StageContext, mesh_id: str) -> dict[str, Any]:
    cm = ctx.manifest.composer_model
    dm = ctx.manifest.dfi_model
    sq = ctx.manifest.status_quo
    if cm is None or dm is None or sq is None:
        raise ConfigurationError("le composeur exige un modèle D/F/I et un statu quo")
    mesh = artifacts.read_mesh(ctx.run_dir, mesh_id)
    partition = status_quo_partition(ctx, mesh)
    institutions = build_institutions(sq, partition)
    kernel = cached_kernel(ctx, mesh, dm.network_kernel_length_km, dm.network_kernel_cutoff)
    population = fields_mod.read_field(ctx.run_dir, mesh_id)[2].astype(np.float64)
    adjacency = cell_adjacency(mesh)
    lib = frozen_library(ctx)
    region = ctx.manifest.request.region
    effects = {k: lib.query(k, region) for k in cm.effect_keys}
    nm = ctx.manifest.normative_manifest
    per_ontology = {}
    for ont in ctx.manifest.ontology_set:
        ctx.check_stop(f"compose {mesh_id} {ont.ontology_id}")
        state, _ = social_state(ctx, mesh, ont.ontology_id, population, kernel)
        per_ontology[ont.ontology_id] = compose(state, partition, institutions, nm.rights,
                                                nm.connection_weights.as_channels(), cm, effects, adjacency,
                                                ctx.check_stop)
    out = {"mesh_id": mesh_id, "geometry": "STATUS_QUO (baselines NO_TERRITORIAL_CHANGE, INSTITUTIONAL_ONLY_REFORM)",
           "regime": ctx.manifest.constitutional_regime.regime_id.value,
           "privacy_class": nm.privacy.default_access.value,
           "effects": {k: {"status": a.status, "grade": None if a.grade is None else a.grade.value}
                       for k, a in effects.items()},
           "ontologies": per_ontology}
    artifacts.write_json(ctx.run_dir, f"fields/{mesh_id}/institutional_composition.json", out)
    record = ProvenanceRecord.create(
        "institutions.compose", [f"causal_freeze:{lib.freeze_hash}", f"composer:{cm.content_hash}",
                                 f"status_quo:{sq.content_hash}"],
        [f"institutional_composition:{mesh_id}:{content_hash(out)}"], run_id=ctx.manifest.run_id)
    artifacts.write_provenance(ctx.run_dir, [record])
    ctx.repo.record_provenance([record])
    conclusions = sorted({v["conclusion"] for v in per_ontology.values()})
    return {"count": len(per_ontology), "detail": ",".join(conclusions)}


def compose_ensemble(ctx: StageContext, _: str) -> dict[str, Any]:
    per_mesh = {d.mesh_id: artifacts.read_json(ctx.run_dir, f"fields/{d.mesh_id}/institutional_composition.json")
                for d in ctx.manifest.mesh_set}
    cells = {(m, o): (v["conclusion"], v["chosen"]) for m, x in per_mesh.items() for o, v in x["ontologies"].items()}
    distinct = sorted(set(cells.values()), key=str)
    if len(distinct) == 1:
        conclusion, chosen = distinct[0]
        stability = "STABLE"
    else:
        conclusion, chosen, stability = "CONDITIONAL", None, "DEPENDS_ON_ONTOLOGY_OR_MESH"
    result = {"conclusion": conclusion, "chosen": chosen, "stability": stability,
              "by_mesh_ontology": {f"{m}|{o}": {"conclusion": c, "chosen": ch} for (m, o), (c, ch) in cells.items()},
              "recommendation_status": "NOT_IDENTIFIABLE",
              "note": "à géométrie fixe ; aucune frontière proposée ; l'adoption reste externe au modèle"}
    artifacts.write_json(ctx.run_dir, "artifacts/institutional_ensemble.json", result)
    return {"detail": f"{conclusion} ({stability})"}
