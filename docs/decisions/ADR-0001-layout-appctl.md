# ADR-0001 — Layout du dépôt et plateforme appctl

*Statut : accepté — 2026-10-20.*

## Contexte
Le prompt maître (§7) propose `docker-compose.yml`, `Makefile` et `src/amtgo/`. Le
VPS impose `compose.yaml` validé par appctl, un service `worker` reprenable et
l'interdiction de rien exécuter sur l'hôte.

## Options
1. Suivre le layout de la spec et contourner appctl : impossible (appctl refuse).
2. Garder la charpente appctl et y loger le paquet.

## Décision
Option 2. `compose.yaml` (et non `docker-compose.yml`), build context à la racine
(`dockerfile: src/Dockerfile`), paquet dans `src/amtgo/`, `src/worker.py` reste la
coque de la boucle. Un service `cli` (profil `cli`) exécute pytest et la CLI
`amtgo` : `sudo appctl run cli …`. Le `Makefile` enveloppe ces commandes.

## Conséquences
Les tests ne tournent jamais sur l'hôte. Le code est monté en lecture seule dans
`cli` par dessus l'installation éditable : pas de rebuild pour tester.
