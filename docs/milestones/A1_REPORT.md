# A1 — Benchmark du modèle spatial de population (Ghana)

*Statut : cible A1 de la [feuille de route révisée](../decisions/ADR-0029-elg-seg-gates-feuille-de-route.md). **Gate A1 non passé** selon sa règle déclarée avant le run : la sélection de variante est instable entre maillages. Le modèle en place (R2b) n'est **pas surconfiant** à l'échelle du district : il est prudent. Rien n'est publié.*

## Question
La revue de 2026-10-22 demandait de corriger une surconfiance à maille fine. Depuis la correction R2b, le constat régional était inverse : des intervalles trop larges. Avec 2 à 11 régions retenues, aucun modèle ne pouvait être départagé.

A1 pose donc d'abord une question de **validation** : le modèle prédit-il correctement des totaux **plus fins que ses marges**, qu'il n'a jamais vus ?

## Fait

### Validation sur les 261 districts du PHC 2021
- **Source** : `gha_census_2021_adm2`, les totaux de district du recensement, lus sur le StatsBank de GSS (API PxWeb) et joints aux 260 polygones COD-AB.
- **Écarts de découpage déclarés** dans le manifeste :
  - le tableau est plat : le pays, les 16 régions et 17 sous-métropoles sont retirés, sinon une métropole serait comptée deux fois avec ses sous-métropoles ;
  - Guan, détaché de Jasikan et sans polygone, est fusionné sur Jasikan ;
  - 22 alias d'orthographe.
- **Contrôle** : la somme des 260 unités égale le total national publié (30 832 019). Un contrôle `expected_total` le garantit à l'ingestion.
- **Licence** : le StatsBank n'affiche aucune condition de réutilisation, et aucune source ouverte des 261 districts n'existe. La redistribution n'est donc **pas supposée** :
  - la source est en zone `RESTRICTED_LOCAL` ;
  - le fichier est déposé sous `restricted/`, épinglé par sha256, avec sa requête d'origine consignée dans le manifeste ;
  - seuls des agrégats sortent.
- **Jamais une marge** : le schéma refuse qu'une source de benchmark soit aussi une vraisemblance du modèle, et le run exige le rôle `multiscale_validation`.

### Le benchmark (`benchmark:<maillage>`, puis `benchmark_summary`)
- **Ajustement** : chaque variante d'erreur du prior est ajustée sur les **mêmes 16 marges régionales**, puis ses tirages sont agrégés aux districts.
- **Bruit d'observation** : le bruit déclaré du total publié (2 %, provisoire) est ajouté aux tirages.
- **Scores, par district** :
  - couverture à 50, 80 et 95 % ;
  - CRPS (estimateur exact sur tirages), rapporté au total ;
  - score logarithmique sur l'échelle log ;
  - PIT et résidu standardisé log.
- **Strate MAUP** : les districts de moins de 4 cellules médianes sont rapportés à part.
- **Validation croisée spatiale** : les districts sont répartis en damier de blocs LAEA de 100 km. La variante préférée (score logarithmique le plus faible) sur une moitié est évaluée sur l'autre, et inversement. Une variante n'est jamais notée sur les districts qui l'ont fait retenir.
- **Reprise** : chaque variante est écrite dès qu'elle est notée, et une variante déjà notée n'est pas recalculée.
- **Coût** : 19 s pour quatre maillages et sept variantes.

### Variantes et gate, déclarés avant le run
| variante | erreur log du prior, en plus du centrage sur l'espérance |
|---|---|
| `indep_s100`, `indep_s050` | terme propre à la cellule, σ = 1,0 ou 0,5 |
| `laea50_s100` (**modèle en place**), `laea50_s050`, `laea50_s030` | niveau 0,10, blocs de 50 km (σ 0,25), terme propre de σ 1,0, 0,5 ou 0,3 |
| `district_s050` | niveau 0,10, **effet par district** (σ 0,25 ; hiérarchique administratif), terme propre de σ 0,5 |
| `multiscale_s050` | niveau 0,10, blocs de 25, 50 et 100 km (σ 0,15 chacun), terme propre de σ 0,5 |

- **Ce qui reste sans effet** : après le recalage exact sur les régions, le niveau commun et tout effet régional s'annulent.
- **Modèles non testés, et déclarés comme tels** :
  - SPDE et processus gaussien : ils ne tiennent pas dans la mémoire du worker ;
  - BYM2 : non implémenté. Les blocs multi-échelles en tiennent lieu, sous leur propre nom.
- **Gate A1** (ADR-0029). Il exige à la fois :
  - une sélection stable entre les deux moitiés du damier ;
  - la même variante retenue sur les quatre maillages ;
  - pour la variante retenue, une couverture supérieure ou égale au niveau moins 0,10, à chaque niveau.

## Résultats (260 districts, ajustement sur 16 régions)

### Le modèle en place (`laea50_s100`, v0.2.0) n'est pas surconfiant
| maillage | couverture à 50 / 80 / 95 % | rms z (log) | z moyen |
|---|---|---|---|
| H3 r5 | 76 / 94 / 98 % | 0,74 | +0,27 |
| H3 r6 | 82 / 93 / 97 % | 0,78 | +0,24 |
| grille 12,5 km | 69 / 95 / 98 % | 0,74 | +0,27 |
| grille 6,25 km | 82 / 94 / 96 % | 0,73 | +0,23 |

Le modèle sur-couvre à tous les niveaux, avec un rms z d'environ 0,75. Il est donc **prudent** à l'échelle du district, comme à l'échelle régionale. Le prior indépendant de σ = 1 se comporte de la même façon : après le recalage régional, les blocs de 50 km ajoutent peu à cette échelle.

### Les variantes resserrées (σ = 0,5) approchent les niveaux nominaux sans les atteindre
| variante | couverture à 95 % (4 maillages) | couverture à 80 % | score log |
|---|---|---|---|
| `district_s050` | 91,5 – 93,1 % | 79 – 89 % | **0,23 – 0,51** |
| `multiscale_s050` | 92,3 – 93,1 % | 79 – 87 % | 0,27 – 0,48 |
| `laea50_s050` | 91,9 – 92,7 % | 79 – 87 % | 0,27 – 0,57 |
| `indep_s050` | 88,1 – 90,4 % | 73 – 83 % | 0,44 – 0,71 |
| `laea50_s030` | 83,1 – 88,8 % | 70 – 84 % | 0,47 – 0,95 |

- **Les variantes à σ = 0,5 avec structure spatiale** (`district`, `multiscale`, `laea50`) obtiennent les meilleurs scores logarithmiques. Elles restent légèrement sous le niveau nominal à 95 %.
- **Un resserrement sans composante spatiale, ou trop fort, devient surconfiant.** `indep_s050` (sans structure) et `laea50_s030` (σ = 0,3) descendent jusqu'à 83 % de couverture à 95 %.

### Le raster seul, recalé proportionnellement sur les régions
Erreur log médiane aux districts : 0,07 à 0,09 sur les maillages fins, 0,16 sur les grossiers. Au 90ᵉ centile, elle va de 0,46 à 0,55. WorldPop répartit donc bien la plupart des districts, avec une queue d'erreurs d'environ ±50 %. Ce diagnostic ne sert à régler aucune variante.

### Biais commun à toutes les variantes : z moyen de +0,13 à +0,27
Le recensement est en moyenne **au-dessus** de la prédiction médiane du district, en échelle log, alors que les totaux régionaux sont exacts. Deux explications non exclusives :
- l'asymétrie à droite des prédictions log-normales ;
- un raster qui concentre trop la population dans les grands districts urbains, au détriment des autres.

Ce biais n'est pas corrigé ici : il est rapporté.

### Validation croisée et gate A1
| maillage | moitié 0 → | moitié 1 → | retenue |
|---|---|---|---|
| H3 r5 | `multiscale_s050` | `multiscale_s050` | `multiscale_s050` |
| H3 r6 | `district_s050` | `district_s050` | `district_s050` |
| grille 12,5 km | `district_s050` | `multiscale_s050` | aucune (instable) |
| grille 6,25 km | `district_s050` | `district_s050` | `district_s050` |

**Gate A1 : non passé.**
- **Ce qui manque** : la sélection est instable sur la grille de 12,5 km, et les variantes retenues diffèrent selon le maillage (`multiscale_s050` ou `district_s050`, dont les scores sont proches).
- **Ce qui est rempli** : aucune variante retenue n'est en défaut de couverture au regard de la tolérance déclarée. La conservation des marges est exacte par construction.

## Challenge
1. **La prémisse de la revue n'est pas confirmée à l'échelle du district.** Depuis R2b, le modèle en place est prudent, pas surconfiant. Un σ trop étroit, lui, le serait (`laea50_s030`, `indep_s050`).
2. **`district_s050` est avantagé par construction.** Son effet aléatoire porte exactement sur les unités évaluées : il place la variance à l'échelle du test. Cela ne dit rien des autres échelles. `multiscale_s050` n'a pas cet avantage, et ses scores sont voisins.
3. **La grille de σ n'est pas indépendante de tout ce qui précède.** Les valeurs 0,5 et 0,3 ont été choisies après le constat régional de prudence (R2b), mais avant de voir les districts. Les districts ont maintenant été vus : **un second tour sur les mêmes 260 districts ne serait plus une validation indépendante.**
4. **Circularité possible avec WorldPop.** On ignore quels totaux infra-régionaux WorldPop R2025A a utilisés pour le Ghana. Une erreur médiane de 7 à 16 % suggère qu'il n'a pas été calé sur les districts du PHC 2021, mais ce n'est pas vérifié.
5. **Unités plus petites que les cellules.** Jusqu'à 161 districts sur 260 font moins de 4 cellules H3 r5. Leur total repose alors sur l'hypothèse de densité homogène dans la cellule. Ils sont rapportés dans une strate à part, où les couvertures sont plus faibles.
6. **Le bruit du recensement (2 %) reste provisoire** : le taux de couverture de l'enquête post-censitaire (PES) n'est pas intégré.

## Conséquences
- **Le champ gelé reste celui du modèle en place** (`laea50_s100`, v0.2.0), prudent à l'échelle du district. Aucune variante n'est promue, puisque le gate n'est pas passé.
- **Changer de modèle demandera une donnée nouvelle**, plus fine ou indépendante : comptes par zone d'énumération, enquêtes géocodées (R3), ou recensement d'un autre pays. Ce choix sera déclaré avant de voir ces données.

## Tests
- **Unitaires** (`test_population_benchmark.py`) :
  - le CRPS sur tirages retrouve la forme analytique d'une loi normale ;
  - un prédicteur calibré couvre au niveau nominal, un prédicteur surconfiant non, et le score logarithmique les ordonne ;
  - damier déterministe ;
  - une variante n'est jamais notée sur sa moitié de sélection ;
  - le gate refuse une sélection instable, une couverture insuffisante ou des variantes différentes selon le maillage ;
  - variances marginales des composantes ;
  - chaque variante garde l'espérance du raster ;
  - une source de benchmark ne peut pas être une vraisemblance.
- **Adapters** :
  - exclusion des lignes d'agrégats et des sous-métropoles ;
  - une exclusion déclarée mais absente du tableau est une erreur ;
  - motifs de noms retirés des deux côtés ;
  - contrôle `expected_total`.
- **Intégration** : le run au format réel, sur des données fictives, porte maintenant huit districts. Il exerce les étapes de benchmark, la validation croisée, le gate et la section du rapport.
