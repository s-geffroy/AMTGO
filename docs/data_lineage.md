# Lignée des données

Toute sortie analytique doit remonter jusqu'à ses sources (prompt §10) :

```text
solution → métrique → champ latent → observations → sources
```

À M2, la chaîne effectivement tracée est :

```text
manifest:<sha256 du SourceManifest>
   └─ ingest.fetch_validate ─► source:<uuid stable (source_id, release)>
          └─ ingest.normalize ─► observations:<sha256 du contenu>
                 └─ geo.create_base_mesh ─► mesh:<mesh_id>:<cells_hash>

observations:* + mesh:* + measurement:<sha256 du MeasurementManifest>
   └─ measurement.fuse ─► field:<field_id>            (statut MODEL)
          └─ measurement.freeze ─► measurement_freeze:<sha256>
```

Chaque `ProvenanceRecord` porte `input_ids`, `output_ids`, `code_version`,
`parameters`, `timestamp` et `run_id`. Son identifiant dépend du contenu, pas de
l'horloge : rejouer une étape ne crée pas de doublon.

## Reproductibilité

- `run_id` = UUID5 de l'empreinte du RunManifest (contenu résolu de toutes les
  configurations, plus la version du code).
- `outputs.json` → `outputs_hash` : empreinte des sorties scientifiques
  (observations, cellules, contrôles multi-échelles), **sans** horodatage
  d'enregistrement.
- Test d'intégration dédié : même manifeste, deux répertoires d'état ⇒ même
  `outputs_hash`.

## Temporalité

`valid_from` / `valid_until` (validité) et `recorded_at` (enregistrement) sont
distincts. Aucune agrégation temporelle n'existe encore ; quand elle existera
(M3), elle exigera un modèle temporel explicite (03 §29).
