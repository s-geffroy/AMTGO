# ADR-0008 — Projection équivalente pour toute surface et distance

*Statut : accepté — 2026-10-20.*

## Décision
Stockage en EPSG:4326. Surfaces et distances en Lambert azimutale équivalente
centrée sur l'Afrique (`+proj=laea +lat_0=5 +lon_0=20`). L'aire des cellules de
grille est définie exactement (côté²) dans cet espace ; celle des cellules H3 est
calculée par reprojection. Aucun calcul métrique en degrés (prompt §64), vérifié
par test.

## Conséquences
La déformation angulaire loin du centre n'affecte pas les surfaces. Pour des
distances précises à longue portée (M5, mobilité), un calcul géodésique sera
préféré.
