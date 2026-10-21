# M12 — Map-R régional

## Fait

### Trajectoires ([ADR-0024](../decisions/ADR-0024-map-r-regional.md))
- Chaque trajectoire part du statu quo et monte la hiérarchie contrefactuelle du §79 sans redescendre.
- Trois familles :
  - le statu quo ;
  - les leviers institutionnels, seuls ou en préfixes de l'ordre du §39 ; chaque étape est réévaluée sur l'option correspondante du composeur ;
  - le changement de frontière vers chaque cible territoriale du front validé.
- Une étape intermédiaire qui viole les droits rend la trajectoire infaisable.

### Coût et urgence
- **Pénalité** (02 §26) : J_path = Σ_t [λ_I ι + λ_U U − λ_V VOI].
  - Les λ sont normatifs (NormativeManifest), ι est déclaré par type d'action.
  - U est la largeur relative de l'effet gelé : 1 pour une frontière, faute d'effet territorial identifié.
  - VOI est un indicateur réversible / non établi, pas une valeur espérée.
- **Urgence** (02 §27) : en cas de domination grave urgente, seule une trajectoire dont la première étape lève toute violation reste faisable, et la VOI ne compte plus.

### Archive et produit
- L'archive des trajectoires compte la transition dans la comparaison au statu quo (Map-R = J + C_transition).
- Produit (02 §34) :
  - conclusion et hiérarchie niveau par niveau ;
  - explication par trajectoire (§80) ;
  - formulation 06 §15 et `valid_as_of` ;
  - couche cartographique, publiée seulement si la validation et le privacy guard le permettent.

### Base
Migration 0013 : table `transitions` (10 §19) et type `transition_action`.

## Résultats (pilote, run worker `a0e172aa…`)

**Conclusion : STATUS_QUO_NOT_DOMINATED.** 19 trajectoires, front de 6.
- **Statu quo** : seule trajectoire du niveau 0, au front.
- **Changements de frontière** : 5 au front, tous des compromis.
  - Ils améliorent la fragmentation, l'intégration, les liens fonctionnels et la viabilité.
  - Ils dégradent la transition (23 à 86 % de la population change d'État), la pénalité (1,40) et souvent le coût institutionnel et la réification.
- **Trajectoires institutionnelles** : aucune au front.
  - Le statu quo ne viole aucun droit, donc les leviers n'ajoutent que du coût et de la pénalité.
  - Fiscal, autonomie territoriale et fédération accroissent en plus la réification.
- **Premier niveau de la hiérarchie au front** : `no_change`.
- **Urgence** : aucune estimation au statu quo.
- **Couche Map-R** : vide (catégorie NOT_IDENTIFIABLE).

Observation : à la borne basse de son efficacité, l'overlay fonctionnel ne crée aucun overlay (complexité 0). Sa trajectoire ne change rien et coûte une pénalité. Elle reste dominée, ce qui est le comportement attendu.

## Challenge
Quatre défauts traités (ADR-0024) :
- un coût de transition scalaire qui aurait sommé des unités différentes ;
- une conclusion `NO_CHANGE` trompeuse en présence de compromis ;
- une VOI présentée comme une valeur ;
- une trajectoire qui traverserait une violation de droits.

## Manquant
- Recomposer une cible territoriale **après** le changement de frontière (trajectoires mixtes frontière + leviers).
- Une VOI calculée (valeur espérée de l'information) plutôt qu'un indicateur.
- L'affaiblissement de frontière à l'échelle régionale (aujourd'hui : sensibilité de régime continental).
- Une représentation cartographique en bandes (§76) compatible avec le privacy guard : une frontière candidate dérive des parts de groupes et reste restreinte.
- S^time, toujours inconnu (M11) : aucune trajectoire n'a de robustesse connue.

## Tests
- **Unitaires** :
  - manifeste (ι(no_change) = 0, toutes les actions présentes) ;
  - U et indicateur de VOI ;
  - réévaluation par étape, violation intermédiaire, option non évaluable ;
  - transition comptée dans la comparaison ;
  - amélioration institutionnelle concluable à géométrie inchangée ;
  - urgence ;
  - formulation.
- **Red-team** :
  - ni « best », ni argmin, ni optimal ;
  - aucune formulation interdite ;
  - couche soumise à la publication et au guard ;
  - frontière sans effet causal ni VOI, même déclarée réversible.
- **Intégration** :
  - statu quo au front, hiérarchie complète, couche vide ;
  - formulation conditionnelle, et aucun mot interdit dans le rapport ;
  - en base : trajectoires enregistrées, statu quo au rang 1.
- Suite complète : 292 tests.

## Benchmarks
Étape `map_r` : moins de 0,1 s. Suite complète : 21 min.

## Prochain milestone
M13 — Map-C-Shallow (après revue).
