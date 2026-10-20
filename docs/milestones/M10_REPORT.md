# M10 — Optimiseur régional (archive de Pareto robuste)

## Fait

- **Objectifs** J_D, J_F, J_conn, J_V, J_G, J_R (UNKNOWN), J_T, J_inst, J_reif pour toute géométrie candidate ([ADR-0022](../decisions/ADR-0022-optimiseur-regional.md)). Le gabarit institutionnel du statu quo est appliqué par emboîtement.
- **Robustesse** : ρ = E + λ·CVaR + λ·Var sur maillages × ontologies.
- **Dominance** : ε-dominance par objectif, tri non dominé, contrainte de droits dure, certificat d'infaisabilité sans relaxation.
- **Archive** : rangs, baselines, conclusion, biais connus, S^ontology et S^scale par variante. S_publish vaut UNKNOWN, donc la publication est bloquée.
- **Gate O** : benchmark exact (énumération des bipartitions contiguës) de chaque heuristique sur son critère, en 5 départs, plus un test Goodhart « micro-territoires ».
- **Pipeline** : `evaluate_candidates:<maillage>` puis `pareto`. Viabilité calculée par partition (comptes fiscaux par cellule).
- **Base** : migration 0011 (`solutions`, jamais `PUBLIC`) ; manifeste de solveur enregistré. Correctif M8 : migration 0010.

## Résultats (pilote)

- 15 variantes, toutes faisables (aucune violation de droits sur aucun ω).
- **Front (rang 1)** : 8 variantes. On y trouve :
  - les 3 baselines (J_T = 0) ;
  - les unions (k = 1, deux familles) ;
  - les bipartitions k-means, k-means amorcée et spectrale.
- Louvain (S^scale 0,48–0,61) est dominé : rangs 4 à 6.
- **Conclusion** : TERRITORIAL_OPTIONS_DOMINATE_STATUS_QUO_EXCEPT_TRANSITION. **L'union** fait au moins aussi bien que le statu quo sur chaque objectif hors transition.
  - C'est un artefact attendu du vecteur d'objectifs : aucun coût d'hétérogénéité des préférences, J_R inconnu, institutions non recomposées.
  - Le rapport le dit, et le statut reste NOT_IDENTIFIABLE.
- **Gate O : PASSED.**
  - k-means : il atteint l'optimum exact, mais 1 départ sur 5 s'en écarte de 3,1 %, ce qui justifie le multi-départ.
  - Coupe spectrale : écart de 2,9 %.

## Challenge

Quatre défauts traités (ADR-0022) :
- benchmark mal posé, dont le front était fait de micro-territoires ;
- biais d'union, déclaré ;
- ρ lu comme une probabilité ;
- identifiant de candidat sans le run.

## Manquant

- Coûts d'hétérogénéité des préférences, et J_R faute de données de risque.
- Composition institutionnelle par candidat : le composeur M9 n'est appliqué qu'au statu quo.
- S^time et S^parameter, donc S_publish.
- Coût de transition dynamique G0 → … → GT (02 §26) : seul le coût statique J_T existe.
- Benchmark exact au-delà de 2 États.

## Tests

- **Unitaires** :
  - ρ, ε-dominance (résolution, objectifs inconnus), tri, certificat sans relaxation ;
  - coupe nulle pour une union, transition invariante aux étiquettes ;
  - aucun coût du nombre d'États sans coûts réels ;
  - ε impossible à déclarer pour J_R ;
  - benchmark exact et Goodhart micro-territoires.
- **Red-team** : aucun `best_solution` ni pénalité au nombre d'États ; J_R jamais 0 ; une violation exclut sans pondérer.
- **Intégration** :
  - statu quo au front, J_R UNKNOWN, Gate O, archive non publiable, front multiple ;
  - base : 15 solutions, toutes NOT_IDENTIFIABLE.

## Benchmarks

Évaluation : environ 8 s par maillage grille ou H3 r5, et 25 s sur H3 r6. Archive et benchmark exact : moins d'une seconde.

## Prochain milestone

M11 — validation et red-team : multi-échelle, ablation, Goodhart, confidentialité. On y traitera aussi les biais déclarés en M10 (après revue).
