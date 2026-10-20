# Lacunes d'implémentation

## Fichiers de spécification manquants

Aucun : les fichiers `00` à `14` listés au §1 du prompt maître sont présents.

## Variables reconnues non identifiables à maille continentale (03 §31)

Elles resteront `PROXY`, `MODEL` ou `UNKNOWN` selon les zones, et ne seront
jamais remplies par un coefficient inventé :

- intégration sociale fine ;
- mariages intergroupes à maille continentale ;
- préférence locale réelle pour l'autonomie ;
- mobilité pastorale complète ;
- représentation administrative détaillée ;
- régimes fonciers comparables ;
- fiscalité sous-nationale ;
- confiance intercommunautaire fine ;
- qualité du consentement.

## Écarts connus au périmètre M0–M2

| écart | raison | quand |
|---|---|---|
| raffinement **adaptatif** du maillage (07 §7) | maillages à résolutions mêlées ; pas de besoin démontré au pilote | après profilage |
| `compare_across_meshes` et $S_{scale}$ | exigent des partitions candidates ; la distance existe déjà | M8 |
| missingness non aléatoire (03 §26) | hypothèse MAR déclarée dans chaque rapport ; exige des covariables de sélection | M3+ |
| corrélation spatiale a priori | prior indépendant : une cellule sans observation garde son prior | M3+ |
| harmonisation temporelle | exclusion stricte hors période cible | M3+ |
| invariance de mesure entre enquêtes (03 §28) | une seule enquête (synthétique) | avec sources réelles |
| rasters (WorldPop, GHSL…) | rasterio différé (ADR-0002) | M3 |
| stockage objet S3/MinIO | les fichiers de run sous `/state` suffisent au prototype | après profilage |
| licence du projet | décision du porteur du projet | — |
| seuils normatifs du manifeste par défaut | provisoires, décision de gouvernance | — |
