"""Statu quo déclaré : partition existante et institutions, pour l'évaluation D/F/I (M5).

Le statu quo est une **donnée** (STATUS_QUO, prompt §78), jamais une
recommandation ni un candidat généré : il sert de baseline. Les niveaux sont
définis par des polygones d'une source (ex. districts d'un recensement) et par
regroupement (ex. États). La frontière entre États suit le gabarit du régime
constitutionnel du run.
"""

from __future__ import annotations

from typing import Literal, Self

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator
from shapely.strtree import STRtree

from amtgo.data.observations import Observation
from amtgo.errors import ConfigurationError, TopologyError
from amtgo.geo.crs import to_equal_area
from amtgo.geo.mesh import Mesh
from amtgo.geo.partition import BorderDim, BorderVector, Partition, PartitionLevel
from amtgo.institutions.competences import (
    CompetenceVector,
    DecisionRule,
    Domain,
    Institution,
    Representation,
    RightsProfile,
    check_exclusive,
)
from amtgo.institutions.regimes import ConstitutionalRegime
from amtgo.utils.canonical import content_hash


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class LevelSpec(_Strict):
    name: str
    from_source: str | None = None
    variable_id: str | None = None
    group_of: str | None = None
    groups: dict[str, tuple[str, ...]] = Field(default_factory=dict)  # juridiction → préfixes
    border: dict[str, float] | Literal["regime"]

    @model_validator(mode="after")
    def _one_kind(self) -> Self:
        if (self.from_source is None) == (self.group_of is None):
            raise ValueError(f"niveau {self.name} : from_source XOR group_of")
        return self


class InstitutionTemplate(_Strict):
    competences: dict[Domain, float]
    threshold: float = Field(ge=0.5, lt=1.0)
    rights_default: float = Field(ge=0.0, le=1.0)
    rights: dict[Domain, float] = Field(default_factory=dict)
    representation: Literal["proportional"] = "proportional"


class StatusQuoSpec(_Strict):
    status_quo_id: str
    version: str
    description: str
    levels: tuple[LevelSpec, ...] = Field(min_length=1)  # du plus élevé au plus local
    institutions: dict[str, InstitutionTemplate]

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        names = [lv.name for lv in self.levels]
        if set(self.institutions) != set(names):
            raise ValueError("une institution type par niveau attendue")
        domains = sorted({d for t in self.institutions.values() for d in t.competences})
        # Compétences partagées entre niveaux : exclusives au total (prompt §84).
        check_exclusive([CompetenceVector(authority=t.competences) for t in self.institutions.values()],
                        domains)
        return self

    @property
    def content_hash(self) -> str:
        return content_hash(self)


def _border(spec: dict[str, float] | str, regime: ConstitutionalRegime) -> BorderVector:
    values = regime.border_template if spec == "regime" else spec
    assert isinstance(values, dict)
    try:
        return BorderVector(strength={BorderDim(k): float(v) for k, v in values.items()})
    except ValueError as exc:
        raise ConfigurationError(f"vecteur de frontière invalide : {exc}") from exc


def assign_cells_to_polygons(mesh: Mesh, polygons: list[Observation]) -> tuple[np.ndarray, list[str]]:
    """Affecte chaque cellule (par son centre) au polygone qui le contient, sinon au plus proche.

    Retourne l'indice de polygone par cellule et les codes, triés par ``admin_code``.
    """
    obs = sorted(polygons, key=lambda o: o.admin_code or "")
    geoms = [to_equal_area(g) for o in obs if (g := o.geometry()) is not None]
    if not geoms or len(geoms) != len(obs):
        raise TopologyError("affectation : polygones absents ou sans géométrie")
    tree = STRtree(geoms)
    assign = np.full(len(mesh.cells), -1, dtype=int)
    for k, c in enumerate(mesh.cells.values()):
        pt = to_equal_area(c.geometry).centroid
        hits = tree.query(pt, predicate="within")
        if len(hits) == 0:
            hits = [int(tree.nearest(pt))]
        assign[k] = int(min(hits))
    return assign, [str(o.admin_code) for o in obs]


def build_partition(spec: StatusQuoSpec, mesh: Mesh, regime: ConstitutionalRegime,
                    polygons: dict[str, list[Observation]]) -> Partition:
    """Affecte chaque cellule (par son centre) aux juridictions de chaque niveau."""
    ids = list(mesh.cells)
    assignments: dict[str, tuple[np.ndarray, list[str]]] = {}
    for lv in reversed(spec.levels):  # local d'abord : les regroupements en dépendent
        if lv.from_source is not None:
            if not polygons.get(lv.from_source):
                raise ConfigurationError(f"niveau {lv.name} : aucun polygone de {lv.from_source}")
            assignments[lv.name] = assign_cells_to_polygons(mesh, polygons[lv.from_source])
        else:
            assert lv.group_of is not None
            child_assign, child_names = assignments[lv.group_of]
            names = sorted(lv.groups)
            parent_of = []
            for cn in child_names:
                owners = [j for j, n in enumerate(names) if any(cn.startswith(p) for p in lv.groups[n])]
                if len(owners) != 1:
                    raise TopologyError(f"{cn} : appartient à {len(owners)} juridictions de {lv.name}")
                parent_of.append(owners[0])
            assignments[lv.name] = (np.array(parent_of)[child_assign], names)
    levels = [PartitionLevel(lv.name, assignments[lv.name][0], assignments[lv.name][1],
                             _border(lv.border, regime)) for lv in spec.levels]
    return Partition(mesh.mesh_id, ids, levels)


def build_institutions(spec: StatusQuoSpec, partition: Partition) -> dict[str, list[Institution]]:
    out: dict[str, list[Institution]] = {}
    for lv in partition.levels:
        t = spec.institutions[lv.name]
        out[lv.name] = [Institution(
            jurisdiction_id=j, level=lv.name, competences=CompetenceVector(authority=t.competences),
            decision={}, default_decision=DecisionRule(threshold=t.threshold),
            rights=RightsProfile(checks=t.rights, default=t.rights_default),
            representation=Representation(rule=t.representation)) for j in lv.jurisdictions]
    return out
