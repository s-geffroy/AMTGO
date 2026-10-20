"""Fixtures partagées. Les tests tournent dans le service 'cli', jamais sur l'hôte."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from hypothesis import settings as hypothesis_settings

from amtgo.config.settings import Settings
from amtgo.utils.canonical import file_sha256

# Pas de base d'exemples sur disque : le code est monté en lecture seule.
hypothesis_settings.register_profile("amtgo", database=None)
hypothesis_settings.load_profile("amtgo")

REPO = Path(__file__).resolve().parents[1]
CONFIGS = REPO / "configs"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def configs_dir(tmp_path: Path) -> Path:
    """Copie de configs/ modifiable par le test, plus deux runs légers pour la mécanique de file."""
    import yaml

    dst = tmp_path / "configs"
    shutil.copytree(CONFIGS, dst)
    pilot = yaml.safe_load((dst / "runs" / "synthetic_pilot.yaml").read_text())
    light = dict(pilot, name="light", mesh_set=["meshes/pilot_grid_l4.yaml"])
    for key in ("measurement_model", "composition_model", "ontology_set"):
        light.pop(key)
    (dst / "runs" / "light.yaml").write_text(yaml.safe_dump(light))
    (dst / "runs" / "light_measure.yaml").write_text(
        yaml.safe_dump(dict(pilot, name="light_measure", mesh_set=["meshes/pilot_grid_l4.yaml"])))
    return dst


@pytest.fixture
def settings(tmp_path: Path, configs_dir: Path) -> Settings:
    return Settings(state_dir=tmp_path / "state", configs_dir=configs_dir, db_host=None)


def _square(x: float, y: float, s: float) -> dict:
    return {"type": "Polygon", "coordinates": [[[x, y], [x + s, y], [x + s, y + s], [x, y + s], [x, y]]]}


@pytest.fixture
def ne_mini(configs_dir: Path, tmp_path: Path) -> Path:
    """Mini-jeu au format Natural Earth (deux carrés FICTIFS), source locale épinglée.

    Ne sert qu'aux tests du pipeline : aucune de ces géométries n'est publiée.
    """
    data = tmp_path / "ne_mini"
    data.mkdir()
    countries = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"ADM0_A3": "TSA", "NAME": "Testland A", "TYPE": "Test",
                                            "CONTINENT": "Africa", "POP_EST": 1},
         "geometry": _square(10.0, 0.0, 4.0)},
        {"type": "Feature", "properties": {"ADM0_A3": "TSB", "NAME": "Testland B", "TYPE": "Test",
                                            "CONTINENT": "Africa"},
         "geometry": _square(14.0, 0.0, 4.0)},
        {"type": "Feature", "properties": {"ADM0_A3": "XEU", "NAME": "Elsewhere", "CONTINENT": "Europe"},
         "geometry": _square(10.0, 50.0, 2.0)},
    ]}
    lines = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"NE_ID": 1, "FEATURECLA": "Disputed (please verify)", "NAME": "x"},
         "geometry": {"type": "LineString", "coordinates": [[14.0, 0.0], [14.0, 4.0]]}},
    ]}
    (data / "countries.geojson").write_text(json.dumps(countries))
    (data / "lines.geojson").write_text(json.dumps(lines))
    src = (CONFIGS / "sources" / "natural_earth_admin0.yaml").read_text()
    import yaml

    m = yaml.safe_load(src)
    m["source_id"] = "ne_mini"
    m["retrieval"] = {
        "kind": "local", "adapter": "natural_earth",
        "resources": [
            {"name": "countries.geojson", "path": str(data / "countries.geojson"),
             "sha256": file_sha256(data / "countries.geojson")},
            {"name": "lines.geojson", "path": str(data / "lines.geojson"),
             "sha256": file_sha256(data / "lines.geojson")},
        ],
        "parameters": {"continent": "Africa", "bbox": [-26.0, -36.0, 64.0, 38.0],
                       "layers": {"countries.geojson": "admin0_polygon",
                                  "lines.geojson": "admin0_boundary_line"}},
    }
    path = configs_dir / "sources" / "ne_mini.yaml"
    path.write_text(yaml.safe_dump(m, sort_keys=False))
    for mid, fam, res, extra in (("mini_h3_r3", "h3", 3, {}),
                                 ("mini_grid_l2", "grid_laea", 2, {"grid_base_km": 400})):
        (configs_dir / "meshes" / f"{mid}.yaml").write_text(yaml.safe_dump({
            "mesh_id": mid, "family": fam, "resolution": res, **extra,
            "extent": {"kind": "source_union", "source_id": "ne_mini", "variable_id": "admin0_polygon"},
        }))
    run = {
        "name": "mini_pages", "description": "test", "region": "testland",
        "constitutional_regime": "R0", "normative_manifest": "normative/default.yaml",
        "sources": [{"manifest": "sources/ne_mini.yaml", "roles": ["basemap_display", "analysis_extent"],
                     "redistribute": True}],
        "mesh_set": ["meshes/mini_h3_r3.yaml", "meshes/mini_grid_l2.yaml"],
    }
    run_path = configs_dir / "runs" / "mini_pages.yaml"
    run_path.write_text(yaml.safe_dump(run))
    return run_path
