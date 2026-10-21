# ADR-0024 — Map-R régional : trajectoires de transition et produit conditionnel (M12)

*Statut : accepté — 2026-10-21.*

## Contexte
- **02 §20** : Map-R = J + C_transition(G, G_0). **02 §26** : transition G_0 → … → G_T et coût J_T = Σ_t [C_T(a_t) + λ_I ι(a_t) + λ_U U_causal(a_t) − λ_V VOI(a_t)]. **02 §27** : exception d'urgence. **02 §34** : le résultat est un tuple, pas une carte.
- **08 §17, §24-25** : amélioration réaliste depuis l'existant ; une trajectoire peut valoir mieux qu'une cible ; valeur d'information.
- **Prompt §75-80** : pas de frontière nette hors ROBUST/CONDITIONAL ; incertitude en bandes ; modes de carte ; baselines ; hiérarchie contrefactuelle ; explication humaine.
- **06 §5, §12, §15-16** : poids de réversibilité normatifs ; la sécurité prime la valeur d'information ; formulation admise ; `valid_as_of`.
- **10 §19** : table `transitions`. **ADR-0009** : Map-R est une archive avec coût de transition, jamais un `argmin`.

## Décision

### Trajectoires
Une trajectoire part du statu quo et monte la **hiérarchie contrefactuelle** (§79), sans jamais redescendre :

no change < droits < réforme institutionnelle < autonomie < fédération < affaiblissement de frontière < changement de frontière < souveraineté

Trois familles de trajectoires :
- **statu quo** : une étape `no_change` ;
- **institutionnelles** : chaque levier à géométrie fixe seul, puis chaque préfixe de l'ordre du §39 ;
  - l'état après l'étape k est l'option du composeur qui applique les k premiers leviers, réévaluée (08 §24), à la borne basse de l'efficacité gelée ;
  - un effet inconnu rend l'option non évaluable, et elle n'est jamais « résolue » ;
- **territoriales** : un changement de frontière vers chaque cible territoriale du front de l'archive validée.
  - L'étape est `sovereignty` si elle crée des États, `border_change` sinon.
  - Aucun effet territorial causal n'est identifié : U = 1.

L'affaiblissement de frontière relève du régime continental (R2/R3). Il n'est pas modélisé à l'échelle régionale ; la sensibilité de régime (M11) en tient lieu.

Une étape intermédiaire qui viole les droits rend la trajectoire **infaisable** : on ne traverse pas une violation pour atteindre une cible.

### Coût
J_path = Σ_t [λ_I ι(a_t) + λ_U U(a_t) − λ_V VOI(a_t)]. Ce coût s'ajoute au vecteur J de l'état final, qui contient J_T (part de la population qui change d'État) et J_pkg (coût institutionnel du paquet).
- **Aucun taux de conversion** n'est introduit entre unités : J_path est un objectif de plus dans l'archive.
- **λ** : normatifs, dans le NormativeManifest (06 §5).
- **ι(a)** : paramètre de modèle déclaré par type d'action, avec ι(no_change) = 0 imposé par le schéma.
- **U** : largeur relative de l'intervalle de l'effet gelé ; 1 si l'effet est inconnu.
- **VOI** : un **indicateur**, pas une valeur espérée de l'information. Il vaut 1 si l'étape est réversible (ι ≤ seuil déclaré) et porte sur un effet qui n'est pas un fait causal (08 §25).

### Urgence (02 §27, 06 §12)
Si le statu quo présente une domination grave urgente, seule une trajectoire dont la **première** étape lève toute violation reste faisable. Ne rien changer devient infaisable, et la VOI ne compte plus.

### Archive et conclusion
Les trajectoires sont des solutions de l'archive (ρ, ε-dominance), avec la transition **comprise** dans la comparaison au statu quo. Les objectifs inconnus suivent la règle M11 : une trajectoire institutionnelle garde la géométrie, donc ses inconnus sont égaux à ceux du statu quo, et elle peut être conclue meilleure.

Conclusions possibles :
- `STATUS_QUO_NOT_DOMINATED` ;
- `INSTITUTIONAL_PATH_IMPROVES_ON_STATUS_QUO` ;
- `TERRITORIAL_PATH_IMPROVES_ON_STATUS_QUO` ;
- `UNRESOLVED_UNKNOWN_OBJECTIVES` ;
- `INFEASIBLE`.

### Produit
Le produit suit le tuple 02 §34 : pour chaque trajectoire, des étapes, un rang et une explication (§80).
- **Explication** : ce qui change, ce qui s'améliore ou se dégrade au-delà de ε, le support causal, l'incertitude et les hypothèses normatives.
- **Formulation** : la seule admise (06 §15).
- **Hiérarchie** : niveau par niveau ; on indique le premier niveau présent au front.
- **Datation** : `valid_as_of`, date du run et millésimes des données.
- **Couche cartographique** : elle n'est publiée que si la validation permet une publication **et** si le privacy guard la laisse sortir. Une frontière candidate dérive des parts de groupes, donc elle est restreinte. Sinon la couche reste vide et dit pourquoi.

### Base
Migration 0013 : table `transitions` (10 §19) et type `transition_action`. Chaque étape est rattachée à la solution visée.

## Ce que le challenge a cassé
| problème | correction |
|---|---|
| Sommer des coûts de natures différentes (composeur, fiscal, population) pour obtenir un J_T scalaire | J_path ne somme que des termes sans unité ; les coûts restent des objectifs séparés |
| Conclusion « NO_CHANGE » alors que le front contient des changements de frontière en compromis | `STATUS_QUO_NOT_DOMINATED`, et le rapport parle de compromis |
| VOI présentée comme une valeur d'information | indicateur déclaré ; nul pour toute étape irréversible et pour toute frontière (aucun effet identifié) |
| Trajectoire échelonnée qui traverserait une violation de droits | infaisable à la première étape fautive |

## Conséquences
- Pilote : le statu quo n'est dominé par aucune trajectoire une fois la transition comptée (`STATUS_QUO_NOT_DOMINATED`). Le front ne contient, à côté du statu quo, que des changements de frontière en compromis : ils améliorent la fragmentation, l'intégration et la viabilité, et dégradent la transition, la pénalité et souvent le coût institutionnel.
- Aucune trajectoire institutionnelle n'est au front : le statu quo ne viole aucun droit, et les leviers ne font qu'ajouter des coûts.
- Couche Map-R vide (NOT_IDENTIFIABLE).
- Restent : la trajectoire dynamique au-delà des préfixes du composeur (recomposer une cible territoriale après changement de frontière) ; une VOI calculée ; l'affaiblissement de frontière à l'échelle régionale ; une représentation cartographique en bandes compatible avec le privacy guard.
