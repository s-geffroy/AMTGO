# M0 — Bootstrap

## Fait

- Paquet `amtgo` (Python 3.12, `pyproject.toml`, `uv.lock` versionné) et arborescence du prompt §7, adaptée à appctl ([ADR-0001](../decisions/ADR-0001-layout-appctl.md)).
- Image `python:3.12-slim`, worker non-root, base **PostGIS dédiée** sur le réseau interne, service `cli` jetable pour les tests et la CLI ; rien ne s'exécute sur l'hôte.
- Configuration d'exécution (`pydantic-settings`) séparée des paramètres normatifs.
- Logs structurés : une ligne JSON par événement, liste blanche de champs, `flush`.
- Taxonomie d'erreurs du §71, plus `ProvenanceError`, `ForbiddenSourceRole` et `StageInterrupted`.
- Types transverses : `EvidenceStatus` (pas de promotion), `PrivacyClass` (défaut non public), `QualityVector` à 7 dimensions (aucun score scalaire), `UncertainValue` fondé sur des tirages ([ADR-0005](../decisions/ADR-0005-incertitude-echantillons.md)), `Entity`, `ProvenanceRecord`.
- `NormativeManifest`, qui refuse au chargement l'inférence de consentement, les hard rights relaxables, la pénalité au nombre d'États et l'accès public par défaut.
- Régimes R0–R3 pilotés par la configuration, avec alias ([ADR-0003](../decisions/ADR-0003-nomenclatures.md)).
- `RunManifest` gelé et hashé ; `run_id` dérivé du contenu ; pas de run sans régime ni manifeste normatif.
- Migrations Alembic versionnées (0001–0004) : énumérations, `CHECK` [0,1], SRID 4326, temps de validité.
- File de runs reprenable dans le worker ([ADR-0012](../decisions/ADR-0012-file-de-runs.md)).
- CI GitHub Actions (ruff, mypy strict, pytest avec PostGIS, smoke test) et publication Pages.

## Manquant

- Stockage objet S3/MinIO : les fichiers de run suffisent au prototype.
- Licence du projet : à décider par le porteur.

## Tests

Unitaires (cœur, manifestes), intégration (file : bout en bout, reprise après SIGTERM, idempotence, échec déterministe immédiat, échec transitoire réessayé, **reproductibilité**), base (migrations, persistance idempotente, contraintes).

## Décisions

ADR-0001, 0002, 0003, 0005, 0012.

## Dette technique

- `code_commit` vaut `unknown` dans les builds locaux (appctl ne passe pas d'argument de build). L'empreinte du code source (`+src.<hash>`) garantit la reproductibilité ; la CI injecte le vrai commit.
- mkdocs-material annonce des ruptures avec MkDocs 2.0 ; `mkdocs<2` est épinglé.

## Prochain milestone

M1.
