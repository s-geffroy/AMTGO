# Architecture

## Pipeline

Le pipeline canonique (prompt §8) est découpé en étapes séparées en code. Les
étapes grisées n'existent pas encore ; aucune n'est simulée.

```text
SOURCE REGISTRY        amtgo.data.sources          M1  ✔
    ↓
INGESTION              amtgo.data.ingestion        M1  ✔  licence → fetch → sha256 → normalize → provenance
    ↓
NORMALIZATION          amtgo.data.observations     M1  ✔  valid time, support, qualité, statut de preuve
    ↓
(maillages)            amtgo.geo                   M2  ✔  h3 + grid_laea, transferts, distance de partitions
    ↓
MEASUREMENT MODELS     amtgo.measurement           M3  ✔  vraisemblances, log-normal + Laplace, marges, validation
ONTOLOGY ENSEMBLE      amtgo.ontology              M4  ✔  ontologies, crosswalks Dirichlet, composition, S^ontology
LATENT STATE FIELDS    amtgo.measurement.fields    M3  ✔  statut MODEL, tirages, calculabilité ; measurement_freeze
CAUSAL LIBRARY—FROZEN  amtgo.causal                M7
D/F/I                  amtgo.domination / fragmentation / integration   M5  ✔  statu quo, mondes A–F
CONSTITUTIONAL REGIME  amtgo.institutions.regimes  M0 (config) / M6
SCENARIO ENSEMBLE      amtgo.scenarios             M6
CANDIDATE GENERATION   amtgo.candidates            M8
INSTITUTIONAL COMP.    amtgo.institutions          M9
ROBUST OPTIMIZATION    amtgo.optimization          M10
PARETO ARCHIVE         amtgo.optimization          M10
VALIDATION             amtgo.validation           M11
PRIVACY / SAFETY GATE  amtgo.privacy.guard         M2 (minimal) / M11
EXPORT                 amtgo.export                M2 (carte publique)
```

## Exécution

```text
           sudo appctl run cli amtgo run submit configs/runs/<run>.yaml
                                   │
                                   ▼
   /state/runs/<run_id>/manifest.json   (RunManifest gelé, hashé)
   /state/runs/<run_id>/state.json      (étapes, tentatives, erreurs)
                                   │
   worker : cycle() ──► advance_one() ──► une étape ──► artefacts + état (atomique)
                                   │                         │
                                   ▼                         ▼
                           PostGIS (registre)        report.md, outputs.json
```

Services (`compose.yaml`) : `worker` (boucle), `db` (PostGIS dédiée, réseau
interne), `cli` (jetable : tests, CLI). Aucun service n'est exposé.

## Garde-fous structurels

| règle | où |
|---|---|
| pas de run sans régime ni manifeste normatif | `RunRequest` (champs obligatoires) |
| consentement jamais inféré, hard rights non relaxables, pas de pénalité au nombre d'États, accès par défaut non public | `NormativeManifest` (refus au chargement) |
| rôle d'une source vérifié avant toute récupération | `ingest_source`, `SourceManifest.require_role` |
| statut de preuve jamais promu | `EvidenceStatus.combine`, contrôle à l'ingestion |
| observation jamais moins protégée que sa source | contrôle à l'ingestion |
| point géomasqué = distribution | `Observation`, `geo.support` |
| aucune surface en degrés | `geo.crs` |
| export public = couches sans population ni groupe | `privacy.guard` |
| pas de `best_solution`, `ethnic_score`, `optimize_africa`… | test red-team d'introspection |
| pas d'étiquette de zone (dominant, majority, main_language…) ; parts seulement | `measurement.composition`, test red-team |
| aucun crosswalk entre dimensions (ethnoculturelle, nationale, territoriale…) | `OntologyCrosswalk.check_against` |
| champs de groupe au minimum CONTROLLED, jamais exportés | `composition_stages`, `privacy.guard` |
| aucune valeur de donnée dans les logs d'erreur | `runs.queue.safe_error` |
| fragmentation = liens coupés, jamais présence ; canal territorial seulement avec attachement | `fragmentation.engine`, test red-team |
| canal sans données = UNKNOWN, D_real non observé = UNKNOWN | moteurs D/F/I |
