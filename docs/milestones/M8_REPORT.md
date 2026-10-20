# M8 — Générateur de candidats

## Fait

- **Modèle** : familles de candidats, manifeste du générateur, `TerritoryCandidate` (schéma 10 §7). Les baselines sont obligatoires et leur portée est déclarée ([ADR-0020](../decisions/ADR-0020-candidats.md)).
- **Algorithmes** déterministes et multi-départ : k-means pondéré (libre ou amorcé sur le statu quo), coupe spectrale normalisée, Louvain.
- **Invariants** : réparation de contiguïté, étiquettes canoniques, doublons signalés.
- **Familles indisponibles** déclarées avec leur raison : historique (rôle dédié absent), linguistique (non implémentée, revue d'éthique requise), mobilité (aucun flux).
- **Pipeline** : `candidates:<maillage>` puis `candidate_ensemble`.
  - S^scale est calculé par variante, avec la distance TRANSFER sur la grille de référence.
  - Le noyau de liens est partagé avec D/F/I grâce à un cache.
- **Base** : migration 0009 (`territory_candidates`). Les géométries sont valides et `active` reste toujours faux.
- **CLI** : `amtgo candidates list <run>`.

## Résultats (pilote)

| famille | variantes | stables (S^scale ≥ 0,8) |
|---|---|---|
| baselines (×3) | 3 | 3 (0,98) |
| GEOGRAPHIC, k = 1…4 | 4 | 4 (0,96–1,00) |
| GEOGRAPHIC_SEEDED, k = 2 | 1 | 1 (0,97) |
| GRAPH_SPECTRAL, k = 1…4 | 4 | 4 (0,93–1,00) |
| GRAPH_COMMUNITY, résolution 0,3 / 1 / 3 | 3 | **0** (0,48–0,61 ; 6 à 44 communautés selon le maillage) |

- Tous les candidats sont contigus sur les quatre maillages.
- Le statut de recommandation reste NOT_IDENTIFIABLE : aucun candidat n'est évalué, aucun n'est publié.

## Challenge

Trois risques traités (ADR-0020) :

- la sélection implicite d'un « nombre d'États optimal » ;
- l'instabilité de Louvain, désormais rapportée plutôt que masquée ;
- une carte ethnographique utilisée comme graine historique.

## Manquant

- Les familles linguistique et mobilité, qui demandent des données, une ontologie linguistique et une revue d'éthique.
- La famille historique sur des sources réelles, qui demande des frontières administratives historiques déclarées.
- L'évaluation des candidats (D/F/I, viabilité, coûts), qui relève de M10.

## Tests

- **Unitaires** :
  - étiquettes canoniques ;
  - k-means séparant deux nuages et déterministe, avec le cas de l'union ;
  - coupe spectrale et Louvain qui passent par le lien faible ;
  - réparation de contiguïté, et île conservée ;
  - manifeste : nombres d'États valides et aucune pénalité déclarable ;
  - baselines et leur portée.
- **Red-team** :
  - le générateur ne lit jamais la composition ;
  - la carte publique ne lit jamais les candidats ;
  - la carte ethnographique est refusée comme graine ;
  - le maillage de référence doit appartenir au run.
- **Intégration** :
  - baselines présentes sur chaque maillage, contiguïté, familles indisponibles ;
  - S^scale du statu quo ≥ 0,8 ;
  - balayage complet de k ;
  - base : territoires enregistrés, aucun actif.

## Benchmarks

Génération sur H3 r6 (4 777 cellules) : 5 s environ. Ensemble S^scale : moins d'une seconde.

## Prochain milestone

M9 — composeur institutionnel à géométrie fixe, qui doit pouvoir conclure « NO BORDER CHANGE » (après revue).
