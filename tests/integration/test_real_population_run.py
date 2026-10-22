"""Run de population au format des données réelles (ADR-0028), sur un mini-jeu FICTIF hors ligne.

Même chaîne que ``gha_population_2021`` : polygones zippés (COD-AB), tableau de
totaux joint par code (COD-PS), raster en prior (WorldPop), recalage sur les
marges. Le jeu est placé en plein Atlantique Sud : seuls les formats sont réels.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import numpy as np
import pytest
import yaml

from amtgo.config.settings import Settings
from amtgo.db.repository import NullRepository
from amtgo.errors import ConfigurationError, ForbiddenSourceRole
from amtgo.measurement.fields import read_field
from amtgo.runs import artifacts
from amtgo.runs.queue import run_to_completion, runs_dir, submit
from amtgo.runs.state import RunStatus
from amtgo.utils.canonical import file_sha256

TOTALS = {"TT01": 400_000.0, "TT02": 150_000.0}
# Districts fictifs (benchmark A1) : quatre carrés de 1° par région, parts inégales des totaux régionaux.
SHARES = (0.4, 0.3, 0.2, 0.1)


def _square(x: float, y: float) -> dict:
    return {"type": "Polygon", "coordinates": [[[x, y], [x + 2, y], [x + 2, y + 2], [x, y + 2], [x, y]]]}


def _write_inputs(data: Path) -> tuple[Path, Path, Path, Path]:
    import rasterio
    from rasterio.transform import from_origin

    regions = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"pcode": "TT01", "name": "Nord"}, "geometry": _square(-25.0, -24.0)},
        {"type": "Feature", "properties": {"pcode": "TT02", "name": "Sud"}, "geometry": _square(-25.0, -26.0)},
    ]}
    districts, rows = [], []
    for code, (x0, y0) in (("TT01", (-25.0, -24.0)), ("TT02", (-25.0, -26.0))):
        for k, (dx, dy) in enumerate(((0, 0), (1, 0), (0, 1), (1, 1))):
            geom = {"type": "Polygon", "coordinates": [[[x0 + dx, y0 + dy], [x0 + dx + 1, y0 + dy],
                                                         [x0 + dx + 1, y0 + dy + 1], [x0 + dx, y0 + dy + 1],
                                                         [x0 + dx, y0 + dy]]]}
            districts.append({"type": "Feature", "properties": {"pcode": f"{code}{k}", "name": f"{code}{k}"},
                              "geometry": geom})
            rows.append(f"{code}{k},{code}{k},{int(TOTALS[code] * SHARES[k])}\n")
    z = data / "bnd.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("adm1.geojson", json.dumps(regions))
        zf.writestr("adm2.geojson", json.dumps({"type": "FeatureCollection", "features": districts}))
    table2 = data / "pop2.csv"
    table2.write_text("PCODE,NAME,T_TL\n" + "".join(rows))
    table = data / "pop.csv"
    table.write_text("PCODE,NAME,T_TL\n" + "".join(f"{k},{k},{int(v)}\n" for k, v in TOTALS.items()))
    rng = np.random.default_rng(11)
    raster = rng.gamma(1.5, 4.0, size=(400, 200))
    raster[:40, 150:] = 0.0  # zone sans bâti détecté : le plancher s'applique, pas un zéro
    tif = data / "pop.tif"
    with rasterio.open(tif, "w", driver="GTiff", height=400, width=200, count=1, dtype="float32",
                       crs="EPSG:4326", transform=from_origin(-25.0, -22.0, 0.01, 0.01)) as dst:
        dst.write(raster.astype("float32"), 1)
    return z, table, tif, table2


def _source(sid: str, adapter: str, files: list[Path], params: dict, status: str, roles: list[str],
            forbidden: list[str] | None = None) -> dict:
    return {
        "source_id": sid, "name": sid, "provider": "tests", "release": "1", "citation": "fictif",
        "license": {"license_id": "CC0", "name": "CC0", "redistribution": True, "commercial_use": True,
                    "attribution_required": False},
        "access": "open", "data_zone": "OPEN_CORE", "privacy_class": "PUBLIC",
        "roles": {"allowed": roles, "forbidden": forbidden or []}, "method": "fictif",
        "temporal_start": "2021-01-01", "temporal_end": "2021-12-31", "default_evidence_status": status,
        "quality": {k: 1.0 for k in ("source_reliability", "spatial_precision", "temporal_precision",
                                     "construct_validity", "representativeness", "license_usability",
                                     "privacy_usability")},
        "retrieval": {"kind": "local", "adapter": adapter, "parameters": params,
                      "resources": [{"name": f.name, "path": str(f), "sha256": file_sha256(f)} for f in files]},
    }


@pytest.fixture
def real_format_run(configs_dir: Path, tmp_path: Path) -> str:
    data = tmp_path / "real_format"
    data.mkdir()
    z, table, tif, table2 = _write_inputs(data)
    layer = {"resource": "bnd.zip", "member": "adm1.geojson", "code_field": "pcode", "name_field": "name"}
    sources = {
        "tt_admin": _source("tt_admin", "admin_boundaries", [z],
                            {"layers": [dict(layer, variable="admin1_polygon", level=1)]}, "P",
                            ["status_quo_geometry", "analysis_extent"]),
        "tt_census": _source("tt_census", "admin_table", [table, z], {
            "variable": "population_total_admin1", "relative_error": 0.02, "join": "code",
            "table": {"resource": "pop.csv", "code_field": "PCODE", "name_field": "NAME", "total_field": "T_TL"},
            "boundaries": layer}, "D", ["population_measurement", "multiscale_validation"]),
        "tt_worldpop": _source("tt_worldpop", "worldpop", [tif], {"variable": "population_prior_raster"}, "M",
                               ["population_prior"], ["population_measurement"]),
        "tt_districts": _source("tt_districts", "admin_table", [table2, z], {
            "variable": "population_total_admin2", "relative_error": 0.02, "join": "code",
            "table": {"resource": "pop2.csv", "code_field": "PCODE", "name_field": "NAME", "total_field": "T_TL"},
            "boundaries": dict(layer, member="adm2.geojson")}, "D", ["multiscale_validation"]),
    }
    for sid, raw in sources.items():
        (configs_dir / "sources" / f"{sid}.yaml").write_text(yaml.safe_dump(raw, sort_keys=False))
    measurement = yaml.safe_load((configs_dir / "measurement" / "gha_population_2021.yaml").read_text())
    measurement["prior"].update(source_id="tt_worldpop", block_pixels=2)
    measurement["likelihoods"][0]["source_id"] = "tt_census"
    measurement["sampling"]["n_samples"] = 60
    measurement["benchmark"].update(source_id="tt_districts", variable_id="population_total_admin2")
    (configs_dir / "measurement" / "tt_population.yaml").write_text(yaml.safe_dump(measurement))
    for mid, res in (("tt_grid_l5", 5), ("tt_grid_l6", 6)):
        (configs_dir / "meshes" / f"{mid}.yaml").write_text(yaml.safe_dump({
            "mesh_id": mid, "family": "grid_laea", "resolution": res, "grid_base_km": 400,
            "extent": {"kind": "source_union", "source_id": "tt_admin", "variable_id": "admin1_polygon"}}))
    run = yaml.safe_load((configs_dir / "runs" / "gha_population_2021.yaml").read_text())
    run.update(name="tt_population", region="testland", measurement_model="measurement/tt_population.yaml",
               mesh_set=["meshes/tt_grid_l5.yaml", "meshes/tt_grid_l6.yaml"],
               sources=[{"manifest": "sources/tt_admin.yaml", "roles": ["status_quo_geometry", "analysis_extent"]},
                        {"manifest": "sources/tt_census.yaml",
                         "roles": ["population_measurement", "multiscale_validation"]},
                        {"manifest": "sources/tt_worldpop.yaml", "roles": ["population_prior"]},
                        {"manifest": "sources/tt_districts.yaml", "roles": ["multiscale_validation"]}])
    (configs_dir / "runs" / "tt_population.yaml").write_text(yaml.safe_dump(run))
    return "runs/tt_population.yaml"


def test_real_format_population_run(settings: Settings, real_format_run: str) -> None:
    manifest, _ = submit(settings.configs_dir / real_format_run, settings)
    state = run_to_completion(settings, NullRepository(), str(manifest.run_id))
    assert state.status is RunStatus.SUCCEEDED, state.error
    d = runs_dir(settings) / str(manifest.run_id)
    for mesh_id in ("tt_grid_l5", "tt_grid_l6"):
        prior = artifacts.read_json(d, f"fields/{mesh_id}/prior.json")
        assert prior["summary"]["cells_at_floor"] > 0  # la zone vide est planchée, pas mise à zéro
        _, _, samples = read_field(d, mesh_id)
        # Chaque tirage est recalé sur les marges : le total suit le recensement, pas WorldPop.
        totals = samples.sum(axis=1)
        assert abs(totals.mean() - sum(TOTALS.values())) / sum(TOTALS.values()) < 0.01
        val = artifacts.read_json(d, f"fields/{mesh_id}/validation.json")
        assert val["calibration"]["status"] == "not_available"  # pas de vérité sur données réelles
    bench = artifacts.read_json(d, "artifacts/population_benchmark.json")
    for mesh_id in ("tt_grid_l5", "tt_grid_l6"):
        pm = bench["per_mesh"][mesh_id]
        assert pm["units"] == 8 and set(pm["variants"]) == {"indep_s100", "indep_s050", "laea50_s100", "laea50_s050",
                                                              "laea50_s030", "district_s050", "multiscale_s050"}
        assert pm["cv"]["status"] == "done"
    assert isinstance(bench["gate_a1"]["passed"], bool)  # le gate conclut, dans un sens ou dans l'autre
    report = (d / "report.md").read_text()
    assert "NOT_IDENTIFIABLE" in report
    assert "Benchmark du modèle spatial (A1)" in report
    assert not (d / "artifacts" / "validation.json").exists()  # aucun candidat, aucun gate de publication


def test_prior_source_cannot_be_an_observation(settings: Settings, real_format_run: str) -> None:
    """WorldPop interdit en observation : refusé à la résolution du manifeste, avant toute exécution."""
    run = yaml.safe_load((settings.configs_dir / real_format_run).read_text())
    for s in run["sources"]:
        if s["manifest"].endswith("tt_worldpop.yaml"):
            s["roles"] = ["population_measurement"]
    (settings.configs_dir / "runs" / "bad.yaml").write_text(yaml.safe_dump(run))
    with pytest.raises((ConfigurationError, ForbiddenSourceRole)):
        submit(settings.configs_dir / "runs" / "bad.yaml", settings)


def test_repository_real_runs_resolve(configs_dir: Path) -> None:
    """Les quatre runs réels préparés se résolvent hors ligne (aucune donnée récupérée ici)."""
    from amtgo.manifests.run import RunRequest, resolve_request

    for name in ("gha_population_2021", "zmb_population_2020", "tza_population_2020", "mwi_population_2023"):
        req = RunRequest.model_validate(yaml.safe_load((configs_dir / "runs" / f"{name}.yaml").read_text()))
        m = resolve_request(req, configs_dir)
        assert m.measurement_model is not None and m.measurement_model.prior.kind == "raster_lognormal_density"
        assert json.dumps(m.request.model_dump(mode="json"))
