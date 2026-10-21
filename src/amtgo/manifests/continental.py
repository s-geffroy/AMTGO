"""Manifeste de coordination continentale (M14 ; 07 §13, 11 phase 10, 02 §33).

Un run continental ne résout **aucun** problème continental monolithique (07 §13) :
il compose des runs régionaux Map-R complets — chacun reste un run ordinaire de la
file, reproductible seul — à travers des couches de coordination déclarées à leurs
interfaces (marché, mobilité, corridors, sécurité ; bassins dès qu'une hydrographie
est ingérée).

Les régions doivent être **commensurables** : même manifeste normatif, même régime,
mêmes ontologies, même optimiseur, même modèle de transition et même noyau de liens,
et des familles de maillage appariables (famille, résolution). Sinon la composition
additionnerait des grandeurs définies différemment : le manifeste est refusé.

Une couche a toujours un coût déclaré strictement positif : une couche gratuite
déplacerait un coût vers le niveau continental sans le compter (05 §14, Goodhart).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from amtgo.causal.library import CausalLibraryManifest
from amtgo.config.loader import load_model, read_yaml
from amtgo.core.enums import MapMode
from amtgo.core.provenance import utcnow
from amtgo.errors import ConfigurationError
from amtgo.manifests.run import RunManifest, RunRequest, resolve_request
from amtgo.scenarios.model import Interval
from amtgo.utils.canonical import content_hash, stable_uuid
from amtgo.utils.code_version import code_commit, code_version

KIND: Literal["continental"] = "continental"


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class LayerType(StrEnum):
    """Couches de fédération des problèmes régionaux (11 phase 10)."""

    BASIN = "basin"
    CORRIDOR = "corridor"
    MARKET = "market"
    SECURITY = "security"
    MIGRATION = "migration"


class LayerTarget(StrEnum):
    CROSS_LINKS = "cross_links"  # μ sur les liens fonctionnels qui traversent l'interface
    BORDER_COST = "border_cost"  # réduction du coût de gestion de la frontière d'interface


class CoordinationLayer(_Strict):
    layer_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_]{1,63}$")
    type: LayerType
    acts_on: LayerTarget
    effect: str  # clé de la bibliothèque causale continentale (μ ou réduction relative)
    band_km: float | None = Field(default=None, gt=0)  # None : toute l'interface
    annual_cost: Interval  # unités des comptes fiscaux régionaux ; PROVISOIRE

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.annual_cost.lo <= 0:
            raise ValueError(f"{self.layer_id} : une couche gratuite déplacerait un coût vers le niveau "
                             "continental sans le compter (Goodhart, 05 §14)")
        if self.type is LayerType.BASIN:
            raise ValueError(f"{self.layer_id} : un bassin exige une hydrographie ingérée ; aucune n'est "
                             "disponible, le bassin n'est pas inventé")
        if self.type is LayerType.SECURITY and self.acts_on is not LayerTarget.BORDER_COST:
            raise ValueError(f"{self.layer_id} : la coordination de sécurité agit sur le coût de frontière")
        if self.acts_on is LayerTarget.BORDER_COST and self.band_km is not None:
            raise ValueError(f"{self.layer_id} : band_km n'a de sens que pour des liens")
        return self


class CoordinationManifest(_Strict):
    model_id: str
    version: str
    description: str
    layers: tuple[CoordinationLayer, ...] = Field(min_length=1)
    max_exhaustive_combinations: int = Field(default=2000, ge=0, le=20000)

    @model_validator(mode="after")
    def _unique(self) -> Self:
        ids = [layer.layer_id for layer in self.layers]
        if len(set(ids)) != len(ids):
            raise ValueError("layer_id dupliqué")
        return self

    @property
    def content_hash(self) -> str:
        return content_hash(self)


class RegionRef(_Strict):
    region_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_]{0,31}$")
    run: str  # requête de run régional, relative à configs/


class ContinentalRequest(_Strict):
    kind: Literal["continental"]
    name: str = Field(pattern=r"^[a-z0-9][a-z0-9_]{1,63}$")
    description: str
    region: str  # contexte de la couche de coordination (bibliothèque causale continentale)
    regions: tuple[RegionRef, ...] = Field(min_length=2)
    coordination_model: str
    causal_library: str


class RegionalRun(_Strict):
    region_id: str
    request: str
    run_id: uuid.UUID
    manifest_hash: str
    context: str  # région de la requête régionale


class ContinentalManifest(_Strict):
    """Manifeste gelé. ``run_id`` dérive du contenu, dont les run_id régionaux."""

    kind: Literal["continental"] = KIND
    run_id: uuid.UUID
    manifest_hash: str
    created_at: datetime
    code_commit: str
    code_version: str
    request: ContinentalRequest
    regions: tuple[RegionalRun, ...]
    coordination_model: CoordinationManifest
    causal_library: CausalLibraryManifest
    normative_manifest_hash: str
    constitutional_regime: str
    constitutional_regime_hash: str


_UNHASHED = {"run_id", "manifest_hash", "created_at"}


def body_hash(m: ContinentalManifest) -> str:
    return content_hash(m.model_dump(mode="json", exclude=_UNHASHED))


def is_continental(path: Path) -> bool:
    data = read_yaml(path)
    return isinstance(data, dict) and data.get("kind") == KIND


def _same(regionals: dict[str, RunManifest], what: str, key: object) -> None:
    values = {rid: key(m) for rid, m in regionals.items()}  # type: ignore[operator]
    if len(set(map(repr, values.values()))) > 1:
        raise ConfigurationError(f"régions non commensurables : {what} diffère ({sorted(values)})")


def mesh_pairing(regionals: dict[str, RunManifest]) -> dict[str, dict[str, str]]:
    """Appariement des maillages par (famille, résolution) : pair_id → {région → mesh_id}."""
    by_region = {rid: {f"{d.family.value}_r{d.resolution}": d.mesh_id for d in m.mesh_set}
                 for rid, m in regionals.items()}
    keys = {frozenset(v) for v in by_region.values()}
    if len(keys) != 1:
        raise ConfigurationError("régions non commensurables : familles de maillage non appariables "
                                 f"({ {r: sorted(v) for r, v in by_region.items()} })")
    return {p: {rid: by_region[rid][p] for rid in by_region} for p in sorted(next(iter(keys)))}


def check_regionals(regionals: dict[str, RunManifest]) -> None:
    for rid, m in regionals.items():
        if m.request.map_mode is not MapMode.R or m.transition_model is None:
            raise ConfigurationError(f"région {rid} : la coordination continentale compose des produits Map-R "
                                     "(trajectoires depuis le statu quo)")
        if m.optimizer_model is None or m.dfi_model is None:
            raise ConfigurationError(f"région {rid} : archive de Pareto et D/F/I requis")
    if len({m.request.region for m in regionals.values()}) != len(regionals):
        raise ConfigurationError("deux régions déclarent le même contexte : la population serait comptée deux fois")
    _same(regionals, "le manifeste normatif", lambda m: m.normative_manifest_hash)
    _same(regionals, "le régime constitutionnel", lambda m: m.constitutional_regime_hash)
    _same(regionals, "l'optimiseur", lambda m: m.optimizer_model.content_hash)
    _same(regionals, "le modèle de transition", lambda m: m.transition_model.content_hash)
    _same(regionals, "le noyau de liens", lambda m: (m.dfi_model.network_kernel_length_km,
                                                     m.dfi_model.network_kernel_cutoff))
    _same(regionals, "les ontologies", lambda m: sorted(
        (o.ontology_id, sorted(c.concept_id for c in o.concepts)) for o in m.ontology_set))
    mesh_pairing(regionals)


def resolve_continental(request: ContinentalRequest, configs_dir: Path) -> tuple[ContinentalManifest,
                                                                                 dict[str, Path]]:
    """Gèle la requête ; renvoie aussi le chemin de chaque requête régionale (à soumettre avant)."""
    ids = [r.region_id for r in request.regions]
    if len(set(ids)) != len(ids):
        raise ConfigurationError("region_id dupliqué")
    paths = {r.region_id: configs_dir / r.run for r in request.regions}
    regionals = {rid: resolve_request(load_model(RunRequest, p), configs_dir) for rid, p in paths.items()}
    check_regionals(regionals)
    coordination = load_model(CoordinationManifest, configs_dir / request.coordination_model)
    library = load_model(CausalLibraryManifest, configs_dir / request.causal_library)
    if library.estimations:
        raise ConfigurationError("bibliothèque continentale : aucune estimation n'est possible sans panel "
                                 "continental ; seuls des effets déclarés (I6/I7) sont admis")
    declared = {d.effect_key: d for d in library.declared}
    for layer in coordination.layers:
        if layer.effect not in declared:
            raise ConfigurationError(f"couche {layer.layer_id} : effet {layer.effect} absent de la bibliothèque")
    first = next(iter(regionals.values()))
    body = {
        "code_commit": code_commit(), "code_version": code_version(), "request": request,
        "regions": tuple(RegionalRun(region_id=rid, request=r.run, run_id=regionals[rid].run_id,
                                     manifest_hash=regionals[rid].manifest_hash,
                                     context=regionals[rid].request.region)
                         for rid, r in zip(ids, request.regions, strict=True)),
        "coordination_model": coordination, "causal_library": library,
        "normative_manifest_hash": first.normative_manifest_hash,
        "constitutional_regime": first.constitutional_regime.regime_id.value,
        "constitutional_regime_hash": first.constitutional_regime_hash,
    }
    draft = ContinentalManifest(run_id=uuid.UUID(int=0), manifest_hash="", created_at=utcnow(), **body)
    h = body_hash(draft)
    return draft.model_copy(update={"run_id": stable_uuid("continental", h), "manifest_hash": h}), paths


def verify_continental(manifest: ContinentalManifest) -> None:
    from amtgo.errors import ReproducibilityError

    if body_hash(manifest) != manifest.manifest_hash:
        raise ReproducibilityError(f"run continental {manifest.run_id} : manifeste altéré")
