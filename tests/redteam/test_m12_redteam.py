"""Red-team M12 (Map-R) : pas de « meilleure trajectoire », pas de carte non validée, lecture conditionnelle."""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "amtgo"
FILES = [SRC / "optimization" / "transition.py", SRC / "runs" / "map_r_stages.py"]


def _identifiers(path: Path) -> set[str]:
    out = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.FunctionDef):
            out.add(node.name)
        elif isinstance(node, ast.Attribute):
            out.add(node.attr)
    return out


def test_no_best_path_and_no_argmin() -> None:
    """ADR-0009 : Map-R est une archive avec coût de transition, jamais un argmin."""
    for path in FILES:
        ids = _identifiers(path)
        assert not {i for i in ids if "best" in i.lower() or "argmin" in i.lower() or "optimal" in i.lower()}, path


def test_no_forbidden_wording() -> None:
    """06 §15 : jamais « AMTGO prouve que cette région devrait… »."""
    for path in FILES:  # le rapport généré est vérifié en intégration
        text = path.read_text().lower()
        for word in ("devrait devenir", "doit devenir indépendant", "prouve que", "recommandée", "best path"):
            assert word not in text, (path, word)


def test_map_layer_requires_release_and_guard() -> None:
    """La couche Map-R ne sort qu'avec une publication permise ET l'accord du privacy guard."""
    src = (SRC / "runs" / "map_r_stages.py").read_text()
    assert '"published": released and decision.released' in src
    assert "derived_from_group_attributes=True" in src
    assert '"features": []' in src  # aucune géométrie n'est écrite par ce milestone


def test_territorial_steps_claim_no_causal_effect() -> None:
    from amtgo.optimization.archive import Variant
    from amtgo.optimization.objectives import SqRelation
    from amtgo.optimization.transition import TransitionManifest, territorial_path

    iota = {"no_change": 0.0, "rights_enforcement": 0.1, "institutional_reform": 0.2, "autonomy": 0.4,
            "federation": 0.6, "border_weakening": 0.6, "border_change": 0.9, "sovereignty": 1.0}
    tm = TransitionManifest.model_validate({"transition_id": "t", "version": "1", "description": "d",
                                            "irreversibility": iota, "reversible_max": 0.95, "path_epsilon": 0.0,
                                            "uncertainty_floor": 0.01})
    v = Variant("c", "GEOGRAPHIC", {}, {("m", "o"): {"violations": []}}, relation=SqRelation.CROSSING)
    step = territorial_path(v, "c", False, tm).steps[0]
    # Même déclarée « réversible », une frontière ne porte aucun effet identifié : U = 1, rien à « apprendre ».
    assert step.uncertainty == 1.0 and step.voi == 0.0
