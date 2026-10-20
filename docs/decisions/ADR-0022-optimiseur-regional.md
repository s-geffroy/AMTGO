# ADR-0022 — Optimiseur régional : archive de Pareto robuste (M10)

*Statut : accepté — 2026-10-20.*

## Contexte
- **Prompt §41-48** : ParetoArchive obligatoire, sans pénalité au nombre d'États, avec certificat d'infaisabilité, robustesse, benchmark exact et multi-départ.
- **02 §15** (C_inst), **§17** (J), **§18** (ρ), **§19** (S_publish), **§33** (master problem).
- **05 §9** (solver validation), **05 §14** (Goodhart).
- **11** : Gate O (« exact benchmark + multi-start »).
- **ADR-0009** : ε-dominance, Map-R = Pareto + coût de transition, jamais un `argmin`.

## Décision

### Solutions
Une solution est une **variante de candidat** (famille, paramètres) de M8.
- Elle est évaluée sur chaque maillage et sous chaque ontologie : ω = maillage × ontologie.
- Elle reçoit le gabarit institutionnel du statu quo : États au niveau supérieur, districts découpés par les États au niveau local.

### Objectifs
J = [J_D, J_F, J_conn, J_V, J_G, J_R, J_T, J_inst, J_reif], tous à minimiser.
- **J_V** : pire P(couverture < τ_V) sur les États et les scénarios S1/S2A.
- **J_G** : liens fonctionnels coupés.
- **J_T** : part de la population qui change d'État, après le meilleur appariement des étiquettes.
- **J_inst** : coûts fixes réels par État, plus la part mutualisée payée une seule fois, plus la gestion des frontières proportionnelle à leur longueur. Sans coûts réels, le nombre d'États ne coûte rien (test).
- **J_R** : **UNKNOWN**, jamais 0.

### Robustesse et dominance
- ρ(J) = E_ω + λ_tail·CVaR_α + λ_var·Var_ω, avec les poids du manifeste normatif.
- **ε-dominance** avec une résolution par objectif : un écart plus petit que ε ne départage jamais. Un objectif inconnu est ignoré, jamais compté à 0.

### Contrainte de droits
Elle est **dure** : une violation sur un seul ω exclut la variante. Si aucune variante ne reste, le certificat d'infaisabilité donne :
- les contraintes liantes ;
- les ensembles de conflit minimaux ;
- les paramètres normatifs.

Aucune relaxation n'est appliquée.

### Archive
- Rangs de Pareto et front ; les baselines sont toujours présentes.
- Map-R : le statu quo, à J_T = 0, n'est jamais exclu par la transition.
- La conclusion distingue NO_TERRITORIAL_CHANGE, TERRITORIAL_OPTIONS_DOMINATE_STATUS_QUO_EXCEPT_TRANSITION et INFEASIBLE.
- Les **biais connus** sont toujours joints.

### Publication
S^time et S^parameter ne sont pas calculés. S_publish vaut donc UNKNOWN et la publication est bloquée : le statut reste NOT_IDENTIFIABLE, et la table `solutions` interdit `PUBLIC`.

### Gate O
Chaque heuristique est comparée à l'**optimum exact de son propre critère**, sur les 627 bipartitions contiguës d'une grille 4×4, avec 5 départs :
- k-means : inertie pondérée ;
- coupe spectrale : coupe normalisée.

## Ce que le challenge a cassé
| problème | correction |
|---|---|
| Premier benchmark sur la coupe des liens seule : le front exact n'est fait que de micro-territoires (1 cellule) et l'écart des heuristiques (58 %) ne mesurait rien | benchmark de chaque heuristique sur son propre critère ; le front « coupe seule » devient un test Goodhart (05 §14) |
| L'union (1 État) fait mieux que le statu quo partout sauf la transition : sans coût d'hétérogénéité des préférences, l'archive favorise mécaniquement les grandes unités | biais déclaré dans l'archive et le rapport ; à modéliser (M11+) avant toute lecture |
| ρ = E + CVaR lu comme une probabilité (valeurs > 1) | colonnes notées ρ(J), biais documenté |
| Identifiant de territoire candidat sans le run : un même candidat généré par un autre run n'était pas enregistré | migration 0010 (correctif M8) |

## Conséquences
- Pilote : 15 variantes, toutes faisables. 8 sont au front, dont les trois baselines. L'union domine le statu quo hors transition, sous les biais déclarés.
- Les communautés de Louvain, instables, sont dominées. Gate O : PASSED (k-means 0 %, spectral 2,9 %).
- M11 doit attaquer les biais : coûts d'hétérogénéité, recomposition institutionnelle par candidat, S^time et S^parameter, red-team Goodhart.
