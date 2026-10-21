"""Étapes D/F/I (M5) : ``dfi:<mesh>`` puis ``dfi_ensemble``.

Elles consomment les champs **gelés** (population × composition) : elles ne
réestiment rien (prompt §32). Le statu quo déclaré est évalué sous chaque
ontologie du run et sur chaque maillage ; S^ontology et S^scale portent désormais
sur des quantités D/F/I.

Groupes : la masse ``__unmapped__`` d'une ontologie projetée n'est attribuée à
aucun groupe ; sa part est rapportée (hypothèse déclarée).
"""

from __future__ import annotations

import io
from itertools import combinations
from typing import TYPE_CHECKING, Any

import numpy as np
from scipy import sparse
from scipy.spatial import cKDTree

from amtgo.core.channels import FragChannel, IntegChannel
from amtgo.core.enums import EvidenceStatus, PrivacyClass, SupportType
from amtgo.core.provenance import ProvenanceRecord
from amtgo.data.ingestion import read_observations
from amtgo.domination.engine import domination
from amtgo.errors import ConfigurationError
from amtgo.fragmentation.engine import fragmentation
from amtgo.geo.crs import to_equal_area
from amtgo.geo.mesh import Mesh
from amtgo.geo.partition import Partition
from amtgo.identity.reification import alignment
from amtgo.identity.state import BoundedSalienceResponse, SocialState
from amtgo.institutions.status_quo import build_institutions, build_partition
from amtgo.integration.engine import integration
from amtgo.measurement import fields as fields_mod
from amtgo.ontology.model import UNMAPPED
from amtgo.runs import artifacts
from amtgo.runs.causal_stages import frozen_library
from amtgo.utils.canonical import content_hash

if TYPE_CHECKING:
    from amtgo.runs.stages import StageContext


# Points de quadrature par cellule pour intégrer le noyau (résolution numérique, pas paramètre
# scientifique) : 16 points suffisent à stabiliser le noyau entre maillages (test MAUP).
QUADRATURE_POINTS = 16


def cell_points(mesh: Mesh, per_cell: int) -> list[np.ndarray]:
    """Points déterministes uniformes dans chaque cellule (LAEA, km) : grille, puis rejet."""
    import shapely

    out = []
    side = int(np.ceil(np.sqrt(per_cell)))
    for c in mesh.cells.values():
        g = to_equal_area(c.geometry)
        minx, miny, maxx, maxy = g.bounds
        k = side
        pts = np.zeros((0, 2))
        while len(pts) < per_cell and k <= 8 * side:
            gx, gy = np.meshgrid(minx + (np.arange(k) + 0.5) * (maxx - minx) / k,
                                 miny + (np.arange(k) + 0.5) * (maxy - miny) / k)
            cand = np.column_stack([gx.ravel(), gy.ravel()])
            pts = cand[shapely.contains_xy(g, cand[:, 0], cand[:, 1])]
            k += 1
        if len(pts) == 0:
            pts = np.array([[g.centroid.x, g.centroid.y]])
        idx = np.linspace(0, len(pts) - 1, min(per_cell, len(pts))).astype(int)
        out.append(pts[idx] / 1000.0)
    return out


def network_kernel(mesh: Mesh, length_km: float, cutoff: float) -> sparse.csr_matrix:
    """R_ij = moyenne de exp(−d/L) sur les paires de points de quadrature des cellules i et j.

    Discrétisation d'un noyau continu de liens par paire de personnes. Évaluer le
    noyau au seul centroïde sous-estime les liens entre grandes cellules voisines
    (beaucoup de paires proches de l'arête commune) : F variait d'un facteur 3 selon
    la maille (révision M5, ADR-0017). Troncature à ``cutoff``·L + diamètres des cellules.
    """
    pts = cell_points(mesh, QUADRATURE_POINTS)
    centres = np.array([p.mean(axis=0) for p in pts])
    radius = np.array([np.max(np.linalg.norm(p - p.mean(axis=0), axis=1)) for p in pts])
    tree = cKDTree(centres)
    reach = cutoff * length_km + 2 * radius.max()
    pairs = tree.query_pairs(reach, output_type="ndarray")
    rows, cols, vals = [], [], []
    for i in range(len(pts)):  # paires intra-cellule
        d = np.linalg.norm(pts[i][:, None, :] - pts[i][None, :, :], axis=2)
        m = ~np.eye(len(pts[i]), dtype=bool)
        rows.append(i)
        cols.append(i)
        vals.append(float(np.exp(-d[m] / length_km).mean()) if m.any() else 1.0)
    for i, j in pairs:
        d = np.linalg.norm(pts[i][:, None, :] - pts[j][None, :, :], axis=2)
        v = float(np.where(d <= cutoff * length_km, np.exp(-d / length_km), 0.0).mean())
        if v > 0:
            rows += [i, j]
            cols += [j, i]
            vals += [v, v]
    n = len(pts)
    return sparse.csr_matrix((vals, (rows, cols)), shape=(n, n))


def cached_kernel(ctx: StageContext, mesh: Mesh, length_km: float, cutoff: float) -> sparse.csr_matrix:
    """Noyau de liens du maillage, calculé une fois par (L, coupure) et conservé dans le run."""
    name = f"fields/{mesh.mesh_id}/network_kernel__L{length_km:g}_c{cutoff:g}.npz"
    path = ctx.run_dir / name
    if path.exists():
        return sparse.load_npz(io.BytesIO(path.read_bytes())).tocsr()
    kernel = network_kernel(mesh, length_km, cutoff)
    buf = io.BytesIO()
    sparse.save_npz(buf, kernel)
    artifacts.write_bytes(ctx.run_dir, name, buf.getvalue())
    return kernel


def _composition(ctx: StageContext, mesh_id: str, ontology_id: str) -> tuple[np.ndarray, list[str]]:
    data = np.load(io.BytesIO((ctx.run_dir / "fields" / mesh_id / f"composition__{ontology_id}.npz").read_bytes()))
    return data["samples"].astype(np.float64), [str(c) for c in data["categories"]]


def _summary(uv: Any) -> dict[str, float] | None:
    if uv is None:
        return None
    return {"mean": float(uv.mean), "lower": float(uv.lower), "upper": float(uv.upper)}


def status_quo_partition(ctx: StageContext, mesh: Mesh) -> Partition:
    """Partition du statu quo déclaré sur ``mesh``, frontière entre États selon le régime du run."""
    sq = ctx.manifest.status_quo
    if sq is None:
        raise ConfigurationError("aucun statu quo déclaré dans ce run")
    polygons: dict[str, list[Any]] = {}
    for lv in sq.levels:
        if lv.from_source:
            polygons[lv.from_source] = [o for o in read_observations(ctx.observations_path(lv.from_source))
                                        if o.variable_id == lv.variable_id and o.support_type in
                                        (SupportType.ADMIN, SupportType.POLYGON)]
    return build_partition(sq, mesh, ctx.manifest.constitutional_regime, polygons)


def social_state(ctx: StageContext, mesh: Mesh, ontology_id: str, population: np.ndarray,
                 kernel: sparse.csr_matrix) -> tuple[SocialState, float]:
    """État social gelé d'une ontologie : effectifs par groupe, noyaux, qualité déclarée ; part non attribuée."""
    m = ctx.manifest.dfi_model
    if m is None:
        raise ConfigurationError("aucun modèle D/F/I dans ce run")
    shares, cats = _composition(ctx, mesh.mesh_id, ontology_id)
    groups = [c for c in cats if c != UNMAPPED]
    idx = [cats.index(g) for g in groups]
    unmapped = float(shares[..., cats.index(UNMAPPED)].mean()) if UNMAPPED in cats else 0.0
    counts = population[:, :, None] * shares[..., idx]
    state = SocialState(
        ontology_id=ontology_id, cell_ids=list(mesh.cells), groups=groups, population=counts,
        ties={FragChannel.NETWORK: kernel}, exposure={IntegChannel.SPATIAL: kernel},
        quality={c: np.full((len(groups), len(groups)), q) for c, q in m.integration_quality.items()},
        assumptions=["qualité des contacts supposée uniforme", "population et composition indépendantes"])
    return state, unmapped


def dfi(ctx: StageContext, mesh_id: str) -> dict[str, Any]:
    m = ctx.manifest.dfi_model
    sq = ctx.manifest.status_quo
    if m is None or sq is None:
        raise ConfigurationError("aucun modèle D/F/I dans ce run")
    mesh = artifacts.read_mesh(ctx.run_dir, mesh_id)
    partition = status_quo_partition(ctx, mesh)
    institutions = build_institutions(sq, partition)
    kernel = cached_kernel(ctx, mesh, m.network_kernel_length_km, m.network_kernel_cutoff)
    population = fields_mod.read_field(ctx.run_dir, mesh_id)[2].astype(np.float64)  # (S, N)
    weights = ctx.manifest.normative_manifest.connection_weights.as_channels()
    rights = ctx.manifest.normative_manifest.rights
    per_ontology: dict[str, Any] = {}
    for ont in ctx.manifest.ontology_set:
        ctx.check_stop(f"dfi {mesh_id} {ont.ontology_id}")
        state, unmapped = social_state(ctx, mesh, ont.ontology_id, population, kernel)
        groups = state.groups
        frag = fragmentation(state, partition)
        integ = integration(state, partition, weights)
        dom = domination(state, partition, institutions, rights)
        align = alignment(state, partition)
        rri: dict[str, Any] = {"status": "CAUSAL_EFFECT_UNKNOWN"}
        if m.reification is not None:
            answer = frozen_library(ctx).query(m.reification.effect, ctx.manifest.request.region)
            if answer.known:
                # Statu quo comparé à lui-même (NO_TERRITORIAL_CHANGE) : Δ = 0 par construction.
                iv = answer.interval()
                rec = frozen_library(ctx).record(m.reification.effect)
                resp = BoundedSalienceResponse(iv.lo, iv.hi, rec.time_horizon_years, rec.source_ids[0])
                r = resp.salience_response(0.0, m.reification.horizon_years)
                rri = {"status": "BOUNDED", "baseline": "status_quo", "interval": [r.lower, r.upper],
                       "effect": m.reification.effect, "admissibility": answer.status,
                       "grade": None if answer.grade is None else answer.grade.value}
        by_domain: dict[str, Any] = {}
        for d in dom:
            cur = by_domain.setdefault(d.domain.value, {"max_p_exceed": 0.0, "violations": 0, "urgent": 0,
                                                        "realized": "UNKNOWN"})
            cur["max_p_exceed"] = max(cur["max_p_exceed"], d.p_exceed)
            cur["violations"] += int(d.violation)
            cur["urgent"] += int(d.urgent)
            if d.realized is not None:
                cur["realized"] = "OBSERVED"
        known_f = [f for f in frag if f.value is not None]
        pop_g = state.population.sum(axis=1).mean(axis=0)
        f_net = {f.group: f.value.mean for f in known_f if f.channel is FragChannel.NETWORK}  # type: ignore[union-attr]
        per_ontology[ont.ontology_id] = {
            "groups": groups, "unmapped_share": unmapped,
            "fragmentation": {f"{f.group}|{f.channel.value}": _summary(f.value) for f in frag},
            "unknown_fragmentation_channels": sorted({f.channel.value for f in frag if f.value is None}),
            "integration": {
                "j_conn": _summary(integ.j_conn),
                "unknown_channels": [c.value for c in integ.unknown_channels],
                "channels": {c.value: {"intergroup_share_of_contact": _summary(v["intergroup_share_of_contact"]),
                                       "cut_share_of_intergroup": _summary(v["cut_share_of_intergroup"])}
                             for c, v in integ.channels.items()},
            },
            "domination": {"by_domain": by_domain, "violations": sum(int(d.violation) for d in dom),
                           "urgent": sum(int(d.urgent) for d in dom), "estimates": len(dom),
                           "realized_component": "UNKNOWN (aucune observation de discrimination)"},
            "alignment": _summary(align),
            "reification": rri,
            "headline": {
                "j_conn": float(integ.j_conn.mean or 0.0) if integ.j_conn else 0.0,
                "f_network_popweighted": float(sum(f_net[g] * pop_g[i] for i, g in enumerate(groups))
                                               / max(pop_g.sum(), 1e-12)),
                "max_p_exceed": max((d.p_exceed for d in dom), default=0.0),
            },
        }
    out = {"mesh_id": mesh_id, "status_quo": sq.status_quo_id,
           "regime": ctx.manifest.constitutional_regime.regime_id.value,
           "privacy_class": PrivacyClass.CONTROLLED.value, "evidence_status": EvidenceStatus.MODEL.value,
           "jurisdictions": {lv.name: len(lv.jurisdictions) for lv in partition.levels},
           "ontologies": per_ontology}
    artifacts.write_json(ctx.run_dir, f"fields/{mesh_id}/dfi.json", out)
    freeze = artifacts.read_json(ctx.run_dir, "measurement_freeze.json")
    record = ProvenanceRecord.create(
        "dfi.evaluate_status_quo",
        [f"measurement_freeze:{freeze['freeze_hash']}", f"dfi:{m.content_hash}", f"status_quo:{sq.content_hash}",
         f"normative:{ctx.manifest.normative_manifest_hash}"],
        [f"dfi:{mesh_id}:{content_hash(out)}"], run_id=ctx.manifest.run_id)
    artifacts.write_provenance(ctx.run_dir, [record])
    ctx.repo.record_provenance([record])
    total_viol = sum(v["domination"]["violations"] for v in per_ontology.values())
    return {"count": len(per_ontology), "detail": f"violations={total_viol}"}


def _relative_gap(a: float, b: float, floor: float) -> float:
    return abs(a - b) / max(abs(a), abs(b), floor)


def _raw_gaps(heads: dict[str, dict[str, float]], keys: tuple[str, ...], floor: float) -> dict[str, Any]:
    """Écarts bruts : relatifs sans plancher et absolus, avec drapeau « sous le plancher »."""
    out = {}
    for k in keys:
        vals = [h[k] for h in heads.values()]
        hi, lo = max(vals), min(vals)
        out[k] = {"absolute": hi - lo, "relative": (hi - lo) / hi if hi > 0 else 0.0,
                  "below_floor": hi < floor}
    return out


def dfi_ensemble(ctx: StageContext, _: str) -> dict[str, Any]:
    """S^ontology et S^scale sur les quantités D/F/I principales (1 − écart relatif maximal)."""
    m = ctx.manifest.dfi_model
    assert m is not None
    per_mesh = {d.mesh_id: artifacts.read_json(ctx.run_dir, f"fields/{d.mesh_id}/dfi.json")
                for d in ctx.manifest.mesh_set}
    keys = ("j_conn", "f_network_popweighted", "max_p_exceed")
    s_ont = {}
    for mid, v in per_mesh.items():
        heads = {o: x["headline"] for o, x in v["ontologies"].items()}
        gaps = [_relative_gap(heads[a][k], heads[b][k], m.relative_floor)
                for a, b in combinations(sorted(heads), 2) for k in keys]
        s_ont[mid] = 1.0 - max(gaps, default=0.0)
    s_scale = {}
    ontologies = sorted(next(iter(per_mesh.values()))["ontologies"])
    for o in ontologies:
        gaps = [_relative_gap(per_mesh[a]["ontologies"][o]["headline"][k],
                              per_mesh[b]["ontologies"][o]["headline"][k], m.relative_floor)
                for a, b in combinations(sorted(per_mesh), 2) for k in keys]
        s_scale[o] = 1.0 - max(gaps, default=0.0)
    raw_scale = {o: _raw_gaps({mid: per_mesh[mid]["ontologies"][o]["headline"] for mid in per_mesh},
                              keys, m.relative_floor) for o in ontologies}
    result = {"s_ontology_dfi_by_mesh": s_ont, "s_ontology_dfi": min(s_ont.values()),
              "s_scale_dfi_by_ontology": s_scale, "s_scale_dfi": min(s_scale.values()),
              "scale_gaps_raw": raw_scale,
              "headline_keys": list(keys), "relative_floor": m.relative_floor}
    artifacts.write_json(ctx.run_dir, "artifacts/dfi_ensemble.json", result)
    return {"detail": f"S_ont={result['s_ontology_dfi']:.2f} S_scale={result['s_scale_dfi']:.2f}"}
