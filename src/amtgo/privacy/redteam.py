"""Red-team de confidentialité et de mésusage politique (05 §15-16), Gate S.

Deux volets :

1. une **suite d'attaques** fixe, chacune une publication construite pour
   permettre une inférence nuisible : reconstruction d'un petit groupe,
   intersection de couches publiques, inférence de religion, route pastorale,
   frontière candidate révélant les groupes, localisation d'une minorité
   (05 §16 : « le système public doit rester inutile à ces usages ») ;
2. l'**inventaire** des couches qu'un run produit, évalué pour une cible PUBLIC.

Gate S passe si chaque attaque est bloquée (rien n'en sort tel quel) et si
aucune couche de l'inventaire portant population, groupe, mobilité ou dérivée
des groupes n'est publiable telle quelle.
"""

from __future__ import annotations

from typing import Any

from amtgo.core.enums import PrivacyClass
from amtgo.privacy.guard import ExportLayer, ReleaseRules, evaluate_release

C, P = PrivacyClass.CONTROLLED, PrivacyClass.PUBLIC


def attack_suite(rules: ReleaseRules) -> list[dict[str, Any]]:
    k = rules.min_group_count
    attacks: dict[str, list[ExportLayer]] = {
        "small_group_reconstruction": [
            ExportLayer("population_fine", P, True, False, False, 100, ("population",), "grid_fine", k / 10)],
        "public_layer_intersection": [
            ExportLayer("population_grid", P, True, False, False, 100, ("population",), "grid", 10 * k),
            ExportLayer("population_hex", P, True, False, False, 100, ("population",), "hex", 10 * k)],
        "religion_inference": [
            ExportLayer("language_map", P, False, False, False, 100, ("language_share",), "grid")],
        "pastoral_route_inference": [
            ExportLayer("corridor", P, False, False, True, 1, ("route",), "corridor")],
        "candidate_border_reveals_groups": [
            ExportLayer("candidate_borders", P, False, False, False, 2, ("boundary",), "grid",
                        derived_from_group_attributes=True)],
        "minority_locator": [
            ExportLayer("group_shares", C, True, True, False, 100, ("group_share",), "grid", 10 * k)],
    }
    out = []
    for name, layers in attacks.items():
        # Évaluée aussi pour une diffusion CONTROLLED (chercheurs habilités), où la population sort :
        # c'est là que les règles de petit effectif et de différenciation doivent tenir seules.
        row: dict[str, Any] = {"attack": name, "blocked": True, "decisions": {}}
        for target in (P, C):
            decisions = evaluate_release(layers, rules, target)
            # Bloquée : au moins une couche de l'attaque ne sort pas telle quelle.
            row["blocked"] &= not all(d.released for d in decisions.values())
            row["decisions"][target.value] = {n: {"action": d.action.value, "reason": d.reason}
                                              for n, d in decisions.items()}
        out.append(row)
    return out


def benign_controls(rules: ReleaseRules) -> list[dict[str, Any]]:
    """Contrôles négatifs : un garde qui bloque tout passerait la suite d'attaques sans rien prouver."""
    k = rules.min_group_count
    cases = [("mesh_geometry", P, ExportLayer("mesh", P, False, False, False, 100, ("geometry",), "grid")),
             ("controlled_population", C,
              ExportLayer("population", P, True, False, False, 100, ("population",), "grid", 10 * k))]
    out = []
    for name, target, layer in cases:
        d = evaluate_release([layer], rules, target)[layer.name]
        out.append({"control": name, "target": target.value, "released": d.released, "reason": d.reason})
    return out


def inventory_decisions(layers: list[ExportLayer], rules: ReleaseRules) -> list[dict[str, Any]]:
    decisions = evaluate_release(layers, rules, P)
    out = []
    for layer in layers:
        d = decisions[layer.name]
        sensitive = (layer.contains_population or layer.contains_group_attributes or layer.contains_mobility
                     or layer.derived_from_group_attributes)
        out.append({"layer": layer.name, "action": d.action.value, "reason": d.reason, "sensitive": sensitive,
                    "leak": sensitive and d.released})
    return out


def gate_s(layers: list[ExportLayer], rules: ReleaseRules) -> dict[str, Any]:
    attacks = attack_suite(rules)
    controls = benign_controls(rules)
    inventory = inventory_decisions(layers, rules)
    ok = (all(a["blocked"] for a in attacks) and all(c["released"] for c in controls)
          and not any(x["leak"] for x in inventory))
    return {"gate_s": "PASSED" if ok else "FAILED", "attacks": attacks, "benign_controls": controls,
            "inventory": inventory, "public_layers": [x["layer"] for x in inventory if x["action"] == "allow"]}
