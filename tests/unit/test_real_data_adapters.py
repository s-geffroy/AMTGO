"""Adapters de données réelles (ADR-0028) : limites administratives, tableaux de totaux, WorldPop.

Toutes les données ici sont FICTIVES et placées en plein Atlantique Sud, comme le
monde synthétique : seuls les formats sont ceux des sources réelles.
"""

from __future__ import annotations

import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from amtgo.data.adapters.admin import (
    AdminBoundariesAdapter,
    AdminTableAdapter,
    exclude_rows,
    group_units,
    join_table,
    normalize_name,
)
from amtgo.data.adapters.worldpop import WorldPopAdapter
from amtgo.data.sources import SourceManifest
from amtgo.errors import ConfigurationError, DataLicenseError
from amtgo.geo.mesh import BBoxExtent, MeshDefinition, MeshFamily, bbox_geometry
from amtgo.geo.ops import create_base_mesh
from amtgo.measurement import raster_prior
from amtgo.measurement.likelihoods import MeshIndex

NOW = datetime(2026, 1, 1, tzinfo=UTC)
Q = {"source_reliability": 1, "spatial_precision": 1, "temporal_precision": 1, "construct_validity": 1,
     "representativeness": 1, "license_usability": 1, "privacy_usability": 1}


def square(x: float, y: float, w: float, h: float) -> dict[str, Any]:
    return {"type": "Polygon", "coordinates": [[[x, y], [x + w, y], [x + w, y + h], [x, y + h], [x, y]]]}


def regions_fc() -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"pcode": "TT01", "name": "Nord-Ouest", "shapeName": "North West"},
         "geometry": square(-25.0, -24.0, 2.0, 2.0)},
        {"type": "Feature", "properties": {"pcode": "TT02", "name": "Sud", "shapeName": "Mbeya"},
         "geometry": square(-25.0, -26.0, 2.0, 2.0)},
    ]}


def write_zip(path: Path, members: dict[str, Any]) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        for name, payload in members.items():
            z.writestr(name, json.dumps(payload))
    return path


def manifest(adapter: str, resources: list[dict[str, Any]], parameters: dict[str, Any],
             status: str = "D") -> SourceManifest:
    return SourceManifest.model_validate({
        "source_id": "fixture_src", "name": "fixture", "provider": "tests", "release": "1",
        "citation": "fictif", "license": {"license_id": "CC0", "name": "CC0", "redistribution": True,
                                          "commercial_use": True, "attribution_required": False},
        "access": "open", "data_zone": "OPEN_CORE", "privacy_class": "PUBLIC",
        "roles": {"allowed": ["population_measurement"]}, "method": "fictif",
        "temporal_start": "2021-06-27", "default_evidence_status": status, "quality": Q,
        "retrieval": {"kind": "local", "adapter": adapter,
                      "resources": [dict(r, sha256="0" * 64) for r in resources], "parameters": parameters},
    })


# --- limites administratives ----------------------------------------------------


def test_boundaries_from_zip_member(tmp_path: Path) -> None:
    z = write_zip(tmp_path / "b.zip", {"adm1.geojson": regions_fc()})
    m = manifest("admin_boundaries", [{"name": "b.zip", "path": str(z)}], {"layers": [
        {"resource": "b.zip", "member": "adm1.geojson", "variable": "admin1_polygon", "level": 1,
         "code_field": "pcode", "name_field": "name"}]})
    obs = list(AdminBoundariesAdapter().normalize(m, {"b.zip": z}, NOW))
    assert [o.admin_code for o in obs] == ["TT01", "TT02"]
    assert all(o.support_type.value == "ADMIN" and o.evidence_status.value == "D" for o in obs)


def test_license_read_in_metadata_must_match(tmp_path: Path) -> None:
    geo = tmp_path / "b.geojson"
    geo.write_text(json.dumps(regions_fc()))
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"boundaryLicense": "Open Data Commons Open Database License 1.0"}))
    params = {"layers": [{"resource": "b.geojson", "variable": "admin1_polygon", "code_field": "pcode",
                          "name_field": "name"}],
              "license_check": {"resource": "meta.json", "field": "boundaryLicense",
                                "expected": "Creative Commons Attribution 4.0 International (CC BY 4.0)"}}
    m = manifest("admin_boundaries", [{"name": "b.geojson", "path": str(geo)},
                                      {"name": "meta.json", "path": str(meta)}], params)
    with pytest.raises(DataLicenseError):
        list(AdminBoundariesAdapter().normalize(m, {"b.geojson": geo, "meta.json": meta}, NOW))


# --- tableaux de totaux ---------------------------------------------------------


def _units() -> dict[str, tuple[str, Any]]:
    from shapely.geometry import shape

    return {f["properties"]["pcode"]: (f["properties"]["shapeName"], shape(f["geometry"]))
            for f in regions_fc()["features"]}


def test_join_by_code_exhaustive() -> None:
    rows = [{"P": "TT01", "N": "x", "T": "100"}, {"P": "TT02", "N": "y", "T": "50"}]
    params = {"table": {"code_field": "P", "name_field": "N", "total_field": "T"}, "join": "code"}
    assert join_table(_units(), rows, params) == {"TT01": (100.0, ["TT01"]), "TT02": (50.0, ["TT02"])}
    with pytest.raises(ConfigurationError, match="lignes sans polygone"):
        join_table(_units(), [*rows, {"P": "TT03", "N": "z", "T": "1"}], params)
    with pytest.raises(ConfigurationError, match="polygones sans total"):
        join_table(_units(), rows[:1], params)


def test_join_by_name_aliases_merge_suffixes() -> None:
    rows = [{"N": "NORTH-WEST District", "T": "10"}, {"N": "MBEYA", "T": "7"}, {"N": "Songwe", "T": "3"}]
    params = {"table": {"code_field": "N", "name_field": "N", "total_field": "T"}, "join": "name",
              "strip_suffixes": ["District"], "merge": {"Mbeya": ["MBEYA", "SONGWE"]}}
    out = join_table(_units(), rows, params)
    assert out["TT01"][0] == 10.0 and out["TT02"] == (10.0, ["mbeya", "songwe"])
    # Sans la fusion déclarée, Songwe n'a pas de polygone : erreur, jamais omission silencieuse.
    with pytest.raises(ConfigurationError):
        join_table(_units(), rows, {**params, "merge": {}})


def test_table_observations_carry_declared_error_and_status(tmp_path: Path) -> None:
    geo = tmp_path / "b.geojson"
    geo.write_text(json.dumps(regions_fc()))
    csv_path = tmp_path / "t.csv"
    csv_path.write_text("P,N,T\nTT01,a,1000\nTT02,b,500\n")
    params = {"variable": "population_total_admin1", "relative_error": 0.05,
              "table": {"resource": "t.csv", "code_field": "P", "name_field": "N", "total_field": "T"},
              "boundaries": {"resource": "b.geojson", "code_field": "pcode", "name_field": "name"}}
    m = manifest("admin_table", [{"name": "t.csv", "path": str(csv_path)},
                                 {"name": "b.geojson", "path": str(geo)}], params, status="M")
    obs = {o.admin_code: o for o in AdminTableAdapter().normalize(m, {"t.csv": csv_path, "b.geojson": geo}, NOW)}
    v = obs["TT01"].value
    assert v is not None and v.mean == 1000.0 and v.std == pytest.approx(50.0)
    assert obs["TT02"].evidence_status.value == "M"  # une projection n'est jamais promue


def test_name_normalization() -> None:
    assert normalize_name("  Zanzibar  Urban/West ") == normalize_name("ZANZIBAR URBAN/WEST")
    assert normalize_name("Nord-Ouest") == "nord ouest"
    assert normalize_name("Ségou") == "segou"


# --- WorldPop et prior raster ---------------------------------------------------


def write_raster(path: Path, data: np.ndarray, west: float, north: float, res: float,
                 crs: str = "EPSG:4326") -> Path:
    import rasterio
    from rasterio.transform import from_origin

    with rasterio.open(path, "w", driver="GTiff", height=data.shape[0], width=data.shape[1], count=1,
                       dtype="float32", crs=crs, transform=from_origin(west, north, res, res),
                       nodata=-99999.0) as dst:
        dst.write(data.astype("float32"), 1)
    return path


def fixture_raster(tmp_path: Path) -> tuple[Path, np.ndarray]:
    rng = np.random.default_rng(3)
    data = rng.gamma(2.0, 5.0, size=(400, 200))
    data[:50, :] = -99999.0  # nodata : compte zéro, pas une valeur
    return write_raster(tmp_path / "pop.tif", data, -25.0, -22.0, 0.01), np.where(data < 0, 0.0, data)


def test_worldpop_single_raster_observation(tmp_path: Path) -> None:
    path, data = fixture_raster(tmp_path)
    m = manifest("worldpop", [{"name": "pop.tif", "path": str(path)}], {"variable": "population_prior_raster"},
                 status="M")
    (obs,) = list(WorldPopAdapter().normalize(m, {"pop.tif": path}, NOW))
    assert obs.support_type.value == "RASTER" and obs.raster_ref == "pop.tif@sha256:" + "0" * 64
    assert obs.attributes["raster_total"] == pytest.approx(float(data.sum()), rel=1e-5)


def test_worldpop_requires_wgs84(tmp_path: Path) -> None:
    path = write_raster(tmp_path / "p.tif", np.ones((10, 10)), 500000.0, 100000.0, 100.0, crs="EPSG:32630")
    m = manifest("worldpop", [{"name": "p.tif", "path": str(path)}], {"variable": "v"}, status="M")
    with pytest.raises(ConfigurationError, match="EPSG:4326"):
        list(WorldPopAdapter().normalize(m, {"p.tif": path}, NOW))


@pytest.mark.parametrize("block", [1, 3, 7])
def test_raster_cell_totals_conserve_mass(tmp_path: Path, block: int) -> None:
    path, data = fixture_raster(tmp_path)
    # Maillage plus petit que le raster : la masse hors maillage est rapportée, jamais redistribuée.
    ext = BBoxExtent(bbox=(-25.0, -26.0, -23.5, -22.5))
    mesh = create_base_mesh(MeshDefinition(mesh_id="tt", family=MeshFamily.GRID_LAEA, resolution=5,
                                           grid_base_km=400, extent=ext), bbox_geometry(ext))
    idx = MeshIndex(mesh)
    cells = raster_prior.cell_totals(path, idx, block)
    assert cells.raster_total == pytest.approx(float(data.sum()), rel=1e-9)
    assert cells.totals.sum() + cells.outside == pytest.approx(cells.raster_total, rel=1e-9)
    assert 0 < cells.outside < cells.raster_total
    dens = raster_prior.prior_density(cells, idx, 1.0)
    assert np.all(dens >= 1.0)


def test_group_boundaries_one_declared_margin() -> None:
    units = _units()
    grouped = group_units(units, {"Tout": ["North West", "Mbeya"]})
    (code, (name, geom)), = grouped.items()
    assert code == "group:TT01+TT02" and name == "Tout"
    assert geom.area == pytest.approx(sum(g.area for _, g in units.values()))
    with pytest.raises(ConfigurationError, match="introuvables"):
        group_units(units, {"X": ["North West", "Atlantis"]})


def test_flat_table_exclusions_and_patterns_on_both_sides() -> None:
    """Tableau plat (StatsBank) : agrégats et sous-métropoles retirés, statuts retirés des deux côtés."""
    rows = [{"N": "Pays", "T": "20"}, {"N": "North-West Metropolitan Area (NWMA)", "T": "10"},
            {"N": "NWMA-Centre", "T": "6"}, {"N": "NWMA-Port", "T": "4"}, {"N": "Mbeya Municipal", "T": "10"}]
    params = {"table": {"code_field": "N", "name_field": "N", "total_field": "T"}, "join": "name",
              "exclude_rows": ["Pays"], "exclude_rows_matching": ["^[A-Z]{2,5}-"],
              "strip_patterns": [r"\s*\([^)]*\)\s*$", r"\s+(Municipal|Metropolitan Area)\s*$"]}
    kept, n = exclude_rows(rows, params)
    assert n == 3  # la métropole n'est pas comptée deux fois avec ses sous-métropoles
    out = join_table(_units(), kept, params)
    assert out["TT01"][0] == 10.0 and out["TT02"][0] == 10.0
    with pytest.raises(ConfigurationError, match="absentes du tableau"):
        exclude_rows(rows, {**params, "exclude_rows": ["Pays", "Inexistant"]})


def test_expected_total_guards_exclusions(tmp_path: Path) -> None:
    geo = tmp_path / "b.geojson"
    geo.write_text(json.dumps(regions_fc()))
    csv_path = tmp_path / "t.csv"
    csv_path.write_text("P,N,T\nTT01,a,1000\nTT02,b,500\n")
    params = {"variable": "population_total_admin1", "relative_error": 0.05, "expected_total": 1500,
              "table": {"resource": "t.csv", "code_field": "P", "name_field": "N", "total_field": "T"},
              "boundaries": {"resource": "b.geojson", "code_field": "pcode", "name_field": "name"}}
    files = {"t.csv": csv_path, "b.geojson": geo}
    res = [{"name": "t.csv", "path": str(csv_path)}, {"name": "b.geojson", "path": str(geo)}]
    assert len(list(AdminTableAdapter().normalize(manifest("admin_table", res, params), files, NOW))) == 2
    wrong = manifest("admin_table", res, {**params, "expected_total": 1600})
    with pytest.raises(ConfigurationError, match="total déclaré"):
        list(AdminTableAdapter().normalize(wrong, files, NOW))
