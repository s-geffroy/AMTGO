# ADR-0012 — File de runs reprenable dans le worker

*Statut : accepté — 2026-10-20.*

## Contexte
AMTGO est un pipeline batch ; la plateforme impose un worker en boucle,
reprenable, qui honore SIGTERM sous 30 s.

## Décision
- `amtgo run submit` gèle une requête en **RunManifest** (contenu résolu,
  empreinte, `run_id` dérivé du contenu) dans `/state/runs/<run_id>/`.
- Chaque cycle du worker exécute **une** étape du plus ancien run non terminé ;
  l'état est écrit atomiquement (fichier temporaire, fsync, rename). Une étape
  n'est `done` qu'après écriture de ses sorties ; ses écritures sont idempotentes.
- SIGTERM pendant une étape : `StageInterrupted`, étape rejouée, sans compter
  comme échec.
- Erreur AMTGO (licence, privacy, topologie…) : déterministe → FAILED
  immédiatement, message conservé. Autre exception : transitoire → réessai,
  FAILED après `max_stage_attempts`.
- `amtgo run execute` exécute le même code de façon synchrone (CI, Pages).

## Conséquences
Les artefacts fichiers sont la trace complète d'un run ; PostGIS en est le
registre interrogeable (upserts sur identifiants stables).
