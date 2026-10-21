"""Red-team Map-C-Deep : branche de recherche séparée, aucun coefficient contemporain, aucune carte."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from amtgo.config.settings import Settings
from amtgo.errors import ConfigurationError
from amtgo.manifests.c_deep import CDeepRequest
from amtgo.runs.queue import submit

SRC = Path(__file__).resolve().parents[2] / "src" / "amtgo"


def _request(configs_dir: Path) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((configs_dir / "research" / "c_deep_synthetic.yaml").read_text())
    return data


def test_c_deep_is_never_a_product_run_mode(settings: Settings, configs_dir: Path) -> None:
    data = yaml.safe_load((configs_dir / "runs" / "smoke.yaml").read_text())
    p = configs_dir / "runs" / "deep.yaml"
    p.write_text(yaml.safe_dump(dict(data, map_mode="C_DEEP")))
    with pytest.raises(ConfigurationError, match="kind: c_deep"):
        submit(p, settings)


@pytest.mark.parametrize("extra", ["causal_library", "sources", "normative_manifest"])
def test_no_contemporary_inputs(configs_dir: Path, extra: str) -> None:
    """04 §20 : jamais de coefficients contemporains extrapolés ; aucune source réelle."""
    with pytest.raises(ValidationError, match="Extra inputs"):
        CDeepRequest.model_validate({**_request(configs_dir), extra: "causal/library_pilot.yaml"})


def test_structural_uncertainty_must_stay_represented(configs_dir: Path) -> None:
    data = _request(configs_dir)
    with pytest.raises(ValidationError):
        CDeepRequest.model_validate({**data, "models": ["border_friction"]})
    with pytest.raises(ValidationError):
        CDeepRequest.model_validate({**data, "validation": {**data["validation"], "min_structural_forms": 1}})


def test_counterfactual_changes_institutions_only(configs_dir: Path) -> None:
    data = _request(configs_dir)
    moved = {**data["history"], "counterfactual": [{"year": 1885, "capitals": [[3, 8]],
                                                    "population_transfer": {"from": "east", "to": "west"}}]}
    with pytest.raises(ValidationError, match="Extra inputs"):
        CDeepRequest.model_validate({**data, "history": moved})


def test_branch_is_isolated_from_the_product() -> None:
    research = "".join((SRC / "research" / f).read_text() for f in ("historical_scm.py", "c_deep.py"))
    stages = (SRC / "runs" / "c_deep_stages.py").read_text()
    for forbidden in ("amtgo.causal", "amtgo.optimization", "amtgo.export", "amtgo.privacy"):
        assert forbidden not in research + stages
    assert not re.search(r"ctx\.repo|Repository|record_", stages)  # rien en base : ni archive, ni solution
    assert '"published": False, "features": []' in stages
    # La vérité synthétique n'est lue que pour calibrer, après l'estimation.
    reads = [m.start() for m in re.finditer(r"read_json\(ctx.run_dir, \"artifacts/synthetic_truth.json\"\)", stages)]
    assert len(reads) == 1 and stages.index("def counterfactual_stage") < reads[0]
    assert "truth" not in (SRC / "research" / "c_deep.py").read_text().split("def estimate(")[1].split("\ndef ")[0]
