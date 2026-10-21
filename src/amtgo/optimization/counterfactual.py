"""Map-C-Shallow (02 §21, 01 §6, 08 §18, 11 phase 9).

Question : quelle géométrie institutionnelle serait préférable **aujourd'hui**
si les frontières actuelles n'avaient aucune priorité juridique ?

    C_legal_legacy = 0,   mais   X = X_2026 observé.

On retire donc du vecteur d'objectifs le seul terme qui exprime le privilège de
la géométrie actuelle : J_T, la part de la population qui changerait d'État
par rapport à elle (``objectives.LEGACY_OBJECTIVES``). Il n'y a pas de
trajectoire : sans G_0 privilégié, « d'où l'on part » n'est pas un coût.

Tout le reste de la société observée est conservé, y compris ce que les
frontières actuelles ont produit : districts, comptes fiscaux, réseaux,
identités nationales. C'est un contre-factuel **contemporain**, donc hybride, et
il le déclare (01 §6). Map-C-Deep, qui modéliserait cette dépendance historique,
reste une branche de recherche séparée (prompt §55, §77).

La comparaison avec Map-R, sur les mêmes évaluations, mesure la **prime de
l'existant** : les options que seul le coût de transition tient hors du front.

Phase 9 (11) : « seulement après réussite des phases précédentes ». Sans tous
les gates passés, le produit reste un résultat de recherche non interprétable.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

HYBRID_KEPT = (
    "population et composition observées (2026), parts seulement",
    "districts actuels : juridictions locales emboîtées dans chaque État candidat",
    "comptes fiscaux par district et régime constitutionnel observé (viabilité)",
    "réseau de liens fonctionnels (noyau spatial) tel qu'il existe aujourd'hui",
)
REMOVED = (
    "J_T : part de la population qui change d'État par rapport à la géométrie actuelle",
    "trajectoires depuis G_0 (Map-R) : sans privilège de l'existant, le point de départ n'est pas un coût",
)


def legacy_premium(front_r: list[str], front_c: list[str], baselines: set[str]) -> dict[str, list[str]]:
    """Options que le coût de transition tient hors du front (et inversement)."""
    return {"enter_without_legacy": sorted(set(front_c) - set(front_r)),
            "leave_without_legacy": sorted(set(front_r) - set(front_c)),
            "baselines_leaving": sorted((set(front_r) - set(front_c)) & baselines)}


def phase_gate(gates: Mapping[str, str], falsification: list[dict[str, Any]]) -> dict[str, Any]:
    failed = {k: v for k, v in gates.items() if v not in ("PASSED", "NOT_APPLICABLE")}
    falsified = [c["control"] for c in falsification if c["status"] == "FAILED"]
    met = not failed and not falsified
    return {"met": met, "unmet_gates": failed, "failed_falsification": falsified,
            "status": "INTERPRETABLE" if met else "RESEARCH_ONLY"}


def statement(regime: str, ontologies: list[str], library_hash: str, robustness: float | None,
              category: str, on_front: bool, vintages: list[str]) -> str:
    """06 §15 transposé au contre-factuel contemporain : conditionnel, non prescriptif."""
    where = "appartient à l'ensemble de Pareto" if on_front else "n'appartient pas à l'ensemble de Pareto"
    rob = "inconnue" if robustness is None else f"{robustness:.2f}"
    return (f"Si les frontières actuelles n'avaient aucune priorité juridique, avec la société observée "
            f"({', '.join(vintages)}) et ses structures contemporaines, sous le régime {regime}, les ontologies "
            f"{', '.join(ontologies)} et les hypothèses causales {library_hash[:19]}…, cette géométrie {where} ; "
            f"sa robustesse (S^publish) est {rob}, sa catégorie {category}. Contre-factuel contemporain, non "
            f"prescriptif : son adoption exige un consentement politique externe au modèle.")
