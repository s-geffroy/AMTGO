# ADR-0026 — Coordination continentale par composition, sans solve monolithique (M14)

*Statut : accepté — 2026-10-21.*

## Contexte
- **07 §13** : « Continental solve monolithique interdit en V1 » ; décomposition local → régional → macro → coordination continentale.
- **07 §14** : petits sous-problèmes vérifiés exactement.
- **11 phase 10** : fédérer les problèmes régionaux via bassins, corridors, marché, sécurité, migrations.
- **02 §33** : master problem = archive de Pareto ρ[J] sous F_hard, jamais un argmin.
- **05 §14** : attaque Goodhart « transfert de coûts vers le niveau continental ».
- **09 §14-15** : cinq régimes de conclusion ; les anciens bassins sont des unités analytiques, recalculées sous plusieurs régimes.
- **ADR-0024 / 0025** : produit Map-R, axiome de fusion appliqué par paire.

## Décision

### Un run continental compose des runs régionaux
- Une requête `kind: continental` nomme des runs régionaux Map-R complets et un modèle de coordination.
- À la soumission, chaque région est soumise comme un run ordinaire, puis la composition. Le worker suit l'ordre de soumission : la composition ne démarre qu'après ses régions, et une région en échec la fait échouer avec son message.
- Étapes : `regional_check` → `interfaces` → `regional_options` → `coordination` → `report`.

### Commensurabilité exigée
Le manifeste est refusé si les régions diffèrent sur l'un de ces points :
- manifeste normatif ou régime ;
- optimiseur ou modèle de transition ;
- noyau de liens ou ontologies ;
- familles de maillage appariables ;
- résolutions ε.

Il l'est aussi si deux régions déclarent le même contexte ou si leurs emprises se recouvrent : la population serait comptée deux fois. Sinon on additionnerait des grandeurs définies différemment.

### Aucune frontière ne traverse une interface
- Une option continentale est un tuple : une trajectoire Map-R par région, un ensemble de couches par interface.
- Les États candidats restent dans leur région. Tout lien inter-régional est donc coupé, quelle que soit l'option régionale.
- Une frontière à travers une interface relèverait d'un run régional sur la macro-région, pas d'une coordination.

Les objectifs sont séparables et s'agrègent par ω = (paire de maillages, ontologie) :

| objectif | agrégation |
|---|---|
| J_D, J_V, J_reif | maximum sur les régions (une violation ne se compense pas ailleurs) |
| J_F, J_conn, J_T | moyenne pondérée par la population |
| J_G | (Σ J_G,r · W_r + coupe inter-régionale atténuée par les couches) / (Σ W_r + W_interfaces) |
| J_inst | Σ régions + gestion des frontières d'interface + coût des couches |
| J_pkg, J_path | sommes ; une couche est une étape d'affaiblissement de frontière (§79, 02 §26) |
| J_R, J_P | UNKNOWN ; relation d'emboîtement composée, axiome de fusion appliqué |

### Couches de coordination
Types :
- **marché** et **mobilité** : sur tous les liens transfrontaliers ;
- **corridor** : sur une bande autour de l'interface ;
- **sécurité** : sur le coût de gestion de la frontière ;
- **bassin** : refusé tant qu'aucune hydrographie n'est ingérée (pas de bassin inventé).

Règles :
- **Coût** : chaque couche a un coût annuel déclaré, strictement positif. Une couche gratuite déplacerait un coût vers le niveau continental sans le compter.
- **Effet** : il vient d'une bibliothèque continentale gelée, faite d'effets déclarés I6/I7 seulement, faute de panel continental.
- **Évaluation** : à la borne **robuste** (μ basse, coût haut). La borne optimiste dit seulement quelles couches entreraient au front : une priorité de recherche.

### Le coût invisible au niveau régional est compté
La frontière extérieure d'une région n'entre jamais dans son J_inst. Au niveau continental, la gestion de chaque frontière d'interface est comptée (longueur × coût par km de l'optimiseur), et elle apparaît dans le produit (`costs_moved_to_continental_level`).

### Décomposition vérifiée et réparée
- **Élagage** : chaque région fournit son front Map-R (plus le statu quo), chaque interface le front de ses ensembles de couches.
- **Pourquoi il est approché** : par séparabilité, il est sûr ; mais l'ε-dominance et le maximum peuvent masquer une dominance régionale. Exemple : une option dominée dans sa région sur J_D, quand l'autre région fixe le maximum.
- **Contrôle et réparation** : quand la taille le permet, deux énumérations exhaustives contrôlent les deux élagages. Toute option manquée est réintégrée et l'archive reconstruite.
- **Au-delà** : l'approximation est déclarée.

### Produit
- Archive continentale et conclusion ; catégorie de publication = la moins publiable des régions.
- Régimes de conclusion (09 §14) par région et par interface. Un régime n'est **établi** que si une option domine le statu quo, inconnus tranchés.
- « Séparation supplémentaire dangereuse » exige que toute trajectoire créant des États soit infaisable, ou pire que le statu quo sur les droits (J_D) au-delà de ε.
- Une réification plus forte (J_reif, borne haute tirée d'un effet déclaré I7) est publiée comme **signal**, sans établir le régime.
- Formulation conditionnelle (06 §15) et `valid_as_of` ; couche cartographique vide.
- En base : migration 0014 (`continental_compositions`, `continental_regions`) et migration 0015 (provenance rattachée à la composition, jamais à `run_manifests`).

## Ce que le challenge a cassé
| problème | correction |
|---|---|
| La frontière d'interface n'est comptée par aucune région : la composer à coût nul cacherait un coût | coût de gestion d'interface compté au niveau continental et publié |
| Une couche gratuite ou un bassin sans hydrographie | refusés au manifeste |
| Le front composé perd une option quand le maximum masque une dominance (test construit) | contrôle exhaustif et réparation ; approximation déclarée au-delà de la borne |
| Régions sous des régimes, normes ou maillages différents | refus de commensurabilité |
| La même région deux fois, ou des emprises qui se recouvrent | refus (double comptage) |
| Une couche présentée comme utile sur une hypothèse d'expert | bornes basses nulles, borne haute = priorité de recherche |
| Provenance continentale sur la clé étrangère de `run_manifests` (rejetée par la base) | colonne `continental_run_id` (0015), exclusive de `run_id` |
| Un régime de conclusion lu sur un compromis du front | établi seulement par dominance ; séparation : toutes les trajectoires |
| Premier pilote : « séparation dangereuse » établie sur la seule borne haute de J_reif (hypothèse I7) pour des options qui restent des compromis au front | le régime exige infaisabilité ou droits dégradés ; J_reif devient un signal |

## Conséquences
- Pilote (ouest = smoke, est = nouvelle région synthétique adjacente) : STATUS_QUO_NOT_DOMINATED. Le statu quo composé reste au front, et les deux contrôles exhaustifs donnent un front identique (voir M14_REPORT).
- Aucune couche n'entre au front à la borne robuste. Mobilité et sécurité y entreraient à la borne haute : c'est ce qu'il faudrait mesurer.
- **Limites déclarées** :
  - J_F et J_conn ignorent les liens de groupe transfrontaliers ; le bénéfice des couches pour les groupes répartis de part et d'autre (09 §2) est donc sous-estimé, au détriment des couches ;
  - la composition multiplie les fronts de toutes les régions, sans élagage intermédiaire entre fusions successives ;
  - pas de recomposition continentale sous R0–R3 : la dépendance au régime est lue sur les validations régionales ;
  - stress-tests continentaux (09) sur géographies réelles.
