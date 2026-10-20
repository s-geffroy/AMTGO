# M2 — Cœur spatial

## Fait

- `MeshDefinition`, `Cell`, `Mesh` ; familles `h3` et `grid_laea` ([ADR-0007](../decisions/ADR-0007-maillages-distance.md)).
- API du §15 : `create_base_mesh`, `refine_mesh`, `coarsen_mesh`, `neighbors`, `parent`, `children`. Déterministe : identifiants triés, `cells_hash` stable.
- Surfaces toujours en projection équivalente, avec densification des arêtes avant projection ([ADR-0008](../decisions/ADR-0008-projection.md)).
- Invariants vérifiés avant persistance :
  - géométries valides ;
  - aires positives ;
  - non-recouvrement au même niveau ;
  - **union des cellules = emprise**.
- Opérations multi-échelles :
  - transfert pondéré par l'aire, avec masse non couverte rapportée ;
  - affectation des points géomasqués par noyau déterministe, sans point-in-polygon naïf ;
  - `partition_distance` (TRANSFER par défaut, VI en variante).
- Persistance (`mesh_definitions`, `cells`).
- Carte publique : pays actuels, frontières disputées, maillages H3 r3 et grille 200 km.

## Résultats du pilote synthétique

Les quatre maillages (H3 r5 et r6, grille 25 km et 12,5 km) couvrent exactement le même domaine (180 281 km²). Les transferts entre familles conservent la masse à 1e-6 près en relatif. La masse non affectée est identique pour les quatre maillages (≈ 1,6 %) : c'est la part réelle des noyaux de déplacement qui déborde du domaine, et le rapport l'affiche.

Le run continental de la carte (Natural Earth, H3 r3 et grille L1) couvre 29,89 M km², cohérent avec la surface de l'Afrique au 1:50m.

## Challenge — ce qui a cassé et a été corrigé

| problème trouvé | correction |
|---|---|
| règle « centre dans l'emprise » : bande de bord non couverte, différente selon le maillage, d'où 2 à 6 % de masse perdue dans les transferts | cellules qui intersectent l'emprise, découpées sur elle ; invariant de couverture ; migration 0004 |
| emprise projetée avec 4 sommets : côtés droits en LAEA alors qu'ils sont courbes | densification systématique avant projection |
| voisinage d'index trompeur pour des cellules découpées | voisinage géométrique (frontière partagée de longueur positive) |
| VI normalisée très sévère aux bords (≈ 0,49 pour un même découpage) | distance de transfert par défaut, VI conservée en variante |
| moyenne flottante > quantile d'un ULP, trouvé par hypothesis | tolérance relative explicite |

## Manquant

- Raffinement adaptatif (07 §7) : exige les champs latents de M3.
- `compare_across_meshes` et $S_{scale}$ : exigent des partitions candidates (M8). La distance existe déjà.

## Tests

Validité, déterminisme, couverture exacte, emprise plus fine qu'une cellule, symétrie du voisinage, cohérence parent / enfants, imbrication exacte de la grille, aires en km² (jamais en degrés²), conservation (exacte et entre familles), identité et ordre des distances, propriétés hypothesis (bornes, symétrie, conservation).

## Benchmarks

Indicatifs, CPU unique du VPS :
- pilote synthétique complet (8 étapes, 4 maillages jusqu'à 4 777 cellules) : ~7 s de calcul ;
- run continental : ~6 s.

## Dette technique

- Les cellules H3 découpées sur le trait de côte peuvent être multi-surfaciques ; leur usage en M5 (voisinage, flux) devra être documenté.
- La tolérance de couverture (1e-3 relatif) reflète la densification à ~5 km ; à resserrer si des maillages plus fins l'exigent.

## Prochain milestone

M3 — modèles de mesure (après revue).
