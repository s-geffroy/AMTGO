# ADR-0006 — Domination : composantes conservées

*Statut : accepté — 2026-10-20.*

## Contexte
$D = \max(D^{pot}, D^{real})$ (02 §9) mélange une *capacité* de domination
($A \times X \times (1-C)$) et une domination *observée* ($q^{inst} D^{obs}$),
d'échelles et de statuts de preuve différents.

## Décision (M5)
`DominationEstimate` stocke $D^{pot}$ et $D^{real}$ séparément, chacun avec son
incertitude et son statut de preuve ; $\max$ n'est qu'une vue dérivée. La
contrainte de droits s'applique **à chaque composante**. Le statut de la vue
dérivée est le plus faible des deux.

## Conséquences
On ne peut pas « compenser » une domination observée faible par une capacité
faible, ni l'inverse.
