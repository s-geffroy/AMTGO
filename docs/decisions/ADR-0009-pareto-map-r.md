# ADR-0009 — Pareto à neuf objectifs et lecture de Map-R

*Statut : accepté — 2026-10-20.*

## Contexte
Avec 9 objectifs (02 §17), presque toute solution est non dominée : un Pareto
brut ne discrimine rien. 02 §20 écrit Map-R comme un `argmin`, alors que le
prompt §41 interdit de ne renvoyer que `best_solution`.

## Décision (M10)
- `ParetoArchive` avec **ε-dominance** (ε par objectif, dans le manifeste
  normatif) et taille d'archive bornée ; le schéma `solutions` le prévoit
  (`pareto_rank`, `metrics`, `stability`).
- Map-R = Pareto sur $\mathbf J + C_{transition}(G, G_0)$, jamais un argmin.
- Les baselines STATUS_QUO, NO_TERRITORIAL_CHANGE, INSTITUTIONAL_ONLY_REFORM
  sont toujours dans l'archive.
