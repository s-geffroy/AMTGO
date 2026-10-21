"""Coordination continentale par composition (M14 ; 07 §13-14, 11 phase 10, 02 §33, 09 §14-15).

Aucun solve continental monolithique (07 §13). La décomposition est :

    local (districts) → régional (runs Map-R) → interfaces (couches de coordination)
    → continental (composition des fronts)

Une option continentale est un tuple (une trajectoire Map-R par région, un ensemble
de couches par interface). Aucune frontière ne traverse une interface : les États
candidats d'une région restent dans la région, si bien que tout lien fonctionnel
inter-régional est coupé quelle que soit l'option régionale. Changer une frontière
à travers une interface relèverait d'un run régional sur la macro-région, pas
d'une coordination. Les objectifs sont donc **séparables** par région et par
interface, et la composition s'agrège ainsi, par ω = (paire de maillages, ontologie) :

- J_D, J_V, J_reif : maximum sur les régions (pire cas : une violation de droits ou
  un État non viable ne se compense pas ailleurs) ;
- J_F, J_conn, J_T : moyennes pondérées par la population des régions ;
- J_G : coupe fonctionnelle continentale = (Σ_r J_G,r·W_r + coupe inter-régionale) /
  (Σ_r W_r + W_interfaces), où W est le poids total des liens et où la coupe
  inter-régionale est atténuée par les couches (μ) ;
- J_inst : Σ_r J_inst,r + coût de gestion des frontières d'interface (invisible au
  niveau régional : la frontière extérieure d'une région n'y est jamais comptée) +
  coût annuel des couches ; la coordination de sécurité réduit le premier terme ;
- J_pkg, J_path : sommes ; une couche est une étape d'affaiblissement de frontière
  (§79) dont la pénalité suit 02 §26 ;
- J_R, J_P : UNKNOWN ; la relation d'emboîtement d'une composition est celle de ses
  composantes (raffinement si chaque région raffine ou est égale), et l'axiome de
  fusion (M11, M13) bloque les dominances comme dans une région.

Les couches sont évaluées à la borne **robuste** (μ basse, coût haut). La borne
optimiste (μ haute, coût bas) ne sert qu'à dire quelles couches entreraient au
front si l'effet était à sa borne haute : une priorité de recherche, pas un résultat.

Élagage : chaque région ne fournit que son front Map-R (plus le statu quo), et
chaque interface le front de ses ensembles de couches. Par séparabilité l'élagage
est sûr, mais l'ε-dominance et le blocage par l'axiome le rendent approché sur les
quasi-égalités : quand la taille le permet, le front composé est comparé à
l'énumération exhaustive (07 §14), et l'écart est publié.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from itertools import chain, combinations, product
from typing import Any

import numpy as np

from amtgo.manifests.normative import RobustnessWeights
from amtgo.optimization.archive import Archive, Variant, build, to_solutions
from amtgo.optimization.objectives import OBJECTIVES, UNKNOWN_OBJECTIVES, SqRelation
from amtgo.optimization.transition import PATH_OBJECTIVE

OBJECTIVES_C = (*OBJECTIVES, PATH_OBJECTIVE)
MAX_KEYS = ("J_D", "J_V", "J_reif")
MEAN_KEYS = ("J_F", "J_conn", "J_T")
SUM_KEYS = ("J_inst", "J_pkg", PATH_OBJECTIVE)
SQ_FAMILY = "STATUS_QUO"
COMPOSED_FAMILY = "CONTINENTAL_COMPOSITION"
ROBUST, OPTIMISTIC = "robust", "optimistic"

Omega = tuple[str, str]  # (paire de maillages, ontologie)


@dataclass(frozen=True)
class RegionOption:
    """Une trajectoire Map-R d'une région, ses objectifs par ω continental."""

    region: str
    key: str
    family: str
    top_action: str
    omega: dict[Omega, dict[str, Any]]
    relation: SqRelation  # au statu quo de la région
    relations: dict[str, SqRelation]  # aux autres trajectoires de la région

    @property
    def status_quo(self) -> bool:
        return self.family == SQ_FAMILY


@dataclass(frozen=True)
class RegionTotals:
    population: float
    link_weight: float  # W = Σ_{i<j} K_ij n_i n_j


@dataclass(frozen=True)
class Interface:
    a: str
    b: str
    border_km: float
    links: dict[str, dict[tuple[str, ...], float]]  # pair_id → {couches couvrant le lien : poids}

    @property
    def key(self) -> str:
        return f"{self.a}~{self.b}"

    def weight(self, pair_id: str) -> float:
        return float(sum(self.links.get(pair_id, {}).values()))


@dataclass(frozen=True)
class LayerEffect:
    layer_id: str
    acts_on: str  # cross_links | border_cost
    mu: tuple[float, float]  # bornes de l'effet gelé
    cost: tuple[float, float]  # coût annuel déclaré
    penalty: float  # J_path de l'étape (02 §26)

    def at(self, bound: str) -> tuple[float, float]:
        """(μ, coût) à la borne demandée : robuste = μ basse et coût haut."""
        return (self.mu[0], self.cost[1]) if bound == ROBUST else (self.mu[1], self.cost[0])


@dataclass(frozen=True)
class World:
    """Ce que la composition lit : totaux régionaux, interfaces, couches évaluables."""

    totals: dict[str, dict[str, RegionTotals]]  # région → pair_id → totaux
    interfaces: list[Interface]
    layers: dict[str, LayerEffect]
    border_cost_per_km: float

    def between(self, regions: Iterable[str]) -> list[Interface]:
        rs = set(regions)
        return [i for i in self.interfaces if i.a in rs and i.b in rs]


Choice = dict[str, tuple[str, ...]]  # interface → couches retenues


def combine_relations(rels: Iterable[SqRelation]) -> SqRelation:
    """Relation d'une composition : celle de ses composantes régionales."""
    rs = set(rels) - {SqRelation.EQUAL}
    if not rs:
        return SqRelation.EQUAL
    if len(rs) == 1:
        return next(iter(rs))
    return SqRelation.CROSSING


def _rel(x: RegionOption, y: RegionOption) -> SqRelation:
    if x.key == y.key:
        return SqRelation.EQUAL
    if y.status_quo:
        return x.relation
    if x.status_quo:
        return {SqRelation.REFINEMENT: SqRelation.COARSENING,
                SqRelation.COARSENING: SqRelation.REFINEMENT}.get(y.relation, y.relation)
    return x.relations.get(y.key, SqRelation.CROSSING)


@dataclass(frozen=True)
class Composite:
    options: dict[str, RegionOption]
    layers: Choice

    @property
    def key(self) -> str:
        parts = [f"{r}={o.key}" for r, o in sorted(self.options.items())]
        parts += [f"{i}=[{'+'.join(ls)}]" for i, ls in sorted(self.layers.items())]
        return "|".join(parts)

    @property
    def status_quo(self) -> bool:
        return all(o.status_quo for o in self.options.values()) and not any(self.layers.values())

    def relation_to(self, other: Composite) -> SqRelation:
        return combine_relations(_rel(o, other.options[r]) for r, o in self.options.items())


class _PairRelations(dict[str, SqRelation]):
    """Relations d'une composition aux autres, calculées à la demande (n² entrées sinon)."""

    def __init__(self, me: Composite, others: Mapping[str, Composite]) -> None:
        super().__init__()
        self._me, self._others = me, others

    def get(self, key: str, default: Any = None) -> Any:
        other = self._others.get(key)
        return default if other is None else self._me.relation_to(other)


def _known(xs: list[Any]) -> list[float] | None:
    """Valeurs d'un objectif sur les régions ; None si l'une est inconnue (UNKNOWN n'est jamais 0)."""
    return None if any(x is None for x in xs) else [float(x) for x in xs]


def evaluate(c: Composite, world: World, bound: str = ROBUST) -> dict[Omega, dict[str, Any]]:
    """Objectifs agrégés d'une composition, par ω commun à toutes ses régions."""
    regions = sorted(c.options)
    omegas = set.intersection(*(set(c.options[r].omega) for r in regions))
    interfaces = world.between(regions)
    out = {}
    for w in sorted(omegas):
        pid = w[0]
        vals = {r: c.options[r].omega[w] for r in regions}
        tot = {r: world.totals[r][pid] for r in regions}
        row: dict[str, Any] = {k: None for k in OBJECTIVES_C}
        for k in MAX_KEYS:
            xs = _known([vals[r].get(k) for r in regions])
            row[k] = None if xs is None else max(xs)
        pop = sum(t.population for t in tot.values())
        for k in MEAN_KEYS:
            xs = _known([vals[r].get(k) for r in regions])
            row[k] = None if xs is None else sum(
                x * tot[r].population for x, r in zip(xs, regions, strict=True)) / pop
        for k in SUM_KEYS:
            xs = _known([vals[r].get(k) for r in regions])
            row[k] = None if xs is None else float(sum(xs))
        num = sum(vals[r]["J_G"] * tot[r].link_weight for r in regions)
        den = sum(tot[r].link_weight for r in regions)
        border = 0.0
        for itf in interfaces:
            chosen = set(c.layers.get(itf.key, ()))
            for sig, wgt in itf.links.get(pid, {}).items():
                keep = 1.0
                for lid in chosen.intersection(sig):
                    keep *= 1.0 - world.layers[lid].at(bound)[0]
                num += wgt * keep
                den += wgt
            keep_border = 1.0
            for lid in chosen:
                le = world.layers[lid]
                mu, cost = le.at(bound)
                if le.acts_on == "border_cost":
                    keep_border *= 1.0 - mu
                if row["J_inst"] is not None:
                    row["J_inst"] += cost
                if row[PATH_OBJECTIVE] is not None:
                    row[PATH_OBJECTIVE] += le.penalty
            border += itf.border_km * world.border_cost_per_km * keep_border
        row["J_G"] = num / den if den > 0 else 0.0
        if row["J_inst"] is not None:
            row["J_inst"] += border
        for u in UNKNOWN_OBJECTIVES:
            row[u] = None
        row["violations"] = sorted(f"{r}:{x}" for r in regions for x in vals[r]["violations"])
        out[w] = row
    return out


def to_variants(composites: list[Composite], world: World, bound: str = ROBUST) -> list[Variant]:
    """Variantes de l'archive ; relations par paire paresseuses (axiome de fusion, M13)."""
    sq = next(c for c in composites if c.status_quo)
    by_key = {c.key: c for c in composites}
    out = []
    for c in composites:
        family = SQ_FAMILY if c.status_quo else COMPOSED_FAMILY
        params = {"regions": {r: o.key for r, o in sorted(c.options.items())},
                  "layers": {i: list(ls) for i, ls in sorted(c.layers.items())}}
        out.append(Variant(c.key, family, params, evaluate(c, world, bound), True, c.relation_to(sq),
                           _PairRelations(c, by_key)))
    return out


def layer_choices(world: World) -> list[tuple[str, ...]]:
    """Tous les ensembles de couches évaluables (la zone d'une couche est portée par les liens)."""
    ids = sorted(world.layers)
    return [tuple(s) for s in chain.from_iterable(combinations(ids, k) for k in range(len(ids) + 1))]


def _sq_options(options: dict[str, list[RegionOption]]) -> dict[str, RegionOption]:
    return {r: next(o for o in opts if o.status_quo) for r, opts in options.items()}


@dataclass
class Composition:
    archive: Archive
    composites: list[Composite]
    layer_fronts: dict[str, list[tuple[str, ...]]]
    layer_improving: dict[str, list[tuple[str, ...]]]  # ensembles de couches qui dominent l'absence de couche
    regional_fronts: dict[str, list[str]]
    exactness: list[dict[str, Any]] = field(default_factory=list)
    repaired: list[str] = field(default_factory=list)  # options réintégrées après contrôle exhaustif


def _archive(composites: list[Composite], world: World, eps: dict[str, float], rob: RobustnessWeights,
             normative: dict[str, Any], bound: str = ROBUST) -> Archive:
    return build(to_variants(composites, world, bound), eps, rob, normative, OBJECTIVES_C,
                 sq_comparison_excludes=())


def compose(options: dict[str, list[RegionOption]], world: World, eps: dict[str, float], rob: RobustnessWeights,
            normative: dict[str, Any], regional_front: dict[str, set[str]], bound: str = ROBUST) -> Composition:
    """Composition hiérarchique : fronts régionaux × fronts de couches par interface."""
    sq = _sq_options(options)
    layer_fronts, layer_improving = {}, {}
    for itf in world.interfaces:
        # Séparabilité : l'apport d'un ensemble de couches ne dépend pas des options régionales.
        cands = [Composite({r: sq[r] for r in (itf.a, itf.b)}, {itf.key: ch}) for ch in layer_choices(world)]
        a = _archive(cands, world, eps, rob, normative, bound)
        on_front = {s.key for s in a.solutions if s.rank == 1}
        layer_fronts[itf.key] = [c.layers[itf.key] for c in cands if c.key in on_front or c.status_quo]
        layer_improving[itf.key] = [c.layers[itf.key] for c in cands if c.key in a.improving]
    kept = {r: [o for o in opts if o.key in regional_front[r] or o.status_quo] for r, opts in options.items()}
    composites = _product(kept, layer_fronts)
    return Composition(_archive(composites, world, eps, rob, normative, bound), composites, layer_fronts,
                       layer_improving,
                       {r: [o.key for o in v] for r, v in kept.items()})


def _product(options: dict[str, list[RegionOption]], layers: dict[str, list[tuple[str, ...]]]) -> list[Composite]:
    regions = sorted(options)
    itfs = sorted(layers)
    out = []
    for opts in product(*(options[r] for r in regions)):
        for chs in product(*(layers[i] for i in itfs)):
            out.append(Composite(dict(zip(regions, opts, strict=True)), dict(zip(itfs, chs, strict=True))))
    return out


def size(options: dict[str, list[RegionOption]], layers: dict[str, list[tuple[str, ...]]]) -> int:
    return int(np.prod([len(v) for v in options.values()]) * np.prod([len(v) for v in layers.values()] or [1]))


def first_front(variants: list[Variant], eps: dict[str, float], rob: RobustnessWeights) -> set[str]:
    """Front (rang 1) vectorisé, mêmes règles que ``nondominated_sort`` : contrôle d'exactitude.

    a domine b ssi, sur les objectifs connus des deux, a ≤ b + ε partout et a < b − ε
    quelque part, et si a ne grossit pas b (axiome de fusion : J_P NOT_BETTER).
    """
    sols = to_solutions(variants, rob, OBJECTIVES_C)
    feas = [i for i, s in enumerate(sols) if s.feasible]
    keys = [k for k in OBJECTIVES_C if k in eps]
    x = np.array([[np.nan if sols[i].objectives.get(k) is None else sols[i].objectives[k] for k in keys]
                  for i in feas], dtype=float)
    e = np.array([eps[k] for k in keys])
    if len(feas) == 0:
        return set()
    a, b = x[:, None, :], x[None, :, :]
    both = ~np.isnan(a) & ~np.isnan(b)
    not_worse = np.where(both, a <= b + e, True).all(axis=2)
    better = np.where(both, a < b - e, False).any(axis=2)
    dom = not_worse & better & both.any(axis=2)
    np.fill_diagonal(dom, False)
    by_key = {v.key: v for v in variants}
    fv = [by_key[sols[i].key] for i in feas]
    sq = next((v for v in fv if v.family == SQ_FAMILY), None)
    rows, cols = np.nonzero(dom)
    for i, j in zip(rows.tolist(), cols.tolist(), strict=True):
        if _coarsens(fv[i], fv[j], sq):
            dom[i, j] = False
    return {sols[feas[j]].key for j in range(len(feas)) if not dom[:, j].any()}


def _coarsens(a: Variant, b: Variant, sq: Variant | None) -> bool:
    from amtgo.optimization.archive import geometry_relation

    return sq is not None and geometry_relation(a, b, sq.key) is SqRelation.COARSENING


def _vectors(variants: list[Variant], keys: set[str], rob: RobustnessWeights) -> dict[str, tuple[Any, ...]]:
    """Fronts comparés dans l'espace des objectifs (deux options distinctes peuvent coïncider)."""
    sols = to_solutions([v for v in variants if v.key in keys], rob, OBJECTIVES_C)
    return {s.key: tuple(None if s.objectives.get(k) is None else round(float(s.objectives[k]), 9)  # type: ignore[arg-type]
                         for k in OBJECTIVES_C) for s in sols}


def exactness_check(name: str, full: list[Composite], composed_front: set[str], world: World,
                    eps: dict[str, float], rob: RobustnessWeights, limit: int,
                    bound: str = ROBUST) -> dict[str, Any]:
    """Compare le front composé à celui de l'énumération exhaustive ``full`` (07 §14).

    ``missed_keys`` : options du front exhaustif dont le vecteur manque au front composé ;
    l'appelant les réintègre (réparation), de sorte que l'élagage ne perd rien quand il est vérifié.
    """
    if len(full) > limit:
        return {"check": name, "size": len(full), "checked": False, "missed_keys": [],
                "reason": f"énumération de {len(full)} options > {limit} : non vérifiée"}
    vs = to_variants(full, world, bound)
    ex = _vectors(vs, first_front(vs, eps, rob), rob)
    co = _vectors(vs, composed_front & {v.key for v in vs}, rob)
    seen = set(co.values())
    missed = sorted(k for k, v in ex.items() if v not in seen)
    return {"check": name, "size": len(full), "checked": True, "exact": not missed and seen <= set(ex.values()),
            "missed": len({ex[k] for k in missed}), "spurious": len(seen - set(ex.values())), "missed_keys": missed}


def verify_and_repair(comp: Composition, options: dict[str, list[RegionOption]], world: World,
                      eps: dict[str, float], rob: RobustnessWeights, normative: dict[str, Any], limit: int,
                      bound: str = ROBUST) -> Composition:
    """Contrôle les deux élagages par énumération (quand la taille le permet) et répare.

    1. couches : fronts régionaux × tous les ensembles de couches ;
    2. fronts régionaux : toutes les trajectoires × fronts de couches.
    Une option du front exhaustif absente du front composé est réintégrée et l'archive
    reconstruite : vérifié, l'élagage ne perd rien ; non vérifié (taille), il reste approché
    et le produit le dit.
    """
    front = set(comp.archive.front)
    all_layers = {i.key: layer_choices(world) for i in world.interfaces}
    kept = {r: [o for o in opts if o.key in comp.regional_fronts[r]] for r, opts in options.items()}
    checks, extra = [], {}
    for name, full in (("couches (fronts régionaux × tous les ensembles de couches)", _product(kept, all_layers)),
                       ("fronts régionaux (toutes les trajectoires × fronts de couches)",
                        _product(options, comp.layer_fronts))):
        chk = exactness_check(name, full, front, world, eps, rob, limit, bound)
        checks.append(chk)
        if chk["missed_keys"]:
            by_key = {c.key: c for c in full}
            extra.update({k: by_key[k] for k in chk["missed_keys"]})
    if not extra:
        return replace(comp, exactness=checks)
    known = {c.key for c in comp.composites}
    composites = comp.composites + [c for k, c in sorted(extra.items()) if k not in known]
    return replace(comp, archive=_archive(composites, world, eps, rob, normative, bound), composites=composites,
                   exactness=checks, repaired=sorted(extra))


# --- lecture : conclusion, régimes de conclusion (09 §14), catégorie -------------------------------

class Verdict(StrEnum):
    """Les cinq régimes de conclusion des stress-tests continentaux (09 §14)."""

    TERRITORIALISATION_UTILE = "territorialisation_utile"
    AUTONOMIE_PREFERABLE = "autonomie_preferable"
    OVERLAY_PREFERABLE = "overlay_preferable"
    FRONTIERE_FONCTIONNELLE_FAIBLE = "frontiere_fonctionnelle_faible"
    SEPARATION_SUPPLEMENTAIRE_DANGEREUSE = "separation_supplementaire_dangereuse"


AUTONOMY_ACTIONS = ("autonomy", "federation")
OVERLAY_LEVER = "functional_overlay"


def _worse(row: Mapping[str, Any], ref: Mapping[str, Any], keys: Iterable[str], eps: Mapping[str, float]) -> list[str]:
    return [k for k in keys if row.get(k) is not None and ref.get(k) is not None and row[k] > ref[k] + eps[k]]


def regional_verdicts(rows: list[dict[str, Any]], improving: list[str], eps: Mapping[str, float]) -> dict[str, Any]:
    """Régimes de conclusion d'une région, lus sur son produit Map-R.

    Un régime n'est **établi** que par une dominance du statu quo (inconnus tranchés) :
    un compromis au front n'établit rien. « Séparation supplémentaire dangereuse » exige
    que **toute** trajectoire qui crée des États soit infaisable ou pire que le statu quo
    sur les droits (J_D) au-delà de ε. Une réification plus forte (J_reif, borne haute
    tirée d'un effet déclaré) est publiée comme signal, sans établir le régime.
    """
    by_id = {r["path_id"]: r for r in rows}
    sq = next(r for r in rows if r["family"] == SQ_FAMILY)
    found: dict[str, list[str]] = {}
    for pid in improving:
        r = by_id[pid]
        levers = {s["payload"].get("lever") for s in r["steps"]}
        if r["family"] == "PATH_TERRITORIAL":
            found.setdefault(Verdict.TERRITORIALISATION_UTILE.value, []).append(r["name"])
        elif r["top_action"] in AUTONOMY_ACTIONS:
            found.setdefault(Verdict.AUTONOMIE_PREFERABLE.value, []).append(r["name"])
        elif OVERLAY_LEVER in levers:
            found.setdefault(Verdict.OVERLAY_PREFERABLE.value, []).append(r["name"])
    sovereign = [r for r in rows if r["top_action"] == "sovereignty"]
    evidence = {r["name"]: ("infaisable" if not r["feasible"]
                            else _worse(r["objectives"], sq["objectives"], ("J_D",), eps))
                for r in sovereign}
    if sovereign and all(e == "infaisable" or e for e in evidence.values()):
        found[Verdict.SEPARATION_SUPPLEMENTAIRE_DANGEREUSE.value] = sorted(evidence)
    signals = {r["name"]: ["J_reif"] for r in sovereign if r["feasible"]
               and _worse(r["objectives"], sq["objectives"], ("J_reif",), eps)}
    return {"established": dict(sorted(found.items())), "separation_evidence": evidence,
            "reification_signals": signals,
            "note": None if found else "aucun régime établi : aucune trajectoire ne domine le statu quo"}


def conclusion(a: Archive) -> str:
    if a.certificate is not None:
        return "INFEASIBLE"
    if a.improving:
        return "CONTINENTAL_COMPOSITIONS_DOMINATE_STATUS_QUO"
    if a.unresolved:
        return "DOMINANCE_UNRESOLVED_UNKNOWN_OBJECTIVES"
    return "STATUS_QUO_NOT_DOMINATED"


CATEGORY_ORDER = ("NOT_IDENTIFIABLE", "EXPLORATORY", "CONDITIONAL", "ROBUST")


def worst_category(categories: Iterable[str]) -> str:
    """Une composition n'est jamais plus publiable que la moins publiable de ses régions."""
    return min(categories, key=CATEGORY_ORDER.index)


def statement(regime: str, ontologies: list[str], freeze_hash: str, category: str, n_regions: int) -> str:
    """Formulation conditionnelle (06 §15), jamais une carte ni une recommandation."""
    return (f"Sous le régime {regime}, avec les ontologies {', '.join(ontologies)} et la bibliothèque "
            f"continentale gelée {freeze_hash[:19]}…, la composition de {n_regions} produits Map-R régionaux par "
            "des couches de coordination déclarées donne l'archive ci-dessus ; aucune frontière ne traverse une "
            f"interface. Catégorie de publication : {category} — aucune frontière nette n'est publiée (§75-76). "
            "L'adoption reste externe au modèle.")
