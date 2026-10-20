# ADR-0002 — Image Debian slim et dépendances différées

*Statut : accepté — 2026-10-20.*

## Contexte
shapely, pyproj et h3 publient des wheels manylinux, pas musl. L'image Alpine du
squelette les compilerait (GEOS, PROJ) ou échouerait. 256 Mo ne suffisent pas.

## Décision
`python:3.12-slim`, `uv` avec `uv.lock` versionné, worker à 768 Mo. Rasterio,
xarray, GeoPandas et Pyomo sont **différés** : M0–M2 n'en ont pas besoin, et
chaque dépendance scientifique doit être justifiée par un milestone (§62).

## Conséquences
Image plus lourde (~400 Mo). Rasters (M3+) et solveurs (M10) ajouteront leurs
dépendances avec leur ADR.
