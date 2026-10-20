# M3 — Cœur de mesure

## Fait

- **Interface de vraisemblance** : `LikelihoodSpec` déclarée par source dans un `MeasurementManifest` versionné et figé dans le RunManifest. Deux modèles :
  - `ea_count_density` (zone d'énumération géomasquée, noyau de déplacement) ;
  - `area_total` (total de polygone).
- **Sélection explicite**. Chaque exclusion est comptée avec sa raison :
  - vraisemblance absente ;
  - rôle non déclaré ;
  - porte de qualité (dimension par dimension) ;
  - **hors période** (aucune harmonisation temporelle implicite) ;
  - hors domaine.
- **Fusion** ([ADR-0013](../decisions/ADR-0013-modele-de-mesure.md)) : structure relative par prior log-normal, Gauss-Newton avec recherche linéaire, Laplace et tirages de Matheron ; totaux administratifs en marges recalées exactement. Le linéaire-gaussien exact est conservé comme référence.
- **Champs latents** : moyenne, écart-type, intervalle, ratio d'information, classe de calculabilité par cellule ; 200 tirages conservés (corrélations a posteriori) ; statut **MODEL** ; classe d'accès la plus restrictive des sources.
- **Validation** (05 §4) : holdout prédictif déterministe, ablation de sources, désaccord inter-sources, calibration contre la vérité (synthétique uniquement), comparaison entre maillages sur une grille de 100 km indépendante des marges, ratio d'information selon l'échelle.
- **Gel de mesure** (prompt §32) : `measurement_freeze.json`, enregistrement de provenance, `run_manifests.measurement_hash`.
- **Persistance** : `latent_fields` et `latent_field_cells` (migration 0005, `CHECK evidence_status = 'M'`).
- **Monde synthétique à vérité connue** ([ADR-0014](../decisions/ADR-0014-monde-synthetique.md)).
- Rapport : section mesure et **registre épistémique** WE KNOW / INFER / ASSUME / DO NOT KNOW (prompt §96).

## Résultats du pilote (vérité : 7,005 M habitants)

| contrôle | résultat |
|---|---|
| total vrai couvert par l'intervalle à 90 % | oui, sur les 4 maillages (erreur 0,4 %) |
| couverture des cellules | 92–94 % |
| holdout prédictif | 91–100 % |
| écart maximal entre maillages (grille 100 km) | z ≤ 1,8 |
| convergence | 4/4 |
| calculabilité, maille cellule | **D** (non identifiée) |
| calculabilité, 100 km | **A/B** |

## Challenge

Quatre versions successives du modèle ont été cassées par la validation avant d'aboutir à l'estimateur retenu ; le détail est dans ADR-0013. Le profilage a par ailleurs révélé une sursouscription des threads BLAS (×200), corrigée ([ADR-0015](../decisions/ADR-0015-ressources-calcul.md)).

## Manquant

- Corrélation spatiale a priori : une cellule sans observation garde son prior.
- Modèle de sélection / missingness non aléatoire (03 §26) : hypothèse MAR déclarée.
- Harmonisation temporelle : exclusion stricte hors période.
- Invariance de mesure entre enquêtes (03 §28) : sans objet sur une seule enquête synthétique.
- Raffinement adaptatif (07 §7) : reporté. Il produirait des maillages à résolutions mêlées, sans besoin démontré.
- Sources réelles de population : à brancher avec revue de licence et de privacy.

## Tests

Exactitude du linéaire-gaussien contre la postérieure dense ; moments de Matheron ; prior conservé sans observation ; positivité et convergence du log-normal ; recalage exact et marges chevauchantes refusées ; conservation des supports ; comptage des exclusions ; holdout déterministe ; règles du manifeste ; classes de calculabilité. Red-team : vérité inaccessible au réel, mondes mêlés refusés, Natural Earth interdit de mesure de population, rôle de mesure obligatoire, statut MODEL. Intégration : propriétés du pilote, persistance PostGIS.

## Benchmarks

Pilote complet (19 étapes, 4 maillages jusqu'à 4 777 cellules, validation comprise) : 16,8 s.

## Dette technique

- La fonction de vérité par quadrature est O(points × bourgs) ; suffisante pour le pilote.
- `representativeness_cv = 1` est conservateur (holdout jusqu'à 100 %) ; à calibrer par sensibilité.

## Prochain milestone

M4 — ontologies concurrentes (après revue).
