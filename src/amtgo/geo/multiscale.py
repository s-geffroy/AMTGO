"""Opérations multi-échelles (M2) : transferts entre maillages et distance de partitions.

Tout se calcule en projection équivalente. Deux briques :

- ``area_weighted_transfer`` : réaffecte une variable *extensive* (un compte)
  d'un maillage à l'autre au prorata des surfaces d'intersection. La masse non
  couverte par le maillage cible est rapportée, jamais redistribuée en silence.
- ``partition_distance`` : distance dans [0,1] entre deux partitions portées par
  des maillages différents, évaluée sur une grille de référence commune
  (ADR-0007). Elle fonde S_scale = 1 − E[d] (02 §6), calculé à partir de M8.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

import networkx as nx
from shapely.geometry.base import BaseGeometry
from shapely.strtree import STRtree

from amtgo.geo.crs import M2_PER_KM2, to_equal_area
from amtgo.geo.mesh import Mesh


@dataclass(frozen=True)
class TransferResult:
    values: dict[str, float]
    total_in: float
    total_out: float
    unallocated: float  # masse tombée hors du maillage cible


def _projected(mesh: Mesh) -> tuple[list[str], list[BaseGeometry]]:
    ids = list(mesh.cells)
    return ids, [to_equal_area(mesh.cells[c].geometry) for c in ids]


def area_weighted_transfer(values: dict[str, float], src: Mesh, dst: Mesh) -> TransferResult:
    src_ids, src_geoms = _projected(src)
    dst_ids, dst_geoms = _projected(dst)
    tree = STRtree(dst_geoms)
    out: dict[str, float] = defaultdict(float)
    total_in = 0.0
    unallocated = 0.0
    for sid, sgeom in zip(src_ids, src_geoms, strict=True):
        v = values.get(sid, 0.0)
        if v == 0.0:
            continue
        total_in += v
        allocated = 0.0
        for k in tree.query(sgeom, predicate="intersects"):
            frac = sgeom.intersection(dst_geoms[k]).area / sgeom.area
            if frac > 0:
                out[dst_ids[k]] += v * frac
                allocated += v * frac
        unallocated += v - allocated
    return TransferResult(dict(sorted(out.items())), total_in, sum(out.values()), unallocated)


def _labels_on_reference(labels: dict[str, str], mesh: Mesh, ref: Mesh) -> dict[str, str]:
    """Étiquette de chaque cellule de référence : celle de la cellule contenant son centre."""
    ids, geoms = _projected(mesh)
    tree = STRtree(geoms)
    out: dict[str, str] = {}
    for rid, rcell in ref.cells.items():
        centre = to_equal_area(rcell.geometry).centroid
        hits = tree.query(centre, predicate="within")
        if len(hits) == 0:
            # Centre sur une arête partagée : on cède à « intersects », choix le plus petit id.
            hits = tree.query(centre, predicate="intersects")
        if len(hits) == 0:
            continue
        cid = min(ids[k] for k in hits)
        if cid in labels:
            out[rid] = labels[cid]
    return out


class PartitionMetric(StrEnum):
    """Distance entre partitions (ADR-0007).

    TRANSFER : part minimale de surface à réaffecter, après le meilleur
    appariement des étiquettes — interprétable, métrique par défaut de S_scale.
    VI : variation d'information normalisée par l'entropie jointe — plus
    sévère aux bords, conservée comme variante de sensibilité.
    """

    TRANSFER = "transfer"
    VI = "vi"


@dataclass(frozen=True)
class PartitionDistance:
    distance: float  # dans [0,1]
    metric: PartitionMetric
    coverage_km2: float  # surface de référence où les deux partitions sont définies
    reference_mesh_id: str


def _joint_table(
    labels_a: dict[str, str], mesh_a: Mesh, labels_b: dict[str, str], mesh_b: Mesh, ref: Mesh
) -> dict[tuple[str, str], float]:
    la = _labels_on_reference(labels_a, mesh_a, ref)
    lb = _labels_on_reference(labels_b, mesh_b, ref)
    joint: dict[tuple[str, str], float] = defaultdict(float)
    for rid in sorted(set(la) & set(lb)):
        joint[(la[rid], lb[rid])] += ref.cells[rid].area_km2
    return joint


def _vi_normalized(joint: dict[tuple[str, str], float], total: float) -> float:
    pa: dict[str, float] = defaultdict(float)
    pb: dict[str, float] = defaultdict(float)
    for (a, b), w in joint.items():
        pa[a] += w
        pb[b] += w

    def h(weights: Iterable[float]) -> float:
        return -sum((w / total) * math.log(w / total) for w in weights if w > 0)

    h_joint = h(joint.values())
    if h_joint == 0.0:
        return 0.0
    vi = 2.0 * h_joint - h(pa.values()) - h(pb.values())
    return max(0.0, min(1.0, vi / h_joint))


def _transfer(joint: dict[tuple[str, str], float], total: float) -> float:
    graph = nx.Graph()
    for (a, b), w in joint.items():
        graph.add_edge(("a", a), ("b", b), weight=w)
    matching = nx.max_weight_matching(graph)
    matched = float(sum(graph[u][v]["weight"] for u, v in matching))
    return max(0.0, min(1.0, 1.0 - matched / total))


def partition_distance(
    labels_a: dict[str, str],
    mesh_a: Mesh,
    labels_b: dict[str, str],
    mesh_b: Mesh,
    ref: Mesh,
    metric: PartitionMetric = PartitionMetric.TRANSFER,
) -> PartitionDistance:
    """Distance aire-pondérée entre deux partitions portées par des maillages quelconques.

    Chaque cellule de ``ref`` reçoit l'étiquette de la cellule qui contient son
    centre, dans chaque partition. 0 : partitions identiques à la grille de
    référence près ; les étiquettes elles-mêmes n'importent pas.
    """
    joint = _joint_table(labels_a, mesh_a, labels_b, mesh_b, ref)
    total = sum(joint.values())
    if total == 0:
        return PartitionDistance(math.nan, metric, 0.0, ref.mesh_id)
    d = _transfer(joint, total) if metric is PartitionMetric.TRANSFER else _vi_normalized(joint, total)
    return PartitionDistance(d, metric, total, ref.mesh_id)


def coverage_ratio(mesh: Mesh) -> float:
    """Part de l'emprise couverte par l'union des cellules (règle du centre ⇒ ≠ 1 aux bords)."""
    extent = to_equal_area(mesh.extent).area
    covered = to_equal_area(mesh.union()).intersection(to_equal_area(mesh.extent)).area
    return covered / extent if extent else math.nan


__all__ = [
    "M2_PER_KM2",
    "PartitionDistance",
    "PartitionMetric",
    "TransferResult",
    "area_weighted_transfer",
    "coverage_ratio",
    "partition_distance",
]
