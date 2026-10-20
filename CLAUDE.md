# Regles du projet amtgo

Ce fichier est lu par Claude Code au demarrage. Il fixe les regles non
negociables de ce projet sur ce VPS.

## Ce projet n'expose rien

C'est un worker : du travail de fond, aucune surface HTTP. Pas de labels
Traefik, pas de reseau edge, `exposure: none` dans `app.yaml` -- et appctl
refuse l'un sans l'autre.

Il n'y a donc pas d'URL a tester en fin de tache. Ce qui tient lieu
d'interface, ce sont **les logs** et **l'etat de sante** du conteneur.

Si le worker doit un jour repondre a quelque chose (une page de metriques, une
sonde), ca se declare : `sudo /opt/infra/scripts/app-exposure.py amtgo --set
worker=tailnet --port worker=<port>`, qui met `app.yaml` et les labels a jour
ensemble. Ne bricole jamais les labels a la main.

## La boucle

- `src/worker.py` porte la charpente : boucle, battement de coeur, arret
  propre. Le travail va dans `cycle()`. Garde le reste.
- **Un cycle qui echoue ne doit pas tuer le worker** : il rate son tour, journalise
  l'erreur, et reessaie au suivant. Ce qui ne doit jamais etre avale, c'est le
  message d'erreur.
- **Un cycle doit etre reprenable** : il peut etre interrompu a tout moment
  (redemarrage, SIGTERM, plantage). Ecris l'avancement au fur et a mesure dans
  `/state`, pas a la fin.
- **SIGTERM s'honore.** `docker stop` laisse `stop_grace_period` avant le
  SIGKILL. Le sommeil est fractionne pour ca : ne le remplace pas par un
  `time.sleep(INTERVAL)` d'un bloc.
- Le battement (`/tmp/heartbeat`) dit "la boucle tourne", pas "le travail
  reussit". Si le seuil du healthcheck change, il doit rester superieur a deux
  fois `WORKER_INTERVAL`.

## Logs

- Tout part sur la sortie standard, **non bufferise** (`flush=True`, et `-u`
  dans le Dockerfile). Sans ca, `appctl logs` ne montre rien pendant des
  minutes, et on croit le worker bloque.
- Une ligne par evenement, horodatee. Pas de secret, pas de donnee personnelle.
- Le volume de logs est une ressource : ne journalise pas a chaque iteration
  d'une boucle interne, journalise les cycles et les erreurs.

## Execution

- Tout runtime applicatif tourne dans Docker. Rien ne s'execute sur l'hote.
- N'installe aucun runtime applicatif sur l'hote.
- PostgreSQL, Redis et tout service de donnees sont DEDIES a cette application
  et declares dans ce `compose.yaml`. Il n'existe pas de base partagee sur ce
  VPS.
- Un worker qui consomme une file ou une base la declare ici, en
  `exposure: none`, sur le reseau `internal`.
- Utilise `appctl` pour toute operation Docker privilegiee. Tu n'as pas acces
  directement a la commande `docker`.
- Pour une tache periodique, garde la boucle : pas de cron dans le conteneur,
  pas de cron sur l'hote.

## Perimetre

- Travaille uniquement dans /srv/apps/amtgo.
- Ne touche jamais a /opt/infra.
- Ne tente jamais d'acceder aux autres applications du VPS.

## Interdictions (appctl les refuse)

- `privileged: true`
- `network_mode: host`, `pid: host`, `ipc: host`, `uts: host`
- `cap_add`, `devices`, `volumes_from`, `cgroup_parent`
- `security_opt` desactivant apparmor ou seccomp
- montage de /var/run/docker.sock
- bind mount hors de ce projet
- `build.context` hors de ce projet
- publication d'un port sur 0.0.0.0

## Secrets

- Aucun secret dans Git, dans le `.env` du projet, dans un prompt ou dans les
  logs. Une cle d'API de service tiers en est un.
- Les vrais secrets vivent dans /etc/app-secrets/amtgo/ (root uniquement) et
  sont injectes via Docker Compose Secrets, lus dans /run/secrets/....
- Le mode du fichier secret est reporte tel quel dans le conteneur : en `0400`
  root, un worker qui tourne en utilisateur non privilegie -- le cas ici -- lit
  `permission denied`. Poser `0444` sur le fichier ; sur l'hote, c'est le
  repertoire (0700 root) qui protege.

## Donnees

- Les donnees persistantes vont dans des named volumes, nommes `amtgo_<usage>`.
  Celui de depart s'appelle `amtgo_state` et est monte sur `/state`.
- Ne supprime jamais un volume sans demande explicite.
- N'execute jamais `docker volume prune`.

## Fin de tache

1. `tests/test_smoke.sh` et les tests pertinents ;
2. `sudo appctl validate` ;
3. `sudo appctl rebuild` si necessaire ;
4. `sudo appctl status` -- le conteneur doit finir `healthy` ;
5. `sudo appctl logs` -- verifier qu'un cycle passe reellement, pas seulement
   que le conteneur tourne ;
6. signaler tout echec restant sans le masquer.
