# ADR-0019 — Bibliothèque causale et gel (M7)

*Statut : accepté — 2026-10-20.*

## Contexte
Sources dans la spec :
- prompt §31–33 : la structure minimale de la bibliothèque, le gel causal, et la règle « unknown means unknown » ;
- 04 en entier : hiérarchie d'identification I1–I7, DiD, RD, contrôle synthétique, transportabilité, identification partielle, politique nouvelle, décomposition de la souveraineté, validation ;
- 05 §8 et §20 (Gate C), 10 §14 (schéma), 11 A5 (aucune affirmation causale sans grade).

## Décision

**Enregistrement.** Un `CausalEffect` reprend les champs de 04 §12 et 10 §14. Il est immuable et identifié par son contenu.
- Le grade ne dépasse jamais le plafond de son design (DiD : I3 au mieux).
- I1–I4 exigent que tous les diagnostics du design soient PASSED. Un diagnostic FAILED est conservé, mais l'effet devient inadmissible.
- I6 et I7 ne portent que des bornes, jamais une loi.

**Admissibilité** pour un contexte cible :

| statut | conditions |
|---|---|
| `CAUSAL_FACT` | I1–I5, transport IDENTIFIED, recouvrement ≥ τ_O |
| `BOUNDED` | I6, ou transport PARTIAL (bornes élargies) |
| `EXPLORATORY_ONLY` | I7 |
| `UNSUPPORTED` | tout autre cas, et la réponse vaut `CAUSAL_EFFECT_UNKNOWN` |

Quelle que soit la combinaison, un I7 n'est jamais un fait causal ; une propriété hypothesis le vérifie.

**Transport.** τ_T ≠ τ_S par défaut. Une requête vers un contexte non évalué répond `CAUSAL_EFFECT_UNKNOWN`.
- Le recouvrement est la part des unités cibles dont chaque modificateur d'effet tombe dans le support source (quantiles 5–95 %).
- Un modificateur absent de la cible donne un recouvrement de 0 : on ne le suppose jamais identique.
- Seule la densité est calculable à ce stade ; tout autre modificateur est refusé.

**Politique nouvelle (04 §14).** On mesure la distance relative d_A au support des intensités. Les bornes sont élargies d'un facteur (1 + κ·d_A), et au-delà de `max_distance` la réponse vaut UNKNOWN.

**Traitements.**
- « autonomy » et « federalism » ne sont pas des composantes : ce sont des bundles de compétences, refusés comme traitements (02 §7). C'est ce qui tranche la tension avec la liste de 04 §2.
- La souveraineté est un bundle obligatoirement décomposé, avec résidu τ_S^res (04 §15).

**DiD échelonné.** ATT(g,t) avec des témoins jamais traités et une base universelle g − 1. L'ATT est agrégé par taille de cohorte, et l'incertitude vient d'un bootstrap par grappes stratifié par cohorte. Diagnostics :
- tendances pré-traitement : test de Wald, covariance bootstrap ;
- anticipation ;
- composition : panel équilibré ;
- spillovers : pente du changement des témoins sur l'exposition E_i = Σ W_ij A_j ;
- adoption endogène : tendances pré-traitement et placebo.

Robustesse : placebo, contrôle négatif, région exclue, et vérité synthétique pour les sources synthétiques.

**Gel.** Ordre : `measurement_freeze` → `causal_estimate:*` → `causal_validate` → `causal_freeze` → D/F/I, viabilité.
- `FrozenCausalLibrary` vérifie l'empreinte au chargement, n'expose que des requêtes, et ses enregistrements sont des modèles gelés.
- Base : tables `causal_effects` et `causal_freezes`, plus `run_manifests.causal_library_hash`. Des contraintes CHECK interdisent une loi pour I6/I7, et un design `expert_hypothesis` hors I7.

**Plus aucun coefficient en dur.**
- Les bornes I7 de M5 (saillance) et de M6 (accès au marché, infrastructures) deviennent des effets déclarés de la bibliothèque.
- Les manifestes D/F/I et viabilité ne portent que des clés, et une clé absente est refusée à la soumission.
- Un effet inconnu rend la viabilité UNKNOWN, jamais nulle.

**Gate C (05 §20).** Elle passe si chaque effet admis réussit chaque test de robustesse exécuté.

## Ce que le challenge a cassé
| problème | correction |
|---|---|
| Spillovers « témoins voisins vs éloignés » non testables sur une grille où tout témoin touche un traité : l'I3 était refusé | exposition continue E_i (04 §4) ; pente testée ; contagion injectée détectée (test) |
| Couverture de la vérité jugée sur les bornes élargies par le transport : l'estimation biaisée (adoption endogène) paraissait « couverte » | couverture jugée sur l'estimation brute ; l'endogène est non couvert **et** rejeté |
| Bornes I7 dupliquées dans les manifestes D/F/I et viabilité, hors de toute bibliothèque | effets déclarés uniques, référencés par clé |

## Conséquences
- Le pilote contient 3 effets I7, 1 effet I3 admis mais BOUNDED (recouvrement 0,75) et 1 effet I3 rejeté. Gate C : PASSED.
- La décomposition S2A (M6) attend toujours une réponse de mobilité volontaire identifiée : aucune n'est déclarée, donc `CAUSAL_EFFECT_UNKNOWN`.
- Restent non implémentés :
  - les estimateurs RD et contrôle synthétique, dont les diagnostics sont déclarés et exigés ;
  - la rétroaction des infrastructures (04 §17) ;
  - le SCM historique de Map-C-Deep.
