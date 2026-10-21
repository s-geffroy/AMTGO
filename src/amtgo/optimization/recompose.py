"""Recomposition institutionnelle d'un candidat (M11, biais déclaré en M10).

En M10, chaque géométrie candidate recevait le gabarit institutionnel du statu
quo : une géométrie qui violait la contrainte de droits était exclue, même si un
levier à géométrie fixe (droits, représentation, overlay, dévolution) l'aurait
levée. Le composeur M9 est maintenant appliqué au candidat qui viole :

- s'il trouve un paquet qui lève toute violation **à la borne basse** de
  l'efficacité gelée (``NO_TERRITORIAL_CHANGE_SUFFICIENT``), le candidat est
  évalué avec ce paquet, dont le coût devient l'objectif J_pkg ;
- sinon (effet inconnu, levée seulement possible, aucune levée), la violation
  reste et le candidat reste infaisable — jamais une relaxation.

Un candidat sans violation garde le gabarit du statu quo (J_pkg = 0) : le
composeur n'ajoute rien qui ne soit nécessaire aux droits.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from amtgo.causal.library import CausalAnswer
from amtgo.core.channels import IntegChannel
from amtgo.geo.partition import Partition
from amtgo.identity.state import SocialState
from amtgo.institutions.competences import Institution
from amtgo.institutions.composer import ComposerManifest, Configuration, border_cells, compose, configuration
from amtgo.manifests.normative import RightsThresholds


@dataclass(frozen=True)
class Recomposition:
    conclusion: str  # conclusion du composeur sur cette géométrie
    option: str | None  # option retenue (premier paquet robuste dans l'ordre du §39)
    configuration: Configuration | None  # None : aucun paquet ne lève robustement la violation
    cost: float
    complexity: int

    def as_json(self) -> dict[str, object]:
        return {"conclusion": self.conclusion, "option": self.option, "cost": self.cost,
                "complexity": self.complexity}


def recompose(state: SocialState, partition: Partition, institutions: dict[str, list[Institution]],
              rights: RightsThresholds, weights: dict[IntegChannel, float], manifest: ComposerManifest,
              effects: dict[str, CausalAnswer], adjacency: list[list[int]],
              check_stop: Callable[[str], None] | None = None) -> Recomposition:
    res = compose(state, partition, institutions, rights, weights, manifest, effects, adjacency, check_stop)
    if res["conclusion"] != "NO_TERRITORIAL_CHANGE_SUFFICIENT":
        return Recomposition(res["conclusion"], res["chosen"], None, 0.0, 0)
    chosen = next(o for o in res["options"] if o["option"] == res["chosen"])
    specs = [next(s for s in manifest.levers if s.lever.value == lv) for lv in chosen["levers"]]
    base = Configuration({k: list(v) for k, v in institutions.items()}, [])
    cells = border_cells(partition, adjacency, manifest.overlay_ring)
    cfg = configuration(base, specs, effects, manifest, cells, "lo")
    return Recomposition(res["conclusion"], res["chosen"], cfg, float(chosen["lo"]["cost"]),
                         int(chosen["lo"]["complexity"]))
