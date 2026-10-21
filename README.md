# AMTGO — African Multilayer Territorial Geometry Optimization

Implémentation de la spécification **V1.0-RC1** : un laboratoire de géométries
constitutionnelles multi-couches. Ce n'est **pas** une carte ethnique ni un
générateur d'États. Le système compare des configurations institutionnelles sous
incertitude, et doit toujours pouvoir conclure *aucun changement territorial* ou
*non identifiable*.

Documentation publique : <https://s-geffroy.github.io/AMTGO/>, avec l'évaluation
d'implémentation, les ADR, les rapports de milestone, les rapports de runs
synthétiques et la carte.

État actuel : **M0–M13** (bootstrap, registre de sources, cœur spatial, mesure, ontologies,
D/F/I, scénarios et viabilité contextuelle, bibliothèque causale gelée, candidats analytiques,
composeur institutionnel, archive de Pareto robuste, validation et red-team avec gates de publication,
Map-R régional : trajectoires de transition depuis le statu quo, Map-C-Shallow : contre-factuel sans
privilège juridique de la géométrie actuelle).
Aucun découpage n'est produit à ce stade.

## Sur le VPS

Worker sans surface HTTP (`exposure: none`), hébergé par appctl. Services :

| service | rôle |
|---|---|
| `worker` | file de runs : chaque cycle exécute **une** étape du plus ancien run, avec écriture atomique dans `/state` |
| `db` | PostgreSQL/PostGIS **dédiée**, réseau interne, volume `amtgo_pgdata` |
| `cli` | conteneur jetable (`profil cli`) : tests et CLI `amtgo` ; rien ne tourne sur l'hôte |

```bash
make validate             # sudo appctl validate
make smoke                # le worker exécute un run synthétique, battement, arrêt propre
make test                 # pytest dans le conteneur cli (PostGIS compris)
make lint typecheck       # ruff, mypy strict
make rebuild status logs  # appctl rebuild / status / logs
make pilot                # soumet configs/runs/synthetic_pilot.yaml à la file du worker
make docs                 # construit le site (vérification locale)
```

Un worker n'a pas d'URL : **les logs sont l'interface** (une ligne JSON par
événement : `run.submitted`, `run.step`, `run.succeeded`…). Les rapports de run
sont dans `/state/runs/<run_id>/report.md`.

## Réglages

| variable | défaut | rôle |
|---|---|---|
| `WORKER_INTERVAL` | `30` | secondes entre deux cycles (le seuil du healthcheck, 180 s, doit rester > 2 × l'intervalle) |
| `AMTGO_STATE_DIR` | `/state` | volume `amtgo_state` : runs, cache des sources |
| `AMTGO_DB_HOST` | `db` | vide = base désactivée (artefacts fichiers seuls) |
| `AMTGO_DB_PASSWORD_FILE` | `/run/secrets/db_password` | secret Compose |

Les **paramètres normatifs** ne sont jamais dans l'environnement : ils vivent dans
`configs/normative/*.yaml` et sont figés dans chaque RunManifest.

## Secrets

`/etc/app-secrets/amtgo/db_password` (root, mode `0444`), injecté par Docker
Compose Secrets. Jamais dans le dépôt, le `.env` ou les logs.

## Spécification

Le corpus V1.0-RC1 est lu depuis `spec/` (local, **non versionné**, car le dépôt
est public). Ses empreintes sha256 figurent dans
`docs/IMPLEMENTATION_ASSESSMENT.md`.

## Licence

Double licence :

- **code** (`src/`, `tests/`, `scripts/`, `configs/`, workflows) : [Apache-2.0](LICENSE) ;
- **documentation, rapports et données dérivées publiées** (`docs/`, rapports de
  run, couches de la carte) : [CC BY 4.0](LICENSE-docs).

Natural Earth reste dans le domaine public. Voir [NOTICE](NOTICE).
