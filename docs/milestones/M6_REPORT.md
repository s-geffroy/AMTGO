# M6 — Scénarios, régimes, viabilité contextuelle

## Fait

- **Régimes typés** ([ADR-0018](../decisions/ADR-0018-scenarios-regimes-viabilite.md)).
  - Mobilité, transferts, défense, marché, ressources et infrastructures communes ont chacun un modèle typé.
  - Les dimensions E, M, R, S de la frontière entre États dérivent des règles.
  - Migration 0007 : tables `constitutional_regimes` et `scenarios`.
- **Scénarios** S1, S1 de stress, S2A et S2C, sur sept axes à intervalles déclarés.
  - Le climat suit au moins deux trajectoires, sinon il est marqué « non modélisé ».
  - Garde-fous de déplacement vérifiés au chargement, à la soumission, à l'exécution et en base.
  - Nouvelle commande `amtgo scenario validate`.
- **S2A** : décomposition exacte direct / composition / spillover. La réponse volontaire reste `CAUSAL_EFFECT_UNKNOWN` jusqu'à M7.
- **S2C** : `CoercionDependencyDiagnostic` (quatre champs, agrégats par juridiction).
  - Aucune origine, destination, route ni calendrier.
  - Sur le statu quo : NOT_APPLICABLE.
- **Viabilité** : `compute_viability(territory, regime, scenario, context)`.
  - La couverture du panier de services intègre les transferts neutres, l'accès au marché, les surcoûts fixes de souveraineté, la défense mutualisée et les infrastructures communes.
  - Les seuils sont normatifs ; aucun seuil de taille n'est accepté.
- **Monde synthétique** : nouvel instrument « comptes fiscaux », avec recettes et coût des services par district et une vérité analytique.
- **Monde V** : quatre propriétés de viabilité, vérifiées à chaque build et publiées avec les mondes A–F.
- **Pilote** : viabilité des deux États fictifs sous R0–R3 × trois scénarios × quatre maillages. S^scale de la viabilité et sensibilité au régime sont calculées, et S2C est rapporté.

## Résultats

### Monde V

| propriété | valeurs |
|---|---|
| un même petit territoire, non viable sous R0, est viable sous R3 | couverture 0,90 → 1,24 |
| aucun seuil de taille : sous R0, un petit territoire est viable et un grand ne l'est pas | small_dense VIABLE, large_sparse NOT_VIABLE |
| au régime d'observation, les coefficients exploratoires n'ont aucun effet | 0 dépendance |
| une viabilité n'a pas de valeur de vérité hors contexte | `bool()` lève |

### Pilote (statu quo, deux États fictifs)

- `s1_baseline` et `s2a_voluntary` : les deux États sont VIABLE sous chacun des quatre régimes (couverture 1,26–1,55).
- `s1_stress` : la viabilité **dépend du régime**.
  - `state_e` : NOT_VIABLE sous R0, UNCERTAIN sous R1–R3.
  - `state_w` : UNCERTAIN sous R0–R1, VIABLE sous R3.
  - Sous R2, le statut de `state_w` dépend du maillage.
- 6 statuts changent entre les bornes des coefficients exploratoires. Ils sont signalés et ne valent pas conclusion.
- S^scale (viabilité) = 0,97.
- Les transferts restent proches de 0 : les deux États ont des bases fiscales par habitant voisines.
- Garde-fous : déplacement forcé 0 et relocalisation induite 0 sur tous les scénarios. Réponse S2A : CAUSAL_EFFECT_UNKNOWN.

## Challenge

Quatre défauts ont été trouvés et corrigés (détail dans l'ADR-0018) :

- incohérence possible entre les gabarits de frontière et les règles du régime ;
- comptes fiscaux supposés neutres vis-à-vis du régime ;
- retour de l'autarcie par le biais des surcoûts fixes ;
- diagnostic S2C indéfini sur le statu quo.

## Manquant

- **Réponse de mobilité volontaire et effets de l'accès au marché et des infrastructures** : bornes exploratoires I7 seulement, en attendant la bibliothèque causale (M7).
- **Valeur de souveraineté MV_S(k, R)** : composeur institutionnel (M9).
- **D/F/I sous scénario** : sous une croissance uniforme (S1), elles sont invariantes, ce qui est vérifié. Des scénarios non uniformes exigent des données spatialisées.
- **Diagnostic S2C sur des candidats** : M8–M10.

## Tests

- **Unitaires** :
  - garde-fous (déplacement forcé, relocalisation induite, réponse hors S2A) ;
  - climat unique refusé ;
  - tirages reproductibles ;
  - projection S1 sans déplacement, S2C sans projection ;
  - invariance de D/F/I sous croissance uniforme ;
  - décomposition exacte, et réponse inconnue ≠ 0 ;
  - cas connu du diagnostic S2C, conservation des groupes, sortie agrégée seulement ;
  - frontière dérivée, monotonie R0 → R3 ;
  - transferts neutres (hypothesis) ;
  - viabilité UNKNOWN sans comptes, `bool()` qui lève, S2C sans viabilité, seuil de taille refusé.
- **Red-team** :
  - aucune fonction `is_viable`, ni de maximisation d'homogénéité, ni de planification de déplacement ;
  - aucun nom origine/destination dans le module S2C ;
  - scénario à déplacement forcé refusé à la soumission ;
  - viabilité sans scénario S1/S2A refusée ;
  - rôle fiscal non déclaré refusé ;
  - scénario dupliqué refusé.
- **Intégration** :
  - propriétés du pilote ;
  - base : quatre régimes et quatre scénarios enregistrés, et contrainte CHECK contre le déplacement forcé.

## Benchmarks

Pilote complet (38 étapes) : environ 40 s, dont la viabilité (quatre maillages × trois scénarios × quatre régimes), qui prend moins de 2 s.

## Dette technique

- La viabilité agrège au niveau des États seulement. Les niveaux infra-étatiques attendent le composeur (M9).
- Les axes de scénario sont uniformes sur la région, faute de données spatialisées de croissance.

## Prochain milestone

M7 — bibliothèque causale et `causal_freeze` (après revue).
