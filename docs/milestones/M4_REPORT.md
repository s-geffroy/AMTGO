# M4 — Ontologies

## Fait

- **Modèle d'ontologie** ([ADR-0016](../decisions/ADR-0016-ontologies-composition.md)) :
  - `Ontology` porte une dimension, un type et un statut de preuve ; une ontologie historique a obligatoirement le statut H et un contexte ;
  - la hiérarchie de concepts est acyclique ;
  - le concept `__unmapped__` est réservé ;
  - le profil fonctionnel des langues est typé (§20).
- **Crosswalks probabilistes** :
  - chaque ligne somme à 1 ;
  - la masse non attribuée est explicite et conservée par composition ;
  - l'incertitude est de Dirichlet ;
  - aucun crosswalk n'est DIRECT ni ne franchit une dimension (§21).
- **Mesure de composition** :
  - Dirichlet-multinomial à deux niveaux, poids de plan, taille d'échantillon effective ;
  - parts seulement, statut MODEL, classe CONTROLLED au minimum.
- **Exécution en ensemble** sous chaque ontologie du run ; projection par crosswalk tirage par tirage ; S^ontology ; mesure de la compression d'une carte historique.
- **Monde synthétique** : couche identitaire fictive (α, β, γ, δ), réponses d'auto-identification, carte historique à étiquette unique (statut H).
- **Persistance** : registre des ontologies, concepts et crosswalks (migration 0006). Aucune table « ethnicity ». Les champs de composition restent dans les artefacts CONTROLLED.
- **Sécurité des logs** : `safe_error`, qui supprime les paramètres SQL liés.

## Résultats du pilote

| contrôle | résultat |
|---|---|
| calibration des parts à 100 km | 87–96 % pour 90 % |
| erreur absolue moyenne des parts (100 km) | 0,044–0,051 |
| S^ontology (catégories propres vs classification externe) | 0,76–0,79 ; min **0,76** |
| part de population couverte par l'étiquette historique de son bloc | ≈ 50 % (min 34 %) |

Lecture : le motif spatial de la diversité **dépend de l'ontologie** (S^ontology < 1), et c'est désormais marqué dans le rapport. Une carte historique à étiquette unique laisse en moyenne la moitié de la population de chaque bloc hors de son étiquette.

## Challenge

Sur-confiance de la composition corrigée par les poids de plan ; colonne d'identifiant d'ontologie ; fuite de valeurs liées dans les logs (corrigée, test de régression). Détail dans ADR-0016.

## Manquant

- Identités endogènes (§18) et risque de réification (§19) : M5.
- Identités nationale et territoriale : le modèle les sépare, mais aucune source synthétique ne les produit encore.
- Corrélation spatiale de la composition au-delà de la mise en commun régionale.
- Crosswalks réels : ils exigent une documentation de preuve (registre 12).

## Tests

- Validité des ontologies : contexte historique, cycles, réservé `__unmapped__`.
- Crosswalks : sommes, jamais DIRECT, refus inter-dimensions, couverture des concepts, matrices stochastiques centrées, composition qui conserve `__unmapped__`.
- Composition : information là où sont les réponses, catégories étrangères refusées, poids de plan exigés, projection et agrégation.
- Red-team : aucune API d'étiquetage, carte historique interdite en entrée de composition, composition sans population refusée, rôle obligatoire, champs CONTROLLED absents de la carte publique, erreurs sans paramètres liés.
- Intégration : propriétés du pilote.

## Benchmarks

Pilote complet (25 étapes, dont 4 compositions × 2 ontologies) : ~22 s. Suite de tests : 103 s.

## Dette technique

- S^ontology repose à ce stade sur une quantité descriptive ; à redéfinir sur D/F/I en M5.
- Les tirages de composition sont stockés en float16 compressé : suffisant pour des parts, à revoir si la précision devient critique.

## Prochain milestone

M5 — D/F/I sur données synthétiques (après revue).
