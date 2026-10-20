"""Ontologies concurrentes (prompt §17, schéma 10 §5-6, 03 §9).

Il n'existe **aucune** classification canonique. Une ontologie est un objet
produit par quelqu'un, dans un but, selon une méthode, à une époque ; plusieurs
coexistent et un même calcul est exécuté sous chacune.

Dimensions strictement séparées (prompt §21) : une ontologie ne porte que sur une
dimension, et aucun crosswalk ne relie deux dimensions différentes — identité
ethnoculturelle, nationale et territoriale ne se déduisent pas les unes des autres.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from amtgo.config.loader import load_model
from amtgo.core.enums import EvidenceStatus
from amtgo.data.sources import HistoricalContext
from amtgo.errors import OntologyMappingError
from amtgo.utils.canonical import content_hash


class IdentityDimension(StrEnum):
    ETHNOCULTURAL = "ethnocultural"
    NATIONAL = "national"
    TERRITORIAL = "territorial"
    LANGUAGE = "language"
    RELIGION = "religion"


class OntologyKind(StrEnum):
    SELF_IDENTIFICATION = "self_identification"  # catégories déclarées par les personnes
    EXTERNAL_CLASSIFICATION = "external_classification"  # catégories attribuées de l'extérieur
    HISTORICAL = "historical"  # classification historique (carte ethnographique, recensement colonial…)
    LINGUISTIC_GENEALOGY = "linguistic_genealogy"  # inventaire / généalogie (type Glottolog)
    ADMINISTRATIVE = "administrative"  # catégories d'un recensement national


class LanguageFunction(StrEnum):
    """Profil fonctionnel d'une langue (prompt §20). Il n'existe pas de « langue principale »."""

    NATIVE = "native"
    HOME = "home"
    DAILY = "daily"
    INTERGROUP = "intergroup"
    ADMINISTRATIVE = "administrative"
    EDUCATION = "education"


# Concept réservé : masse de probabilité qu'un crosswalk n'attribue à aucun concept cible.
UNMAPPED = "__unmapped__"


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class OntologyConcept(_Strict):
    concept_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_\-]{0,63}$")
    source_label: str
    definition: str
    parent_id: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    self_identified: bool | None = None
    external_label: bool | None = None


class Ontology(_Strict):
    ontology_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_]{1,63}$")
    version: str
    name: str
    dimension: IdentityDimension
    kind: OntologyKind
    description: str
    evidence_status: EvidenceStatus
    source_ids: tuple[str, ...] = ()
    historical_context: HistoricalContext | None = None
    concepts: tuple[OntologyConcept, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _coherence(self) -> Self:
        ids = [c.concept_id for c in self.concepts]
        if len(set(ids)) != len(ids):
            raise ValueError(f"{self.ontology_id} : concepts dupliqués")
        if UNMAPPED in ids:
            raise ValueError(f"{UNMAPPED} est réservé")
        known = set(ids)
        parents = {c.concept_id: c.parent_id for c in self.concepts}
        for c in self.concepts:
            if c.parent_id is not None and c.parent_id not in known:
                raise ValueError(f"{self.ontology_id}/{c.concept_id} : parent inconnu {c.parent_id}")
        for cid in ids:  # hiérarchie acyclique
            seen: set[str] = set()
            cur: str | None = cid
            while cur is not None:
                if cur in seen:
                    raise ValueError(f"{self.ontology_id} : cycle hiérarchique via {cid}")
                seen.add(cur)
                cur = parents[cur]
        if self.kind is OntologyKind.HISTORICAL:
            if self.historical_context is None:
                raise ValueError(f"{self.ontology_id} : ontologie historique sans contexte (01 §29)")
            if self.evidence_status is not EvidenceStatus.HISTORICAL:
                raise ValueError(f"{self.ontology_id} : une ontologie historique a le statut H")
        if self.kind is OntologyKind.SELF_IDENTIFICATION and any(c.self_identified is False for c in self.concepts):
            raise ValueError(f"{self.ontology_id} : concept non auto-déclaré dans une ontologie d'auto-identification")
        return self

    @property
    def concept_ids(self) -> list[str]:
        return [c.concept_id for c in self.concepts]

    @property
    def leaf_ids(self) -> list[str]:
        """Concepts sans enfant : les catégories effectivement mesurées."""
        parents = {c.parent_id for c in self.concepts if c.parent_id}
        return [c for c in self.concept_ids if c not in parents]

    @property
    def content_hash(self) -> str:
        return content_hash(self)


class CrosswalkRow(_Strict):
    source_concept: str
    # P(cible | source) ; la masse non attribuée va explicitement à UNMAPPED.
    targets: dict[str, float]
    # Concentration de Dirichlet : force de la preuve qui fonde la ligne (prompt §17).
    concentration: float = Field(gt=0)
    evidence: str


class OntologyCrosswalk(_Strict):
    crosswalk_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_]{1,63}$")
    version: str
    source_ontology: str
    target_ontology: str
    description: str
    evidence_status: EvidenceStatus
    rows: tuple[CrosswalkRow, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _probabilities(self) -> Self:
        for row in self.rows:
            for t, p in row.targets.items():
                if not 0.0 <= p <= 1.0:
                    raise ValueError(f"{self.crosswalk_id}/{row.source_concept}→{t} : probabilité hors [0,1]")
            total = sum(row.targets.values())
            if abs(total - 1.0) > 1e-6:
                raise ValueError(
                    f"{self.crosswalk_id}/{row.source_concept} : somme {total:.6f} ≠ 1 "
                    f"(la masse non attribuée doit être déclarée sous {UNMAPPED})")
        if len({r.source_concept for r in self.rows}) != len(self.rows):
            raise ValueError(f"{self.crosswalk_id} : concept source dupliqué")
        if self.evidence_status is EvidenceStatus.DIRECT:
            # Une correspondance entre classifications est toujours un modèle ou un proxy.
            raise ValueError(f"{self.crosswalk_id} : un crosswalk ne peut pas être DIRECT")
        return self

    def check_against(self, source: Ontology, target: Ontology) -> None:
        """Vérifie le crosswalk contre ses deux ontologies. Lève OntologyMappingError."""
        if source.ontology_id != self.source_ontology or target.ontology_id != self.target_ontology:
            raise OntologyMappingError(f"{self.crosswalk_id} : ontologies inattendues")
        if source.dimension is not target.dimension:
            raise OntologyMappingError(
                f"{self.crosswalk_id} : {source.dimension.value} → {target.dimension.value} interdit "
                "(aucun mapping automatique entre dimensions, prompt §21)")
        leaves = set(source.leaf_ids)
        covered = {r.source_concept for r in self.rows}
        if covered != leaves:
            raise OntologyMappingError(
                f"{self.crosswalk_id} : lignes {sorted(covered)} ≠ concepts feuilles {sorted(leaves)}")
        allowed = set(target.leaf_ids) | {UNMAPPED}
        for row in self.rows:
            unknown = set(row.targets) - allowed
            if unknown:
                raise OntologyMappingError(f"{self.crosswalk_id}/{row.source_concept} : cibles inconnues {unknown}")

    @property
    def content_hash(self) -> str:
        return content_hash(self)


def load_ontology(path: Path) -> Ontology:
    return load_model(Ontology, path)


def load_crosswalk(path: Path) -> OntologyCrosswalk:
    return load_model(OntologyCrosswalk, path)
