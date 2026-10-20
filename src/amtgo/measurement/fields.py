"""Champs latents (schéma 10 §4) : moyenne, incertitude, tirages, provenance, calculabilité.

Statut de preuve : toujours MODEL (prompt §11 — un champ fusionné n'est jamais
une observation directe). Classe d'accès : la plus restrictive des sources.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from amtgo.core.enums import ComputabilityClass, EvidenceStatus, PrivacyClass
from amtgo.measurement.engine import FitResult, summarize
from amtgo.measurement.manifest import ComputabilitySpec, MeasurementManifest
from amtgo.runs.state import write_json_atomic
from amtgo.utils.canonical import stable_uuid

_SCHEMA = pa.schema([
    ("cell_id", pa.string()),
    ("mean", pa.float64()),
    ("sd", pa.float64()),
    ("lower", pa.float64()),
    ("upper", pa.float64()),
    ("information_ratio", pa.float64()),
    ("negative_fraction", pa.float64()),
    ("computability", pa.string()),
])


def cell_class(info: float, neg: float, spec: ComputabilitySpec) -> ComputabilityClass:
    if neg > spec.max_negative_sample_fraction:
        # Le modèle gaussien produit des populations négatives ici : mal spécifié localement.
        return ComputabilityClass.D
    if info >= spec.a_min:
        return ComputabilityClass.A
    if info >= spec.b_min:
        return ComputabilityClass.B
    if info >= spec.c_min:
        return ComputabilityClass.C
    return ComputabilityClass.D


_ORDER = [ComputabilityClass.D, ComputabilityClass.C, ComputabilityClass.B, ComputabilityClass.A]


def zone_class(classes: list[ComputabilityClass]) -> ComputabilityClass:
    """Classe de zone : classe médiane des cellules (aucune moyenne n'efface une zone D)."""
    if not classes:
        return ComputabilityClass.D
    ranks = sorted(_ORDER.index(c) for c in classes)
    return _ORDER[ranks[(len(ranks) - 1) // 2]]  # médiane basse : conservatrice


@dataclass(frozen=True)
class LatentFieldMeta:
    field_id: str
    mesh_id: str
    cells_hash: str
    variable_id: str
    period: dict[str, str]
    measurement_hash: str
    model_version: str
    evidence_status: EvidenceStatus
    privacy_class: PrivacyClass
    computability: ComputabilityClass
    used: dict[str, int]
    excluded: dict[str, int]
    total: dict[str, float]
    median_information_ratio: float
    misspecified_cells: int
    cells: int
    samples_hash: str
    laplace: dict[str, Any] | None

    def as_dict(self) -> dict[str, Any]:
        d = dict(self.__dict__)
        for k in ("evidence_status", "privacy_class", "computability"):
            d[k] = d[k].value
        return d


def build_field(fit_result: FitResult, mesh_id: str, cells_hash: str, manifest: MeasurementManifest,
                inputs_hash: str, privacy: PrivacyClass, run_id: str
                ) -> tuple[LatentFieldMeta, list[dict[str, Any]]]:
    post, sel, idx = fit_result.posterior, fit_result.selection, fit_result.index
    level = manifest.sampling.interval_level
    alpha = (1.0 - level) / 2.0
    lo = np.quantile(post.samples, alpha, axis=0)
    hi = np.quantile(post.samples, 1 - alpha, axis=0)
    info, neg = post.information_ratio, post.negative_fraction
    rows, classes = [], []
    for k, cid in enumerate(idx.ids):
        c = cell_class(float(info[k]), float(neg[k]), manifest.computability)
        classes.append(c)
        rows.append({"cell_id": cid, "mean": float(post.mean[k]), "sd": float(np.sqrt(post.var[k])),
                     "lower": float(lo[k]), "upper": float(hi[k]), "information_ratio": float(info[k]),
                     "negative_fraction": float(neg[k]), "computability": c.value})
    if fit_result.laplace is not None and not fit_result.laplace.converged:
        # Approximation de Laplace sans mode convergé : aucune conclusion de mesure.
        classes = [ComputabilityClass.D] * len(classes)
        for r in rows:
            r["computability"] = ComputabilityClass.D.value
    mean, sd, tlo, thi = summarize(post.samples.sum(axis=1), level)
    samples32 = post.samples.astype(np.float32)
    meta = LatentFieldMeta(
        # Un champ appartient à un run : deux runs aux entrées identiques ont deux champs.
        field_id=str(stable_uuid("latent_field", {"in": inputs_hash, "mesh": cells_hash,
                                                  "m": manifest.content_hash, "run": run_id})),
        mesh_id=mesh_id, cells_hash=cells_hash, variable_id=manifest.variable_id,
        period={"start": manifest.target_period.start.isoformat(),
                "end": manifest.target_period.end.isoformat()},
        measurement_hash=manifest.content_hash, model_version=f"{manifest.model_id}@{manifest.version}",
        evidence_status=EvidenceStatus.MODEL, privacy_class=privacy, computability=zone_class(classes),
        used=dict(sorted(sel.used.items())), excluded=dict(sorted(sel.excluded.items())),
        total={"mean": mean, "sd": sd, "lower": tlo, "upper": thi, "level": level},
        median_information_ratio=float(np.median(info)),
        misspecified_cells=int((neg > manifest.computability.max_negative_sample_fraction).sum()),
        cells=len(idx.ids),
        laplace=None if fit_result.laplace is None else dict(fit_result.laplace.__dict__),
        # Empreinte locale à la machine : BLAS/LAPACK peuvent différer au dernier bit entre
        # processeurs. La reproductibilité inter-machines se juge sur les résumés (tolérance).
        samples_hash="sha256:" + hashlib.sha256(np.round(samples32, 1).tobytes()).hexdigest(),
    )
    return meta, rows


def write_field(run_dir: Path, meta: LatentFieldMeta, rows: list[dict[str, Any]], samples: np.ndarray) -> Path:
    d = run_dir / "fields" / meta.mesh_id
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "cells.parquet.part"
    pq.write_table(pa.Table.from_pylist(rows, schema=_SCHEMA), tmp)
    tmp.replace(d / "cells.parquet")
    tmp_npy = d / "samples.npy.part"
    with tmp_npy.open("wb") as fh:
        np.save(fh, samples.astype(np.float32))
    tmp_npy.replace(d / "samples.npy")
    write_json_atomic(d / "field.json", json.dumps(meta.as_dict(), indent=2, ensure_ascii=False))
    return d


def read_field(run_dir: Path, mesh_id: str) -> tuple[dict[str, Any], list[dict[str, Any]], np.ndarray]:
    d = run_dir / "fields" / mesh_id
    meta = json.loads((d / "field.json").read_text(encoding="utf-8"))
    rows = pq.read_table(d / "cells.parquet").to_pylist()
    return meta, rows, np.load(d / "samples.npy")
