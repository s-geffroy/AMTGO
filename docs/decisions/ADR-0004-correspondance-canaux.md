# ADR-0004 — Correspondance canaux → dimensions de frontière d(c)

*Statut : accepté — 2026-10-20.*

## Contexte
02 §10 définit la charge frontalière $B^g_{ijc} = C^g_{ijc}\,\sigma^{d(c)}_{ij}(1-\mu^g_{ijc})$
mais ne définit jamais $d(c)$. Il y a 7 canaux de cohésion, 5 de
fragmentation, 7 d'intégration et 6 dimensions σ (P, C, E, M, R, S).

## Décision (M5, figée ici pour que M3–M4 n'en dépendent pas implicitement)
Une table **versionnée** dans `configs/`, proposée :

| canal | dimension σ |
|---|---|
| territorial | P (politique) |
| social, family | M (mobilité) |
| cultural, linguistic | C (culturelle) |
| economic | E (économique) |
| mobility | M (mobilité) |
| institutional, civic | P (politique) |
| identity | C (culturelle) |
| ressources (hyperarêtes) | R |
| sécurité | S |

La table est un paramètre de modèle, enregistré dans le RunManifest, et sa
sensibilité sera testée (05 §18).

## Conséquences
Aucun calcul de F ou de J_conn ne peut s'exécuter sans table déclarée.
