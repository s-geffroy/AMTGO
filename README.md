# amtgo

Worker heberge sur le VPS multi-applications : du travail de fond, **aucune
surface HTTP**.

## Ou est le travail

`src/worker.py`, fonction `cycle()`. Tout le reste est la charpente :

| element | role |
|---|---|
| boucle | rappelle `cycle()` toutes les `WORKER_INTERVAL` secondes |
| battement | `/tmp/heartbeat`, touche a chaque tour, lu par le healthcheck |
| arret propre | SIGTERM honore, sommeil fractionne, fin du cycle en cours |
| `/state` | volume `amtgo_state`, ce qui doit survivre a un redemarrage |

## Cycle de developpement

```bash
sudo -iu amtgo
cd /srv/apps/amtgo
claude
```

Puis, apres modification :

```bash
tests/test_smoke.sh      # un cycle, un battement, un arret propre
sudo appctl validate
sudo appctl rebuild
sudo appctl status       # le conteneur doit passer 'healthy'
sudo appctl logs -f      # c'est ici qu'on voit si le travail se fait
```

Un worker n'a pas d'URL a ouvrir : **les logs sont l'interface**. `status` dit
que la boucle tourne, `logs` dit que le travail se fait. Les deux sont
necessaires.

## Reglages

| variable | defaut | role |
|---|---|---|
| `WORKER_INTERVAL` | `30` | secondes entre deux cycles |
| `WORKER_STATE` | `/state` | repertoire d'etat (volume persistant) |
| `WORKER_HEARTBEAT` | `/tmp/heartbeat` | fichier de battement |

Le seuil du healthcheck (180 s dans `compose.yaml`) doit rester superieur a
deux fois `WORKER_INTERVAL`.

## Exposition

`app.yaml` le declare en `none` : le conteneur ne parle qu'au reseau interne de
l'application. Pour ouvrir une page de metriques ou une sonde :

```bash
sudo /opt/infra/scripts/app-exposure.py amtgo --set worker=tailnet --port worker=9100
```

`app.yaml` et les labels Traefik sont mis a jour ensemble.

## Secrets

Les secrets reels vont dans `/etc/app-secrets/amtgo/` (root uniquement),
jamais dans ce depot :

```bash
printf '%s\n' "<la cle>" | sudo tee /etc/app-secrets/amtgo/api_key
sudo chmod 0444 /etc/app-secrets/amtgo/api_key   # lisible dans le conteneur
```

et dans `compose.yaml` :

```yaml
    secrets:
      - api_key
    environment:
      API_KEY_FILE: /run/secrets/api_key

secrets:
  api_key:
    file: /etc/app-secrets/amtgo/api_key
```

`0444` et non `0400` : le mode est reporte tel quel dans le conteneur, ou le
worker tourne en utilisateur non privilegie. Sur l'hote, c'est le repertoire
(0700 root) qui protege le secret.
