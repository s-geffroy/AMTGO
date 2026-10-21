# ADR-0027 — Map-C-Deep : branche de recherche, SCM historique sur monde synthétique (M15)

*Statut : accepté — 2026-10-21. Branche expérimentale, séparée du produit principal.*

## Contexte
- **02 §22** : X_2026^cf = f_θ(X_historique, A^cf_historique) ; structurellement beaucoup plus incertaine ; statut « historical counterfactual — non-prescriptive ».
- **01 §6** : contre-factuel de la dépendance historique, à publier comme exercice historique de sensibilité, jamais comme recommandation.
- **04 §20** : SCM historique séparé ; jamais extrapoler les coefficients contemporains sur 150 ans.
- **04 §21** : leave-region-out, temporal holdout, placebo, contrôles négatifs.
- **08 §19** : « comment les sociétés auraient-elles pu évoluer sous une autre histoire institutionnelle ? »
- **11 phase 11** et **prompt §55** : branche de recherche, séparée, expérimentale.
- Aucune donnée historique réelle n'est ingérée dans le projet.

## Décision

### Séparation du produit
- Une requête `kind: c_deep` passe par la même file de runs, mais ce n'est pas un `RunRequest`.
- `map_mode: C_DEEP` reste refusé dans le produit, avec renvoi à la branche.
- Le run n'écrit rien en base, ne produit ni archive, ni solution, ni carte. Les modules de recherche n'importent ni la causalité, ni l'optimisation, ni l'export, ni la confidentialité du produit.

### Un banc d'essai à vérité connue, pas une histoire réelle
- Seul un **monde historique synthétique** est admis (1885 → 2025, pas de 10 ans) : aucune source et aucune bibliothèque causale ne peuvent être déclarées.
- Un SCM historique non validé sur une vérité connue ne peut pas être appliqué à une histoire réelle.
- La vérité (θ, état initial) ne sert qu'à générer les observations historiques bruitées, puis à calibrer après coup. Deux artefacts sont séparés :
  - les observations, seules lues par l'estimation ;
  - la vérité, lue seulement par l'étape contre-factuelle, pour calibrer.

### Le SCM historique
Institutions historiques A_t : affectation des cellules à des entités politiques, une capitale par entité. Mécanismes :
- **Croissance** : uniforme, estimée sur les totaux observés.
- **Migration volontaire** : vers la masse (α) et les capitales (γ), freinée par les frontières (β). Les groupes migrent avec leurs parts, si bien qu'aucun territoire n'est attribué à un groupe.
- **Identification à l'entité d'appartenance** : construction nationale (ν), perte λ lors d'un changement d'entité ou d'une migration qui en franchit une.

Estimation et contre-factuel :
- **Estimation** : moindres carrés pondérés par le bruit déclaré, sur les recensements par bloc, les parts de groupes et les enquêtes historiques. Les erreurs-types viennent de la jacobienne ; le bootstrap paramétrique sert à l'ensemble.
- **Actions contre-factuelles** : frontières et capitales seulement, aucun déplacement de population (refusé au schéma).

### Gate H, nécessaire mais pas suffisant
Par forme structurelle (avec friction frontalière, sans friction) :
- **temporal holdout** : estimation avant 2005, prédiction de 2005–2025 ;
- **leave-region-out** : blocs du nord retenus, découpage orthogonal à la partition ;
- **placebo** : frontière fictive horizontale à partir de 1925 ; |β_placebo| ≤ 2 se.

Critère hors échantillon : z, la moyenne quadratique des résidus en unités du bruit déclaré, qui vaut environ 1 sous un modèle correct, avec une tolérance de 2. L'écart relatif maximal des recensements est publié à titre d'information. Pouvoir du gate : une partition mal datée (1955 au lieu de 1925) est rejetée, par le leave-region-out des enquêtes (z = 2,73).

Le critère a changé en cours de route. La première version (écart relatif maximal ≤ 3 σ, soit 9 %) rejetait la **vraie** forme structurelle 4 fois sur 10 graines de bruit, et le pilote ne passait que par chance de graine : un maximum croît mécaniquement avec le nombre de blocs et d'années. Avec z, la vraie forme passe 10 fois sur 10 (z de 0,9 à 1,6). Ce changement vient d'une étude de la méthode sur plusieurs graines, pas d'un réglage sur le résultat du pilote.

**Red-team décisif** : la forme *sans friction* passe le Gate H alors que la vérité en comporte une. Pourtant, ses intervalles contre-factuels manquent la vérité sur 3 indicateurs sur 4. Une validation sur l'histoire factuelle ne valide donc pas un contre-factuel. En conséquence :
- au moins **deux formes structurelles** doivent passer, sinon NOT_IDENTIFIABLE ;
- les formes qui passent forment l'ensemble, sans en retenir une seule ;
- le rapport dit en clair que le Gate H est nécessaire, pas suffisant.

### Produit (artefact de recherche)
- Indicateurs agrégés en 2025, autour de la frontière factuelle, avec intervalles à 90 % :
  - part des liens fonctionnels qui la traversent ;
  - part de la population à l'est ;
  - identification à l'entité d'appartenance, de chaque côté.
- Calibration sur la vérité synthétique (couverture, signe).
- Parts de groupes calculées, CONTROLLED, jamais publiées.
- Statut obligatoire en tête, aucune couche cartographique.

## Ce que le challenge a cassé
| problème | correction |
|---|---|
| Une forme structurelle fausse passe toute la validation factuelle et donne un contre-factuel faux, avec assurance | au moins deux formes validées ; Gate H déclaré nécessaire, pas suffisant |
| Tentation de réutiliser les effets de la bibliothèque contemporaine | aucun champ ne le permet (schéma fermé), aucun import |
| Un leave-region-out est-ouest rendrait λ inidentifiable (seul l'est est traité) | découpage nord-sud, orthogonal à la partition |
| Gate H d'abord fondé sur l'écart relatif maximal : la vraie forme rejetée 4 fois sur 10 graines, réussite du pilote due à la graine | critère z (résidus standardisés, ≈ 1 sous un modèle correct, tolérance 2) : 10 sur 10 ; changement déclaré, étude multi-graines publiée |
| Un contre-factuel qui déplacerait des populations | refusé au schéma : frontières et capitales seulement |
| Le mot « meilleur » dans la phrase même qui refuse de choisir une forme | reformulé ; vocabulaire contrôlé par le test d'intégration |

## Conséquences
- Pilote synthétique : les deux formes passent le Gate H, l'ensemble compte 60 tirages, et la vérité contre-factuelle est **couverte** pour les quatre indicateurs, signes retrouvés (M15_REPORT).
- Limite majeure : la vraie forme structurelle fait partie de l'ensemble, parce que le monde est généré par elle. Sur une histoire réelle, la vraie forme est inconnue, et aucune calibration ne remplacerait celle-ci.
- **Manquant** :
  - données historiques réelles (cartes et recensements numérisés) et leur adaptateur ;
  - formes structurelles plus riches (infrastructure, langues véhiculaires, conflits) ;
  - transport du SCM entre régions ;
  - recomposition du contre-factuel X_2026^cf dans le pipeline (Map-C sur société contre-factuelle), délibérément non faite : elle empilerait l'incertitude du contre-factuel historique sous une archive normative.
