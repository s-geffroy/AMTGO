# ADR-0016 — Ontologies concurrentes et mesure de composition (M4)

*Statut : accepté — 2026-10-20.*

## Contexte
Prompt §17 : pas de table `ethnicity` canonique ; ontologies, concepts et
crosswalks probabilistes P(g_b | g_a) ; une même analyse sous plusieurs
ontologies. §21 : identités ethnoculturelle, nationale et territoriale
séparées, sans mapping automatique. §20 : profil fonctionnel des langues.
03 §9 : pas de fusion autoritaire de classifications historiques concurrentes.

## Décision
- **Modèle** : `Ontology` (une dimension, un type, un statut de preuve,
  contexte obligatoire si historique), `OntologyConcept` (hiérarchie
  acyclique), `OntologyCrosswalk` (lignes P(· | a) sommant à 1, masse
  `__unmapped__` explicite, jamais DIRECT, jamais entre dimensions).
- **Incertitude des crosswalks** : chaque ligne est tirée d'une Dirichlet de
  concentration déclarée (force de la preuve) ; la masse non attribuée est
  conservée et rapportée.
- **Composition** : parts seulement, Dirichlet-multinomial à deux niveaux
  (région de 100 km, cellule), taille d'échantillon effective réduite (κ),
  **poids de plan** des réponses. Comptes de groupe = parts × population gelée
  (indépendance déclarée).
- **Ensemble** : chaque ontologie du run est évaluée ; S^ontology (provisoire,
  M4) = corrélation de rang, entre ontologies, du motif de diversité à 100 km
  (nombre effectif de catégories, quantité *descriptive* — la diversité n'est
  jamais pénalisée). À partir de M5, S^ontology portera sur D/F/I.
- **Source historique** : utilisée seulement pour mesurer sa compression
  (part de population couverte par son étiquette unique), jamais comme vérité
  ni comme entrée de la composition (rôle interdit).
- **Vie privée de groupe** : champs de composition au minimum CONTROLLED,
  artefacts non exportés, base limitée au registre des ontologies ; rapports
  limités aux agrégats de domaine (et seulement pour un monde synthétique) et
  aux mesures entre ontologies.

## Ce que le challenge a cassé
| problème | correction |
|---|---|
| calibration des parts à 100 km : 61–87 % pour 90 % (sur-confiance) | EA tirées en surface, vérité par habitant : **poids de plan** → 87–96 % |
| identifiants d'ontologie lisibles vs colonne UUID du schéma 10 | migration 0006 (texte) et registre des ontologies |
| une erreur SQL recopiait toutes les valeurs liées (comptes d'identité) dans les logs et l'état | `safe_error` : erreur d'origine sans paramètres, tronquée ; test de régression |

## Conséquences
- Aucune fonction du paquet ne renvoie l'étiquette d'une zone (test red-team
  par introspection : dominant, majority, main_language, ethnic_label…).
- Les identités endogènes (§18) restent à M5 : M4 ne fournit que des parts
  statiques, ce que le registre épistémique déclare.
