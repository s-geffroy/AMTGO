"""Trajectoires de transition et produit Map-R (02 §20, §26-27, §34 ; 08 §17, §24-25 ; prompt §77-80).

Map-R demande quelle amélioration est réaliste **depuis les institutions
présentes** : le changement a un coût, et une trajectoire peut valoir mieux
qu'une cible (08 §24). Une trajectoire G_0 → G_1 → … → G_T est une suite
d'actions rangées dans la hiérarchie contrefactuelle du §79 :

    no change < droits < réforme institutionnelle < autonomie < fédération
              < affaiblissement de frontière < changement de frontière < souveraineté

Une trajectoire ne redescend jamais la hiérarchie. Chaque étape est
**réévaluée** (08 §24) : l'état après l'étape k est celui du préfixe k des
leviers du composeur (M9), ou la géométrie cible (M10). Une étape qui
violerait les droits rend la trajectoire infaisable : on ne traverse pas une
violation pour atteindre une cible.

Coût (02 §26), à minimiser :

    J_path = Σ_t [ λ_I ι(a_t) + λ_U U_causal(a_t) − λ_V VOI(a_t) ]

à côté du vecteur J de l'état final, dont J_T (part de la population qui change
d'État) et J_pkg (coût institutionnel du paquet). Les unités restent séparées :
aucun taux de conversion n'est inventé. Les poids λ sont normatifs (06 §5) ;
ι(a) est un paramètre de modèle déclaré par type d'action.

- U_causal : largeur relative de l'intervalle de l'effet gelé ; 1 si l'effet est
  inconnu, et pour tout changement de frontière (aucun effet territorial identifié) ;
- VOI : **indicateur** (pas une valeur espérée de l'information) — 1 si l'étape est
  réversible (ι ≤ seuil déclaré) et porte sur un effet qui n'est pas un fait causal,
  donc qu'on apprendrait en l'essayant (08 §25) ; 0 sinon ;
- urgence (02 §27, 06 §12) : si le statu quo présente une domination grave urgente,
  seule une trajectoire dont la **première** étape lève toute violation reste
  faisable — y compris l'absence de changement, qui devient infaisable — et la
  valeur d'information ne compte plus : la sécurité des personnes a priorité.

Le résultat est une archive de trajectoires et une lecture conditionnelle,
jamais une « meilleure » trajectoire, et jamais une décision : l'adoption reste
externe au modèle (prompt §30).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from amtgo.causal.library import CausalAnswer
from amtgo.institutions.composer import ComposerManifest, Lever
from amtgo.manifests.normative import TransitionWeights
from amtgo.optimization.archive import Variant
from amtgo.optimization.objectives import SqRelation
from amtgo.utils.canonical import content_hash

PATH_OBJECTIVE = "J_path"
SQ_FAMILY = "STATUS_QUO"
INSTITUTIONAL_FAMILY = "PATH_INSTITUTIONAL"
TERRITORIAL_FAMILY = "PATH_TERRITORIAL"


class ActionType(StrEnum):
    """Hiérarchie contrefactuelle (prompt §79), dans l'ordre de comparaison."""

    NO_CHANGE = "no_change"
    RIGHTS_ENFORCEMENT = "rights_enforcement"
    INSTITUTIONAL_REFORM = "institutional_reform"
    AUTONOMY = "autonomy"
    FEDERATION = "federation"
    BORDER_WEAKENING = "border_weakening"
    BORDER_CHANGE = "border_change"
    SOVEREIGNTY = "sovereignty"

    @property
    def level(self) -> int:
        return list(ActionType).index(self)


LEVER_ACTION = {
    Lever.RIGHTS_ENFORCEMENT: ActionType.RIGHTS_ENFORCEMENT,
    Lever.REPRESENTATION: ActionType.INSTITUTIONAL_REFORM,
    Lever.LANGUAGE_RIGHTS: ActionType.INSTITUTIONAL_REFORM,
    Lever.FUNCTIONAL_OVERLAY: ActionType.INSTITUTIONAL_REFORM,
    Lever.FISCAL_AUTONOMY: ActionType.AUTONOMY,
    Lever.TERRITORIAL_AUTONOMY: ActionType.AUTONOMY,
    Lever.FEDERATION: ActionType.FEDERATION,
    Lever.CONFEDERATION: ActionType.SOVEREIGNTY,
    Lever.SOVEREIGNTY: ActionType.SOVEREIGNTY,
}


class TransitionManifest(BaseModel):
    """Paramètres de MODÈLE des trajectoires (les poids λ sont normatifs : NormativeManifest)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    transition_id: str
    version: str
    description: str
    irreversibility: dict[ActionType, float]  # ι(a) ∈ [0, 1] par type d'action (PROVISOIRE)
    reversible_max: float = Field(ge=0, le=1)  # au-delà, une étape n'apprend rien qu'on puisse défaire
    path_epsilon: float = Field(ge=0)  # résolution de J_path
    uncertainty_floor: float = Field(gt=0)  # plancher du dénominateur de la largeur relative

    @model_validator(mode="after")
    def _complete(self) -> Self:
        if set(self.irreversibility) != set(ActionType):
            raise ValueError(f"irreversibility : une valeur par type d'action {[a.value for a in ActionType]}")
        if any(not 0.0 <= v <= 1.0 for v in self.irreversibility.values()):
            raise ValueError("irreversibility ∈ [0, 1]")
        if self.irreversibility[ActionType.NO_CHANGE] != 0.0:
            raise ValueError("ne rien changer est réversible par définition : ι(no_change) = 0")
        return self

    @property
    def content_hash(self) -> str:
        return content_hash(self)


@dataclass(frozen=True)
class Step:
    index: int
    action: ActionType
    payload: dict[str, Any]
    irreversibility: float
    uncertainty: float
    voi: float
    violations: int  # pire nombre de violations de l'état atteint, sur les ω
    cost: float | None  # coût institutionnel cumulé (unités du composeur) ; None : sans objet

    def as_json(self) -> dict[str, Any]:
        return {"step": self.index, "action": self.action.value, "payload": self.payload,
                "irreversibility": self.irreversibility, "uncertainty": self.uncertainty,
                "value_of_information": self.voi, "violations": self.violations, "cost": self.cost}


@dataclass
class Path:
    path_id: str
    family: str
    target: str  # clé de la variante (solution) visée
    steps: list[Step]
    omega: dict[tuple[str, str], dict[str, Any]]  # état final par ω (objectifs J, violations)
    relation: SqRelation
    notes: list[str] = field(default_factory=list)

    @property
    def top_action(self) -> ActionType:
        return max((s.action for s in self.steps), key=lambda a: a.level)

    def penalty(self, w: TransitionWeights) -> float:
        return float(sum(w.lambda_irreversibility * s.irreversibility + w.lambda_uncertainty * s.uncertainty
                         - w.lambda_voi * s.voi for s in self.steps))

    def as_variant(self, w: TransitionWeights) -> Variant:
        pen = self.penalty(w)
        return Variant(self.path_id, self.family, {"steps": [s.action.value for s in self.steps]},
                       {k: {**v, PATH_OBJECTIVE: pen} for k, v in self.omega.items()}, True, self.relation)


def step_uncertainty(answer: CausalAnswer | None, floor: float) -> float:
    if answer is None or not answer.known:
        return 1.0
    iv = answer.interval()
    return float(min(1.0, (iv.hi - iv.lo) / max(abs(iv.hi), abs(iv.lo), floor)))


def voi_indicator(iota: float, answer: CausalAnswer | None, reversible_max: float) -> float:
    if answer is None or not answer.known or answer.status == "CAUSAL_FACT":
        return 0.0
    return 1.0 if iota <= reversible_max else 0.0


def status_quo_path(sq: Variant) -> Path:
    return Path("path:status_quo", SQ_FAMILY, sq.key,
                [Step(1, ActionType.NO_CHANGE, {}, 0.0, 0.0, 0.0, _worst_violations(sq.omega), 0.0)],
                {k: dict(v) for k, v in sq.omega.items()}, SqRelation.EQUAL)


def _worst_violations(omega: dict[tuple[str, str], dict[str, Any]]) -> int:
    return max((len(v["violations"]) for v in omega.values()), default=0)


def institutional_paths(composer: dict[tuple[str, str], dict[str, Any]], sq: Variant, cm: ComposerManifest,
                        effects: dict[str, CausalAnswer], tm: TransitionManifest) -> tuple[list[Path], list[str]]:
    """Trajectoires à géométrie fixe : chaque levier seul, puis chaque préfixe de l'ordre du §39.

    ``composer`` : résultat du composeur sur la géométrie du statu quo, par ω.
    Renvoie aussi les options non évaluables (effet inconnu sur au moins un ω).
    """
    fixed = [lv for lv in cm.levers if lv.lever.fixed_geometry]
    sequences = [[lv] for lv in fixed] + [fixed[:k] for k in range(2, len(fixed) + 1)]
    paths, skipped = [], []
    for seq in sequences:
        # État après l'étape j : l'option du composeur qui applique les j premiers leviers (réévaluation, 08 §24).
        if len(seq) == 1:
            label = seq[0].lever.value
            prefixes = [label]
        else:
            label = f"cumul→{seq[-1].lever.value}"
            prefixes = [seq[0].lever.value] + [f"cumul→{lv.lever.value}" for lv in seq[1:]]
        options = {w: {o["option"]: o for o in res["options"]} for w, res in composer.items()}
        if any(options[w].get(p) is None or options[w][p]["lo"] is None for w in composer for p in prefixes):
            skipped.append(label)
            continue
        steps = []
        for j, (lv, p) in enumerate(zip(seq, prefixes, strict=True)):
            action = LEVER_ACTION[lv.lever]
            iota = tm.irreversibility[action]
            ans = effects.get(lv.effect) if lv.effect else None
            states = [options[w][p]["lo"] for w in composer]
            base = max(composer[w]["baseline"]["cost"] for w in composer)
            steps.append(Step(j + 1, action, {"lever": lv.lever.value, "option": p}, iota,
                              step_uncertainty(ans, tm.uncertainty_floor),
                              voi_indicator(iota, ans, tm.reversible_max),
                              max(s["violations"] for s in states), max(s["cost"] for s in states) - base))
        omega = {}
        for w, res in composer.items():
            final = options[w][prefixes[-1]]["lo"]
            interim = [f"droits (étape {j + 1}, {p})" for j, p in enumerate(prefixes)
                       if options[w][p]["lo"]["violations"] > 0]
            v = dict(sq.omega[w])
            v.update({"J_D": final["max_p_exceed"], "J_F": final["f_network"], "J_conn": final["j_conn"],
                      "J_reif": final["rri"][1] if final["rri"] else v.get("J_reif"),
                      "J_pkg": final["cost"] - res["baseline"]["cost"], "violations": interim})
            omega[w] = v
        paths.append(Path(f"path:{label}", INSTITUTIONAL_FAMILY, "INSTITUTIONAL_ONLY_REFORM", steps, omega,
                          SqRelation.EQUAL))
    return paths, skipped


def territorial_path(v: Variant, name: str, creates_states: bool, tm: TransitionManifest) -> Path:
    """Changement de frontière vers une géométrie candidate : une étape, sans effet territorial identifié."""
    action = ActionType.SOVEREIGNTY if creates_states else ActionType.BORDER_CHANGE
    iota = tm.irreversibility[action]
    step = Step(1, action, {"target": name}, iota, 1.0, voi_indicator(iota, None, tm.reversible_max),
                _worst_violations(v.omega), None)
    return Path(f"path:{v.key}", TERRITORIAL_FAMILY, v.key, [step], {k: dict(x) for k, x in v.omega.items()},
                v.relation)


def apply_urgency(paths: list[Path]) -> list[str]:
    """02 §27 : en urgence, la première étape doit lever toute violation ; la VOI ne compte plus."""
    affected = []
    for p in paths:
        p.steps = [Step(s.index, s.action, s.payload, s.irreversibility, s.uncertainty, 0.0, s.violations, s.cost)
                   for s in p.steps]
        if p.steps[0].violations > 0:
            for v in p.omega.values():
                v["violations"] = [*v["violations"], "urgence : mesure corrective différée (02 §27)"]
            affected.append(p.path_id)
    return affected


def conclusion(archive_conclusion: str, improving: list[str], families: dict[str, str]) -> str:
    if archive_conclusion == "INFEASIBLE":
        return "INFEASIBLE"
    if any(families[k] == INSTITUTIONAL_FAMILY for k in improving):
        return "INSTITUTIONAL_PATH_IMPROVES_ON_STATUS_QUO"
    if improving:
        return "TERRITORIAL_PATH_IMPROVES_ON_STATUS_QUO"
    if archive_conclusion == "DOMINANCE_UNRESOLVED_UNKNOWN_OBJECTIVES":
        return "UNRESOLVED_UNKNOWN_OBJECTIVES"
    return "STATUS_QUO_NOT_DOMINATED"  # rien ne fait au moins aussi bien partout, transition comprise


def explain(objectives: dict[str, float | None], sq_objectives: dict[str, float | None],
            eps: dict[str, float]) -> dict[str, list[str]]:
    """Prompt §80 : ce qui s'améliore et ce qui se dégrade par rapport au statu quo (au-delà de ε)."""
    better, worse, unknown = [], [], []
    for k, e in sorted(eps.items()):
        a, b = objectives.get(k), sq_objectives.get(k)
        if a is None or b is None:
            unknown.append(k)
        elif a < b - e:
            better.append(k)
        elif a > b + e:
            worse.append(k)
    return {"improved": better, "worsened": worse, "not_compared": unknown}


def statement(regime: str, ontologies: list[str], library_hash: str, robustness: float | None,
              category: str, on_front: bool) -> str:
    """06 §15 : la seule formulation admise ; jamais « devrait », jamais « prouve »."""
    where = "appartient à l'ensemble de Pareto des trajectoires" if on_front else \
        "n'appartient pas à l'ensemble de Pareto des trajectoires"
    rob = "inconnue" if robustness is None else f"{robustness:.2f}"
    return (f"Sous le régime {regime}, les ontologies {', '.join(ontologies)} et les hypothèses causales "
            f"{library_hash[:19]}…, cette trajectoire {where} ; sa robustesse (S^publish) est {rob}, "
            f"sa catégorie {category}, et son adoption exige un consentement politique externe au modèle.")
