# ADR-0020 — Générateur de candidats territoriaux (M8)

*Statut : accepté — 2026-10-20.*

## Contexte
- **Prompt §38** : sept familles de candidats ; « le générateur ne doit pas imposer la réponse ».
- **Prompt §78** : baselines obligatoires.
- **07 §11** : ne pas laisser une heuristique définir l'univers des solutions.
- **11, phase 3** : le gate est la stabilité multi-échelle.
- **09 §15** : les bassins sont des « unités analytiques candidates », pas des propositions.
- **10 §7** : schéma de `territory_candidates`.

## Décision

### Baselines toujours présentes
STATUS_QUO, NO_TERRITORIAL_CHANGE et INSTITUTIONAL_ONLY_REFORM ont la même géométrie, celle du statu quo. Elles diffèrent par leur portée institutionnelle, que M9 composera. Sans elles, la génération échoue.

### Familles territoriales
Elles ne reposent que sur la population gelée et la géographie :
- **GEOGRAPHIC** : k-means pondéré par la population, multi-départ ;
- **GEOGRAPHIC_SEEDED** : k-means amorcé sur les centres du statu quo ;
- **GRAPH_SPECTRAL** : coupe normalisée du graphe des liens, avec le même noyau que D/F/I, mis en cache ;
- **GRAPH_COMMUNITY** : Louvain sur l'adjacence pondérée par liens × populations, avec balayage de résolution.

Le nombre d'États est **balayé** de 1 (union) à 4, jamais pénalisé : c'est une sortie (prompt §42).

### Aucune part de groupe
Les modules du générateur n'importent ni la composition ni l'état social. Un test red-team l'impose.

### Familles déclarées NOT_AVAILABLE, avec la raison
- **HISTORICAL** : exige une source au rôle `historical_boundary_seed`. La carte ethnographique synthétique ne déclare que `ontology_validation` ; son usage comme graine est refusé à la soumission.
- **LANGUAGE** : non implémentée. Elle exige une ontologie linguistique et une revue d'éthique (06), car un découpage par langue est un découpage identitaire.
- **MOBILITY** : aucun flux disponible.

### Invariants (§85)
- Chaque cellule a un État, et les étiquettes sont canoniques.
- **La contiguïté est réparée de façon déterministe** : une composante mineure rejoint le voisin avec lequel elle partage le plus d'arêtes.
- Une île du maillage n'est pas un défaut.
- Les doublons de géométrie entre familles sont signalés, pas dédupliqués silencieusement.

### Stabilité
- S^scale par variante vaut 1 − la distance TRANSFER maximale entre maillages, mesurée sur la grille de référence.
- La variante est stable si S^scale ≥ τ_scale du manifeste normatif.
- Stable veut dire nécessaire, jamais suffisant.

### Aucune publication
- Le statut de recommandation reste NOT_IDENTIFIABLE.
- La carte publique ne lit jamais les candidats (red-team).
- En base, `territory_candidates.active` vaut toujours faux.

## Ce que le challenge a cassé
| problème | correction |
|---|---|
| Un « nombre d'États optimal » choisi par le générateur (silhouette, coude) aurait imposé la réponse | balayage complet, aucune sélection ici |
| Louvain : le nombre de communautés dépend du maillage (6 à 44) — l'heuristique fabriquait de l'instabilité | rapportée telle quelle : variantes **instables** (S^scale 0,48–0,61), signalées |
| La carte historique synthétique, ethnographique, aurait pu servir de graine « historique » | rôle dédié `historical_boundary_seed`, refusé par son manifeste |

## Conséquences
- 15 variantes par maillage. 12 sont stables ; les 3 variantes Louvain ne le sont pas.
- M9 compose les institutions à géométrie fixe, sur les baselines d'abord (prompt §39 : recherche institutionnelle avant frontière).
- M10 évaluera et comparera les candidats.
