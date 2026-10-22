"""Red-team ADR-0028 : les données sous licence nominative ne sortent ni par Git, ni par l'image, ni par un chemin.

Les contrôles sur ``.gitignore``, ``.dockerignore`` et ``compose.yaml`` ne
s'exécutent que là où ces fichiers existent (CI, dépôt) ; le conteneur ``cli``
ne les monte pas.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from amtgo.data.sources import SourceManifest

REPO = Path(__file__).resolve().parents[2]


def _restricted_raw(configs_dir: Path, path: str) -> dict:
    raw = yaml.safe_load((configs_dir / "sources" / "natural_earth_admin0.yaml").read_text())
    raw.update(access="restricted", data_zone="RESTRICTED_LOCAL", privacy_class="CONTROLLED")
    raw["license"]["redistribution"] = False
    raw["retrieval"] = {"kind": "local", "adapter": "natural_earth",
                        "resources": [{"name": "f", "path": path, "sha256": "0" * 64}]}
    return raw


def test_restricted_source_reads_only_under_mount(configs_dir: Path) -> None:
    SourceManifest.model_validate(_restricted_raw(configs_dir, "/restricted/dhs/GHGE8AFL.zip"))


@pytest.mark.parametrize("path", ["/app/configs/x.zip", "restricted/x.zip", "/restricted/../etc/passwd",
                                  "/state/x.zip", "/restrictedx/y.zip"])
def test_restricted_source_outside_mount_refused(configs_dir: Path, path: str) -> None:
    with pytest.raises(ValueError, match="/restricted"):
        SourceManifest.model_validate(_restricted_raw(configs_dir, path))


def _need(name: str) -> Path:
    p = REPO / name
    if not p.exists():
        pytest.skip(f"{name} absent (conteneur cli) : contrôle exécuté en CI")
    return p


def test_restricted_ignored_by_git_and_docker() -> None:
    gitignore = _need(".gitignore").read_text().splitlines()
    assert "restricted/*" in gitignore and "!restricted/README.md" in gitignore
    assert "restricted" in _need(".dockerignore").read_text().splitlines()


def test_restricted_mounted_read_only() -> None:
    services = yaml.safe_load(_need("compose.yaml").read_text())["services"]
    for name in ("worker", "cli"):
        assert "./restricted:/restricted:ro" in services[name]["volumes"]
    for name in ("db", "gh"):
        assert not any("restricted" in str(v) for v in services[name].get("volumes", []))


def test_nothing_tracked_under_restricted_but_readme() -> None:
    _need(".git")
    try:
        out = subprocess.run(["git", "-C", str(REPO), "ls-files", "restricted"], capture_output=True,
                             text=True, check=True).stdout.split()
    except (FileNotFoundError, subprocess.CalledProcessError):
        pytest.skip("git indisponible")
    assert out == ["restricted/README.md"]
