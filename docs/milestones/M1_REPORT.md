# M1 — Registre de sources

## Fait

- `License`, `SourceManifest` (prompt §69, schéma 10 §1) et `Source`. Contrôles :
  - zones de données et redistribution cohérentes ;
  - rôles autorisés et interdits disjoints ;
  - ressources épinglées par sha256 ;
  - sources restreintes jamais récupérées par http ;
  - contexte obligatoire pour toute source historique (01 §29).
- `Observation` : temps de validité et temps d'enregistrement distincts, 8 types de support, point géomasqué traité comme une distribution (`UNCERTAIN_POINT` + `displacement_km`), géométries valides.
- Contrat `SourceAdapter` (`discover` / `fetch` / `validate` / `normalize`) ; le réseau n'est touché que dans `fetch`.
- Pipeline d'ingestion, dans cet ordre :
  1. **rôle et licence vérifiés avant toute récupération** ;
  2. checksum ;
  3. normalisation ;
  4. garde-fous par observation (pas de déclassement de sensibilité, pas de promotion de preuve) ;
  5. parquet et provenance.
- Adapters :
  - **Natural Earth** v5.1.2, domaine public, frontières *de facto* : rôle `basemap_display` autorisé, `legal_boundary_truth` interdit ;
  - **synthétique** déterministe, placé en plein Atlantique Sud.
- Persistance PostGIS (`licenses`, `sources`, `observations`), en upserts idempotents.

## Manquant

- Adapters de sources réelles de population, de langue ou d'identité : ils exigent les modèles de mesure (M3) et une revue privacy.
- Modèle de missingness (03 §26) : M3.

## Tests

Validation des manifestes, observations, red-team :
- rôle interdit refusé **sans aucun fetch** ;
- redistribution interdite ;
- déclassement de sensibilité ;
- promotion silencieuse de preuve ;
- checksum altéré ;
- lignée perdue ;
- empreinte indépendante de l'horloge ;
- points synthétiques dans l'emprise déclarée.

## Décisions

[ADR-0011](../decisions/ADR-0011-carte-publique.md) (Natural Earth comme Source).

## Challenge

Le générateur synthétique tirait ses grappes dans le rectangle LAEA formé par deux coins projetés. À 45° du centre de projection, ce rectangle est très tourné par rapport à l'emprise lon/lat, et des points tombaient hors emprise. Corrigé par un tirage avec rejet dans l'emprise projetée ; un test de régression a été ajouté.

## Prochain milestone

M2.
