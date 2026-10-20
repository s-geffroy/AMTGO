"""Red-team M10 : jamais une seule « meilleure » solution, pas de pénalité au nombre d'États, pas de relaxation."""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "amtgo"


def _identifiers(path: Path) -> set[str]:
    out = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.FunctionDef):
            out.add(node.name)
        elif isinstance(node, ast.Attribute):
            out.add(node.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.add(node.value)
    return out


def test_no_single_best_solution_and_no_state_count_penalty() -> None:
    """Prompt §41-42 : archive obligatoire ; ``loss += lambda_states * number_of_states`` interdit."""
    files = [*sorted((SRC / "optimization").glob("*.py")), SRC / "runs" / "optimizer_stages.py"]
    for path in files:
        ids = _identifiers(path)
        assert "best_solution" not in ids, path
        assert not {i for i in ids if "lambda_state" in i or "state_count_penalty" in i}, path


def test_unknown_objective_is_never_zero() -> None:
    from amtgo.optimization.objectives import OBJECTIVES, UNKNOWN_OBJECTIVES

    assert "J_R" in UNKNOWN_OBJECTIVES and set(UNKNOWN_OBJECTIVES) <= set(OBJECTIVES)
    src = (SRC / "runs" / "optimizer_stages.py").read_text()
    assert '"J_R": None' in src and '"J_R": 0' not in src


def test_rights_violation_makes_infeasible_not_penalized() -> None:
    """Une violation sur un seul ω exclut la variante : la contrainte de droits n'est jamais un poids."""
    from amtgo.optimization.pareto import Solution, nondominated_sort

    good = Solution("g", "f", {}, {"J_D": 0.9, "J_F": 0.9}, True)
    excellent_but_violating = Solution("v", "f", {}, {"J_D": 0.0, "J_F": 0.0}, False, ["droits:x|land (ω=m/o)"])
    nondominated_sort([good, excellent_but_violating], {"J_D": 0.01, "J_F": 0.01})
    assert good.rank == 1 and excellent_but_violating.rank is None
