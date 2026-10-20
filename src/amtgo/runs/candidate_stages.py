"""Étapes M8 : ``candidates:<mesh>`` puis ``candidate_ensemble`` (S^scale par famille).

Les candidats sont générés sur chaque maillage à partir de la population gelée
et de la géographie seulement. Leur stabilité multi-échelle (gate de la phase 3,
11) est mesurée par la distance TRANSFER entre maillages, sur la grille de
référence. Rien n'est évalué ni classé ici, et rien n'est publié : le statut de
recommandation reste NOT_IDENTIFIABLE jusqu'à l'optimiseur et aux gates.
"""

from __future__ import annotations

import io
from collections import defaultdict
from itertools import combinations
from typing import TYPE_CHECKING, Any

import numpy as np
from shapely import STRtree

from amtgo.candidates.generate import (
    canonical_labels,
    community_partition,
    is_contiguous,
    repair_contiguity,
    spectral_partition,
    weighted_kmeans,
)
from amtgo.candidates.model import (
    BASELINES,
    ROLE_HISTORICAL_SEED,
    CandidateFamily,
    CandidateManifest,
    TerritoryCandidate,
)
from amtgo.core.enums import SupportType
from amtgo.core.provenance import ProvenanceRecord
from amtgo.data.ingestion import read_observations
from amtgo.errors import ConfigurationError, TopologyError
from amtgo.geo.crs import to_equal_area
from amtgo.geo.mesh import Mesh
from amtgo.geo.multiscale import transfer_distance
from amtgo.geo.ops import neighbor_graph
from amtgo.institutions.status_quo import assign_cells_to_polygons
from amtgo.measurement import fields as fields_mod
from amtgo.runs import artifacts
from amtgo.runs.dfi_stages import cached_kernel, status_quo_partition
from amtgo.utils.canonical import content_hash, stable_uuid

if TYPE_CHECKING:
    from amtgo.runs.stages import StageContext


def _model(ctx: StageContext) -> CandidateManifest:
    m = ctx.manifest.candidate_model
    if m is None:
        raise ConfigurationError("aucun générateur de candidats dans ce run")
    return m


def _adjacency(mesh: Mesh) -> list[list[int]]:
    index = {c: k for k, c in enumerate(mesh.cells)}
    return [[index[n] for n in nbrs] for nbrs in neighbor_graph(mesh).values()]


def generate(ctx: StageContext, mesh_id: str) -> tuple[list[TerritoryCandidate], dict[str, np.ndarray],
                                                      dict[str, str]]:
    cm = _model(ctx)
    mesh = artifacts.read_mesh(ctx.run_dir, mesh_id)
    sq = next(lv for lv in status_quo_partition(ctx, mesh).levels if lv.name == cm.level)
    pop = fields_mod.read_field(ctx.run_dir, mesh_id)[2].astype(np.float64).mean(axis=0)
    xy = np.array([[(p := to_equal_area(c.geometry).centroid).x / 1000.0, p.y / 1000.0]
                   for c in mesh.cells.values()])
    adjacency = _adjacency(mesh)
    seed = ctx.manifest.seeds[0]
    out: list[TerritoryCandidate] = []
    assignments: dict[str, np.ndarray] = {}
    by_hash: dict[str, str] = {}

    def add(family: CandidateFamily, method: str, params: dict[str, Any], assign: np.ndarray) -> None:
        moved = 0
        if family.is_baseline:
            assign = canonical_labels(assign)
        else:
            assign, moved = repair_contiguity(assign, adjacency, pop)
        h = content_hash(assign.tolist())
        cid = str(stable_uuid("candidate", {"mesh": mesh_id, "family": family.value, "params": params, "h": h}))
        k = int(assign.max()) + 1
        shares = [float(pop[assign == j].sum() / pop.sum()) for j in range(k)]
        dup = None if family.is_baseline else by_hash.get(h)
        by_hash.setdefault(h, cid)
        out.append(TerritoryCandidate(cid, family, method, params, mesh_id, cm.level, k, h,
                                      is_contiguous(assign, adjacency), moved, shares, dup))
        assignments[cid] = assign

    # Baselines : toujours (prompt §78). Même géométrie, portées institutionnelles distinctes (M9).
    for fam in BASELINES:
        add(fam, "statu quo déclaré", {}, sq.assignment)
    for k in cm.state_counts:
        add(CandidateFamily.GEOGRAPHIC, "k-means pondéré par la population", {"k": k},
            weighted_kmeans(xy, pop, k, cm.restarts, seed))
    centres = np.array([np.average(xy[sq.assignment == j], axis=0, weights=pop[sq.assignment == j])
                        for j in range(len(sq.jurisdictions))])
    add(CandidateFamily.GEOGRAPHIC_SEEDED, "k-means amorcé sur les centres du statu quo",
        {"k": len(sq.jurisdictions)}, weighted_kmeans(xy, pop, len(sq.jurisdictions), 1, seed, init=centres))
    kernel = cached_kernel(ctx, mesh, cm.network_kernel_length_km, cm.network_kernel_cutoff)
    for k in cm.state_counts:
        ctx.check_stop(f"candidates {mesh_id} spectral {k}")
        add(CandidateFamily.GRAPH_SPECTRAL, "coupe normalisée du graphe des liens", {"k": k},
            spectral_partition(kernel, pop, k, cm.restarts, seed))
    for r in cm.community_resolutions:
        add(CandidateFamily.GRAPH_COMMUNITY, "Louvain, graphe d'adjacence pondéré", {"resolution": r},
            community_partition(adjacency, kernel, pop, r, seed))

    unavailable: dict[str, str] = {}
    seeds = [s for s in ctx.manifest.data_manifest if ROLE_HISTORICAL_SEED in s.use.roles]
    if seeds:
        for s in seeds:
            polys = [o for o in read_observations(ctx.observations_path(s.manifest.source_id))
                     if o.support_type in (SupportType.ADMIN, SupportType.POLYGON)]
            add(CandidateFamily.HISTORICAL, "frontières administratives historiques", {"source": s.manifest.source_id},
                assign_cells_to_polygons(mesh, polys)[0])
    else:
        unavailable[CandidateFamily.HISTORICAL.value] = (
            f"aucune source déclarée avec le rôle {ROLE_HISTORICAL_SEED!r} ; une carte ethnographique "
            "(rôle ontology_validation) n'en est jamais une")
    unavailable[CandidateFamily.LANGUAGE.value] = (
        "non implémenté : exige une ontologie de dimension « language » et une revue d'éthique (06) ; "
        "les familles territoriales n'utilisent jamais les parts de groupes")
    unavailable[CandidateFamily.MOBILITY.value] = "aucun flux de mobilité dans ce run (data gap critique, 03 §20)"
    if not all(any(c.family is f for c in out) for f in BASELINES):
        raise TopologyError("baselines manquantes : le générateur serait biaisé vers l'action (prompt §78)")
    return out, assignments, unavailable


def candidates(ctx: StageContext, mesh_id: str) -> dict[str, Any]:
    cm = _model(ctx)
    cands, assignments, unavailable = generate(ctx, mesh_id)
    buf = io.BytesIO()
    arrays: dict[str, Any] = {c.candidate_id: assignments[c.candidate_id] for c in cands}
    np.savez_compressed(buf, **arrays)
    artifacts.write_bytes(ctx.run_dir, f"fields/{mesh_id}/candidates.npz", buf.getvalue())
    out = {"mesh_id": mesh_id, "level": cm.level,
           "privacy_class": ctx.manifest.normative_manifest.privacy.default_access.value,
           "candidates": [c.to_json() for c in cands], "unavailable_families": unavailable}
    artifacts.write_json(ctx.run_dir, f"fields/{mesh_id}/candidates.json", out)
    freeze = artifacts.read_json(ctx.run_dir, "measurement_freeze.json")
    record = ProvenanceRecord.create(
        "candidates.generate", [f"measurement_freeze:{freeze['freeze_hash']}", f"candidates:{cm.content_hash}",
                                f"mesh:{mesh_id}"],
        [f"candidates:{mesh_id}:{content_hash(out)}"], run_id=ctx.manifest.run_id)
    artifacts.write_provenance(ctx.run_dir, [record])
    ctx.repo.record_provenance([record])
    mesh = artifacts.read_mesh(ctx.run_dir, mesh_id)
    ctx.repo.record_candidates(ctx.manifest.run_id, mesh, cands, assignments)
    distinct = len({c.assignment_hash for c in cands})
    return {"count": len(cands), "detail": f"distincts={distinct} non_contigus={sum(not c.contiguous for c in cands)}"}


def _reference_index(mesh: Mesh, ref: Mesh) -> np.ndarray:
    """Pour chaque cellule de référence, l'indice de la cellule de ``mesh`` qui contient son centre (−1 sinon)."""
    geoms = [to_equal_area(c.geometry) for c in mesh.cells.values()]
    tree = STRtree(geoms)
    out = np.full(len(ref.cells), -1, dtype=int)
    for k, rc in enumerate(ref.cells.values()):
        centre = to_equal_area(rc.geometry).centroid
        hits = tree.query(centre, predicate="within")
        if len(hits) == 0:
            hits = tree.query(centre, predicate="intersects")
        if len(hits):
            out[k] = int(min(hits))
    return out


def _distance(a: np.ndarray, b: np.ndarray, ia: np.ndarray, ib: np.ndarray, area: np.ndarray) -> float:
    ok = (ia >= 0) & (ib >= 0)
    joint: dict[tuple[str, str], float] = defaultdict(float)
    for la, lb, w in zip(a[ia[ok]], b[ib[ok]], area[ok], strict=True):
        joint[(str(la), str(lb))] += float(w)
    return transfer_distance(joint)


def candidate_ensemble(ctx: StageContext, _: str) -> dict[str, Any]:
    cm = _model(ctx)
    ref = artifacts.read_mesh(ctx.run_dir, cm.reference_mesh)
    area = np.array([c.area_km2 for c in ref.cells.values()])
    meshes = [d.mesh_id for d in ctx.manifest.mesh_set]
    per_mesh = {m: artifacts.read_json(ctx.run_dir, f"fields/{m}/candidates.json") for m in meshes}
    arrays = {m: dict(np.load(io.BytesIO((ctx.run_dir / "fields" / m / "candidates.npz").read_bytes())))
              for m in meshes}
    index = {m: _reference_index(artifacts.read_mesh(ctx.run_dir, m), ref) for m in meshes}
    groups: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for m, v in per_mesh.items():
        for c in v["candidates"]:
            groups[f"{c['family']}|{content_hash(c['params'])}"][m] = c
    tau = ctx.manifest.normative_manifest.stability.scale_min
    by_key: dict[str, Any] = {}
    for key, by_m in sorted(groups.items()):
        ctx.check_stop("candidate_ensemble")
        dists = [_distance(arrays[a][by_m[a]["candidate_id"]], arrays[b][by_m[b]["candidate_id"]],
                           index[a], index[b], area) for a, b in combinations(sorted(by_m), 2)]
        s_scale = 1.0 - max(dists) if dists else None
        first = next(iter(by_m.values()))
        by_key[key] = {"family": first["family"], "params": first["params"], "s_scale": s_scale,
                       "stable": None if s_scale is None else s_scale >= tau,
                       "n_states_by_mesh": {m: c["n_states"] for m, c in sorted(by_m.items())},
                       "contiguous_everywhere": all(c["contiguous"] for c in by_m.values()),
                       "duplicate_on": sorted(m for m, c in by_m.items() if c["duplicate_of"])}
    families: dict[str, Any] = defaultdict(lambda: {"variants": 0, "stable": 0})
    for v in by_key.values():
        f = families[v["family"]]
        f["variants"] += 1
        f["stable"] += int(bool(v["stable"]))
    result = {"reference_mesh": cm.reference_mesh, "scale_min": tau, "variants": by_key,
              "families": dict(families),
              "unavailable_families": next(iter(per_mesh.values()))["unavailable_families"],
              "recommendation_status": "NOT_IDENTIFIABLE",
              "note": "unités analytiques, non évaluées (M10) ; aucune n'est une proposition"}
    artifacts.write_json(ctx.run_dir, "artifacts/candidate_ensemble.json", result)
    stable = sum(int(bool(v["stable"])) for v in by_key.values())
    return {"count": len(by_key), "detail": f"stables={stable}/{len(by_key)}"}
