"""Monde synthétique à vérité connue (M3 ; mondes A–F en M5).

Un champ de densité de population *vrai* est défini analytiquement : un fond
uniforme plus des bourgs gaussiens. Deux instruments l'observent :

- ``survey`` : des zones d'énumération (EA) de surface connue, comptées
  (bruit de Poisson), puis géomasquées (déplacement uniforme dans un disque) ;
- ``census`` : des totaux par district (grille de districts lon/lat), avec une
  erreur relative.

La vérité ne sert qu'à la **validation** (calibration) et n'existe que pour des
sources synthétiques : aucun chemin de code ne permet de l'associer à une source
réelle. Le territoire est placé en plein océan (Atlantique Sud).
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from functools import cached_property
from typing import Any

import numpy as np
import shapely
from shapely.geometry import Point, Polygon, box
from shapely.prepared import prep

from amtgo.errors import ConfigurationError
from amtgo.geo.crs import to_equal_area, to_wgs84
from amtgo.utils.canonical import content_hash


def _num(params: dict[str, Any], name: str, kind: type = float) -> Any:
    if name not in params:
        raise ConfigurationError(f"monde synthétique : paramètre {name!r} manquant")
    try:
        return kind(params[name])
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(f"monde synthétique : paramètre {name!r} invalide ({exc})") from exc


@dataclass(frozen=True)
class SyntheticWorld:
    """Paramètres du monde : identiques pour tous les instruments d'un même run."""

    seed: int
    bbox: tuple[float, float, float, float]
    background_density: float  # hab./km²
    n_towns: int
    town_peak_density: tuple[float, float]  # hab./km², bornes du tirage
    town_scale_km: tuple[float, float]  # écart-type spatial, bornes du tirage
    quadrature_km: float  # pas de la quadrature de vérité
    groups_hash: str = ""  # empreinte de la couche de groupes (M4), incluse dans world_hash

    @classmethod
    def from_params(cls, p: dict[str, Any]) -> SyntheticWorld:
        try:
            bbox = tuple(float(v) for v in p["bbox"])
            peak = tuple(float(v) for v in p["town_peak_density"])
            scale = tuple(float(v) for v in p["town_scale_km"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigurationError(f"monde synthétique : paramètre invalide ({exc})") from exc
        if len(bbox) != 4 or len(peak) != 2 or len(scale) != 2:
            raise ConfigurationError("monde synthétique : bbox (4), town_peak_density (2), town_scale_km (2)")
        return cls(
            seed=_num(p, "seed", int), bbox=bbox,
            background_density=_num(p, "background_density"), n_towns=_num(p, "n_towns", int),
            town_peak_density=peak, town_scale_km=scale,
            quadrature_km=_num(p, "quadrature_km"),
            groups_hash=content_hash(p["groups"]) if "groups" in p else "",
        )

    @property
    def world_hash(self) -> str:
        # Champs déclarés seulement : __dict__ contient aussi les valeurs mises en cache.
        return content_hash({f.name: getattr(self, f.name) for f in fields(self)})

    @cached_property
    def region_ea(self) -> Polygon:
        geom = to_equal_area(box(*self.bbox))
        assert isinstance(geom, Polygon)
        return geom

    @cached_property
    def towns(self) -> np.ndarray:
        """(n, 4) : x, y (m, LAEA), pic (hab./km²), échelle (m)."""
        rng = np.random.default_rng([self.seed, 1])
        pts = _uniform_in(self.region_ea, self.n_towns, rng)
        peak = rng.uniform(*self.town_peak_density, self.n_towns)
        scale = rng.uniform(*self.town_scale_km, self.n_towns) * 1000.0
        return np.column_stack([pts, peak, scale])

    def density(self, xy: np.ndarray) -> np.ndarray:
        """Densité vraie (hab./km²) aux points ``xy`` (m, LAEA), forme (n, 2)."""
        d = np.full(len(xy), self.background_density)
        for tx, ty, peak, s in self.towns:
            r2 = (xy[:, 0] - tx) ** 2 + (xy[:, 1] - ty) ** 2
            d += peak * np.exp(-r2 / (2.0 * s * s))
        return d

    @cached_property
    def quadrature(self) -> tuple[np.ndarray, float]:
        """Points de quadrature (m, LAEA) dans la région et surface élémentaire (km²)."""
        step = self.quadrature_km * 1000.0
        minx, miny, maxx, maxy = self.region_ea.bounds
        xs = np.arange(minx + step / 2, maxx, step)
        ys = np.arange(miny + step / 2, maxy, step)
        gx, gy = np.meshgrid(xs, ys)
        pts = np.column_stack([gx.ravel(), gy.ravel()])
        mask = shapely.contains_xy(self.region_ea, pts[:, 0], pts[:, 1])
        return pts[mask], self.quadrature_km**2

    def true_total(self, polygon_ea: Polygon) -> float:
        """Population vraie d'un polygone (LAEA) par quadrature."""
        pts, da = self.quadrature
        mask = shapely.contains_xy(polygon_ea, pts[:, 0], pts[:, 1])
        return float(self.density(pts[mask]).sum() * da) if mask.any() else 0.0


def _uniform_in(region: Polygon, n: int, rng: np.random.Generator) -> np.ndarray:
    inside = prep(region)
    minx, miny, maxx, maxy = region.bounds
    out: list[tuple[float, float]] = []
    while len(out) < n:
        x, y = rng.uniform(minx, maxx), rng.uniform(miny, maxy)
        if inside.contains(Point(x, y)):
            out.append((float(x), float(y)))
    return np.array(out).reshape(n, 2)


@dataclass(frozen=True)
class SurveyDesign:
    n_ea: int
    ea_area_km2: float
    displacement_km: float

    @classmethod
    def from_params(cls, p: dict[str, Any]) -> SurveyDesign:
        return cls(_num(p, "n_ea", int), _num(p, "ea_area_km2"), _num(p, "displacement_km"))


@dataclass(frozen=True)
class EnumerationArea:
    key: str
    true_xy: tuple[float, float]  # jamais publié : sert à la vérité seulement
    released_lonlat: tuple[float, float]
    count: int


def simulate_survey(world: SyntheticWorld, design: SurveyDesign) -> list[EnumerationArea]:
    rng = np.random.default_rng([world.seed, 2])
    xy = _uniform_in(world.region_ea, design.n_ea, rng)
    lam = world.density(xy) * design.ea_area_km2
    counts = rng.poisson(lam)
    # Géomasquage : déplacement uniforme en surface dans un disque (03 §6).
    r = design.displacement_km * 1000.0 * np.sqrt(rng.uniform(0, 1, design.n_ea))
    theta = rng.uniform(0, 2 * np.pi, design.n_ea)
    released = xy + np.column_stack([r * np.cos(theta), r * np.sin(theta)])
    out = []
    for k in range(design.n_ea):
        p = to_wgs84(Point(*released[k]))
        assert isinstance(p, Point)
        out.append(EnumerationArea(f"ea-{k:05d}", (float(xy[k, 0]), float(xy[k, 1])),
                                   (round(p.x, 6), round(p.y, 6)), int(counts[k])))
    return out


@dataclass(frozen=True)
class CensusDesign:
    districts_x: int
    districts_y: int
    relative_error: float

    @classmethod
    def from_params(cls, p: dict[str, Any]) -> CensusDesign:
        return cls(_num(p, "districts_x", int), _num(p, "districts_y", int), _num(p, "relative_error"))


@dataclass(frozen=True)
class District:
    key: str
    polygon: Polygon  # EPSG:4326
    reported_total: float
    reported_sd: float


def simulate_census(world: SyntheticWorld, design: CensusDesign) -> list[District]:
    rng = np.random.default_rng([world.seed, 3])
    minx, miny, maxx, maxy = world.bbox
    dx = (maxx - minx) / design.districts_x
    dy = (maxy - miny) / design.districts_y
    out = []
    for i in range(design.districts_x):
        for j in range(design.districts_y):
            poly = box(minx + i * dx, miny + j * dy, minx + (i + 1) * dx, miny + (j + 1) * dy)
            truth = world.true_total(to_equal_area(poly))
            sd = design.relative_error * truth
            reported = max(0.0, truth + rng.normal(0.0, sd))
            out.append(District(f"d-{i:02d}-{j:02d}", poly, round(reported, 1),
                                round(design.relative_error * reported, 1)))
    return out


# --- Couche identitaire FICTIVE (M4) ------------------------------------------------
#
# Catégories abstraites (alpha, beta…) sans rapport avec aucun groupe réel. Chaque
# bourg a une composition tirée autour d'un groupe d'ancrage ; le fond a une
# composition mêlée. La composition vraie en un point est la moyenne des
# compositions pondérée par les densités qui s'y superposent.


@dataclass(frozen=True)
class GroupLayer:
    categories: tuple[str, ...]
    background_weights: tuple[float, ...]
    town_concentration: float  # concentration de Dirichlet autour du groupe d'ancrage
    town_anchor_weight: float  # poids du groupe d'ancrage dans la moyenne de Dirichlet

    @classmethod
    def from_params(cls, p: dict[str, Any]) -> GroupLayer:
        try:
            cats = tuple(str(c) for c in p["categories"])
            bg = tuple(float(w) for w in p["background_weights"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigurationError(f"monde synthétique : couche de groupes invalide ({exc})") from exc
        if len(cats) != len(bg) or len(cats) < 2:
            raise ConfigurationError("monde synthétique : categories et background_weights incohérents")
        return cls(cats, bg, _num(p, "town_concentration"), _num(p, "town_anchor_weight"))


def group_layer(world_params: dict[str, Any]) -> GroupLayer | None:
    return GroupLayer.from_params(world_params["groups"]) if "groups" in world_params else None


def town_compositions(world: SyntheticWorld, layer: GroupLayer) -> np.ndarray:
    """(n_towns, K) : composition de chaque bourg."""
    rng = np.random.default_rng([world.seed, 4])
    k = len(layer.categories)
    out = np.zeros((world.n_towns, k))
    for t in range(world.n_towns):
        anchor = rng.integers(k)
        mean = np.full(k, (1.0 - layer.town_anchor_weight) / (k - 1))
        mean[anchor] = layer.town_anchor_weight
        out[t] = rng.dirichlet(mean * layer.town_concentration)
    return out


def composition(world: SyntheticWorld, layer: GroupLayer, xy: np.ndarray) -> np.ndarray:
    """(n, K) : composition vraie aux points ``xy`` (m, LAEA)."""
    bg = np.array(layer.background_weights) / sum(layer.background_weights)
    comp = np.outer(np.full(len(xy), world.background_density), bg)
    tc = town_compositions(world, layer)
    for (tx, ty, peak, s), c in zip(world.towns, tc, strict=True):
        r2 = (xy[:, 0] - tx) ** 2 + (xy[:, 1] - ty) ** 2
        comp += np.outer(peak * np.exp(-r2 / (2.0 * s * s)), c)
    return np.asarray(comp / comp.sum(axis=1, keepdims=True))


def simulate_identity_counts(world: SyntheticWorld, layer: GroupLayer, eas: list[EnumerationArea],
                             respondents: int) -> list[dict[str, int]]:
    """Auto-identification de ``respondents`` personnes par EA, à la position VRAIE de l'EA."""
    rng = np.random.default_rng([world.seed, 5])
    xy = np.array([ea.true_xy for ea in eas])
    comp = composition(world, layer, xy)
    return [dict(zip(layer.categories, (int(v) for v in rng.multinomial(respondents, comp[k])), strict=True))
            for k in range(len(eas))]


@dataclass(frozen=True)
class HistoricalBlock:
    key: str
    polygon: Polygon  # EPSG:4326
    label: str  # UN seul concept par bloc : la carte historique comprime la diversité


def simulate_historical_map(world: SyntheticWorld, layer: GroupLayer, blocks_x: int, blocks_y: int,
                            lumping: dict[str, str]) -> list[HistoricalBlock]:
    """Carte « historique » : chaque bloc porte la catégorie externe la plus représentée.

    C'est délibérément le défaut des cartes ethnographiques anciennes (01 §29) : une
    étiquette par zone, selon une classification extérieure qui regroupe des
    catégories. Elle sert à mesurer cette compression, jamais de vérité.
    """
    minx, miny, maxx, maxy = world.bbox
    dx, dy = (maxx - minx) / blocks_x, (maxy - miny) / blocks_y
    pts, da = world.quadrature
    dens = world.density(pts)
    comp = composition(world, layer, pts)
    ext = sorted(set(lumping.values()))
    out = []
    for i in range(blocks_x):
        for j in range(blocks_y):
            poly = box(minx + i * dx, miny + j * dy, minx + (i + 1) * dx, miny + (j + 1) * dy)
            mask = shapely.contains_xy(to_equal_area(poly), pts[:, 0], pts[:, 1])
            mass = (dens[mask, None] * comp[mask]).sum(axis=0) * da
            ext_mass = {e: sum(m for c, m in zip(layer.categories, mass, strict=True) if lumping[c] == e)
                        for e in ext}
            out.append(HistoricalBlock(f"h-{i:02d}-{j:02d}", poly, max(ext, key=lambda e: ext_mass[e])))
    return out


# --- Comptes fiscaux FICTIFS (M6) ---------------------------------------------------
#
# Recettes propres et coût d'un panier de services de référence, par district.
# Vérité analytique : la base fiscale par habitant croît avec la densité
# (agglomération), le coût des services par habitant décroît avec elle (économies
# de densité). Unités monétaires fictives.


@dataclass(frozen=True)
class FiscalDesign:
    districts_x: int
    districts_y: int
    relative_error: float
    revenue_base_pc: float
    revenue_agglomeration_pc: float
    revenue_half_density: float  # hab./km²
    cost_base_pc: float
    cost_sparsity_pc: float
    cost_reference_density: float  # hab./km²

    @classmethod
    def from_params(cls, p: dict[str, Any]) -> FiscalDesign:
        return cls(_num(p, "districts_x", int), _num(p, "districts_y", int), _num(p, "relative_error"),
                   _num(p, "revenue_base_pc"), _num(p, "revenue_agglomeration_pc"), _num(p, "revenue_half_density"),
                   _num(p, "cost_base_pc"), _num(p, "cost_sparsity_pc"), _num(p, "cost_reference_density"))

    def revenue_pc(self, density: np.ndarray) -> np.ndarray:
        return self.revenue_base_pc + self.revenue_agglomeration_pc * density / (density + self.revenue_half_density)

    def cost_pc(self, density: np.ndarray) -> np.ndarray:
        return self.cost_base_pc + self.cost_sparsity_pc * self.cost_reference_density / (
            density + self.cost_reference_density)


@dataclass(frozen=True)
class FiscalDistrict:
    key: str
    polygon: Polygon  # EPSG:4326
    revenue: float
    revenue_sd: float
    service_cost: float
    service_cost_sd: float


def simulate_fiscal(world: SyntheticWorld, design: FiscalDesign) -> list[FiscalDistrict]:
    rng = np.random.default_rng([world.seed, 6])
    minx, miny, maxx, maxy = world.bbox
    dx = (maxx - minx) / design.districts_x
    dy = (maxy - miny) / design.districts_y
    pts, da = world.quadrature
    dens = world.density(pts)
    out = []
    for i in range(design.districts_x):
        for j in range(design.districts_y):
            poly = box(minx + i * dx, miny + j * dy, minx + (i + 1) * dx, miny + (j + 1) * dy)
            mask = shapely.contains_xy(to_equal_area(poly), pts[:, 0], pts[:, 1])
            d = dens[mask]
            rev = float((d * design.revenue_pc(d)).sum() * da)
            cost = float((d * design.cost_pc(d)).sum() * da)
            e = design.relative_error
            rev_r = max(0.0, rev + rng.normal(0.0, e * rev))
            cost_r = max(0.0, cost + rng.normal(0.0, e * cost))
            out.append(FiscalDistrict(f"d-{i:02d}-{j:02d}", poly, round(rev_r, 1), round(e * rev_r, 1),
                                      round(cost_r, 1), round(e * cost_r, 1)))
    return out
