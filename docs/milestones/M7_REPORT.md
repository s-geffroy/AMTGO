# M7 — Bibliothèque causale et gel

## Fait

- **Enregistrements causaux** ([ADR-0019](../decisions/ADR-0019-bibliotheque-causale.md)) :
  - grades I1–I7 et plafond par design ;
  - diagnostics exigés par design ;
  - admissibilité : CAUSAL_FACT, BOUNDED, EXPLORATORY_ONLY ou UNSUPPORTED (→ `CAUSAL_EFFECT_UNKNOWN`).
- **Transport** :
  - recouvrement des modificateurs d'effet, statuts IDENTIFIED, PARTIAL ou UNSUPPORTED ;
  - un contexte non évalué donne UNKNOWN.
- **Politique nouvelle** : distance au support, bornes élargies, puis UNKNOWN au-delà du seuil.
- **Traitements** : souveraineté décomposée en bundle avec résidu ; « autonomy » et « federalism » refusés comme traitements primitifs.
- **DiD échelonné** : ATT(g,t), bootstrap par grappes. Diagnostics : tendances pré-traitement, anticipation, composition, spillovers par exposition, adoption endogène. Robustesse : placebo, contrôle négatif, région exclue.
- **Monde synthétique** : instrument `policy_panel` (36 districts × 15 ans, cohortes 2015 et 2018), avec adoption exogène ou endogène et effet vrai connu.
- **Pipeline** : `causal_estimate:*` → `causal_validate` (Gate C) → `causal_freeze`, placés après `measurement_freeze` et avant D/F/I et viabilité. La bibliothèque gelée est en lecture seule, avec empreinte vérifiée.
- **Plus de coefficients en dur** : saillance (M5), accès au marché et infrastructures (M6) sont maintenant des effets I7 déclarés, référencés par clé.
- **Base** : migration 0008 (`causal_effects`, `causal_freezes`, `causal_library_hash`), avec contraintes de doctrine.
- **CLI** : `amtgo causal validate` et `amtgo causal show <run>`.

## Résultats (pilote)

| effet | design | grade | transport (recouvrement) | statut |
|---|---|---|---|---|
| décentralisation fiscale fictive → couverture des services | DiD | I3 | PARTIAL (0,75) | **BOUNDED** [0,054 ; 0,090] |
| droits linguistiques fictifs (adoption endogène) | DiD | I3 | PARTIAL (0,88) | **rejeté** : tendances pré-traitement, adoption endogène, placebo |
| accès au marché → base fiscale | hypothèse d'expert | I7 | — | EXPLORATORY_ONLY [0 ; 0,3] |
| infrastructures communes → coût des services | hypothèse d'expert | I7 | — | EXPLORATORY_ONLY [0 ; 0,2] |
| institutionnalisation → saillance | hypothèse d'expert | I7 | — | EXPLORATORY_ONLY [0 ; 0,5] |

- **Effet exogène** :
  - ATT estimé 0,072, IC à 90 % [0,063 ; 0,081] avant élargissement ;
  - il couvre la vérité 0,071 ;
  - placebo, contrôle négatif et région exclue passent.
- **Effet endogène** : l'ATT estimé vaut 0,088, avec un intervalle qui **ne couvre pas** la vérité. Le biais est réel, et les diagnostics l'ont détecté avant tout usage.
- **Gate C : PASSED.**
- **Viabilité et D/F/I** : résultats identiques à M6, car ce sont les mêmes bornes, désormais lues dans la bibliothèque gelée.

## Challenge

Trois défauts trouvés et corrigés (ADR-0019) :
- spillovers non testables sur grille ;
- couverture de la vérité jugée sur des bornes élargies ;
- bornes I7 dupliquées hors de la bibliothèque.

## Manquant

- Estimateurs RD géographique et contrôle synthétique : leurs diagnostics sont déclarés et exigés, mais aucun estimateur n'est écrit.
- Réponse de mobilité volontaire (S2A) : aucune source, donc `CAUSAL_EFFECT_UNKNOWN`.
- Rétroaction des infrastructures (04 §17) ; holdout temporel et holdout de politique.
- Modificateurs d'effet autres que la densité.

## Tests

- **Unitaires** :
  - plafond de grade, diagnostics exigés, I7 limité aux bornes et jamais fait causal (hypothesis) ;
  - matrice d'admissibilité, refus d'autonomy et federalism, bundle de souveraineté et résidu ;
  - distance au support ; requêtes (contexte non évalué, hors support) ; altération détectée ; lecture seule ; tirages ;
  - DiD : effet exogène retrouvé, adoption endogène signalée et biaisée, spillovers injectés détectés, témoins requis ;
  - recouvrement et statuts de transport.
- **Red-team** :
  - effets référencés par clé, jamais par nombre ;
  - effet inventé ou bibliothèque absente refusés ;
  - rôle d'estimation exigé ;
  - effet déclaré I1 refusé ;
  - gel avant tout consommateur.
- **Intégration** :
  - Gate C, effet rejeté, couverture de la vérité, gel lié à `measurement_freeze`, effets consommés par la viabilité ;
  - base : 5 effets gelés, empreinte du run, contrainte CHECK contre une loi pour un I7.

## Benchmarks

Estimation, validation et gel : moins d'une seconde (2 panels × 200 tirages bootstrap).

## Prochain milestone

M8 — générateur de candidats, avec STATUS_QUO, NO_TERRITORIAL_CHANGE et INSTITUTIONAL_ONLY_REFORM comme baselines (après revue).
