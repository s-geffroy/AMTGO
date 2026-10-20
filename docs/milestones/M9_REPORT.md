# M9 — Composeur institutionnel à géométrie fixe

## Fait

- **Composeur** ([ADR-0021](../decisions/ADR-0021-composeur-institutionnel.md)) :
  - 7 leviers à géométrie fixe, dans l'ordre de recherche du §39 ; confédération et souveraineté sont renvoyées à M10 ;
  - chaque levier est un changement de vecteurs primitifs (C, seuils, A, μ) ;
  - l'efficacité de chaque levier vient de la bibliothèque causale gelée, et chaque option est évaluée aux deux bornes.
- **Objectifs par option** :
  - violations et P(D > τ) maximal ;
  - F réseau et J_conn ;
  - institutionnalisation et risque de réification ;
  - C_inst ;
  - complexité effective.
- **Sorties** :
  - ensemble non dominé, statu quo inclus ;
  - conclusions NO_CHANGE / NO_TERRITORIAL_CHANGE_SUFFICIENT / INSTITUTIONAL_UNCERTAIN / INSTITUTIONAL_INSUFFICIENT_AT_FIXED_GEOMETRY.
- **Bibliothèque** : 5 efficacités I7 déclarées (droits, majorité qualifiée, langue, coopération transfrontalière, dévolution).
- **Pipeline** : `compose:<maillage>` puis `compose_ensemble`. La conclusion est retenue seulement si elle est identique sur chaque ontologie et chaque maillage. SIGTERM est honoré entre deux options.
- **Monde I** : cinq propriétés, vérifiées à chaque build et publiées avec A–F et V.

## Résultats

### Monde I

| propriété | résultat |
|---|---|
| violation au statu quo, levée par l'application des droits | NO_TERRITORIAL_CHANGE_SUFFICIENT (4 violations → 0) |
| effets quasi nuls | INSTITUTIONAL_INSUFFICIENT_AT_FIXED_GEOMETRY, aucune frontière proposée |
| aucune violation au statu quo | NO_CHANGE |
| overlay sans effet identifié | non évalué ; F inchangé (identifié : 0,116 → 0,086) |
| dévolution vers des districts alignés | RRI haut 0,009 contre 0 pour les droits |

### Pilote

- **NO_CHANGE**, stable sur les 4 maillages et les 2 ontologies : le statu quo fictif ne viole aucun droit.
- Tous les leviers sont NOT_NEEDED. La dévolution (fiscale → fédération) accroît le RRI haut jusqu'à 0,021.
- Non dominés : le statu quo et l'overlay, qui est équivalent au statu quo à la borne basse puisque μ = 0.

## Challenge

Quatre défauts corrigés (ADR-0021) :
- représentation par groupe, contraire à l'égalité civique ;
- overlay nominal ;
- statut trompeur quand il n'y a rien à résoudre ;
- dévolution présentée comme gratuite.

## Manquant

- Leviers combinés hors ordre de recherche (seuls les préfixes de l'ordre sont testés).
- Frontières vectorielles σ entre districts comme levier : seuls les overlays atténuent la charge frontalière.
- Test de nécessité de la souveraineté (§40) : il exige la recherche territoriale (M10).
- Registre `institutions` en base (10 §8) : il sera enregistré avec les solutions (M10).

## Tests

- **Unitaires** :
  - ordre de recherche imposé ;
  - effet causal obligatoire ;
  - application partielle des droits, sans effet de bord ;
  - dévolution qui préserve l'exclusivité ;
  - seuil qualifié ;
  - overlay jamais créé sans μ ni cellules ;
  - souveraineté refusée à géométrie fixe ;
  - propriétés du monde I.
- **Red-team** :
  - des effets inconnus ne résolvent jamais rien ;
  - la géométrie n'est jamais modifiée ;
  - coût et complexité rapportés ;
  - un effet inventé est refusé à la soumission.
- **Intégration** : conclusion NO_CHANGE stable, renvois à M10, statuts.

## Benchmarks

Composition sur H3 r6 (4 777 cellules, 13 options × 2 bornes × 2 ontologies) : environ 40 s. Pilote complet : environ 2 min 30.

## Prochain milestone

M10 — optimiseur régional : Pareto des candidats territoriaux composés contre les baselines, avec benchmark exact (après revue).
