# M15 — Map-C-Deep (branche de recherche)

*Statut : expérimental, séparé du produit principal (11 phase 11, prompt §55). Contre-factuel historique, non prescriptif.*

## Fait

### Séparation ([ADR-0027](../decisions/ADR-0027-map-c-deep.md))
- **Requête** : `kind: c_deep` (`configs/research/`). Elle passe par la même file de runs, mais ce n'est pas un run du produit.
- **Refus côté produit** : `map_mode: C_DEEP` reste refusé, avec renvoi à la branche.
- **Isolement** :
  - rien en base ; ni archive, ni solution, ni carte ;
  - l'export de la carte Pages refuse ces runs ;
  - les modules de recherche n'importent ni la causalité, ni l'optimisation, ni l'export, ni la confidentialité du produit.
- **Schéma fermé** :
  - ni sources, ni bibliothèque causale, ni manifeste normatif : aucun coefficient contemporain n'est extrapolé (04 §20) ;
  - actions contre-factuelles limitées aux frontières et aux capitales, sans aucun déplacement de population.

### Monde historique synthétique et SCM (`amtgo.research`)
- **Monde** : treillis 20 × 16 de 10 km, de 1885 à 2025 par pas de 10 ans, deux groupes fictifs. Une partition, en 1925, coupe l'aire du second groupe ; le contre-factuel retire cette partition.
- **Vérité et observations** : la vérité (θ, état initial) génère les recensements par bloc, les parts de groupes et les enquêtes d'identification, tous bruités. Les observations et la vérité sont deux artefacts séparés : la vérité n'est lue qu'à la calibration.
- **SCM** : croissance, migration volontaire (masse, capitales, friction frontalière), identification à l'entité d'appartenance (construction nationale, perte au changement d'entité).
- **Estimation** : moindres carrés pondérés par le bruit, erreurs-types par la jacobienne, bootstrap paramétrique.

### Gate H et ensemble
- **Trois contrôles** par forme structurelle :
  - temporal holdout (2005–2025) ;
  - leave-region-out (nord, orthogonal à la partition) ;
  - placebo (frontière fictive).
- **Critère** : z, les résidus standardisés hors échantillon (≈ 1 sous un modèle correct), avec une tolérance de 2.
- **Ensemble** : au moins deux formes structurelles validées, sinon NOT_IDENTIFIABLE.
- **Produit** : X_2025 factuel reconstruit, contre-factuel et écart, avec intervalles à 90 %, pour quatre indicateurs agrégés. Puis calibration sur la vérité synthétique. Les parts de groupes sont CONTROLLED et jamais publiées.

## Résultats (`c_deep_synthetic`)
**Conclusion : HISTORICAL_COUNTERFACTUAL_ESTIMATED**, calibration **COVERED**.

**Estimation et validation**
- Les deux formes passent le Gate H :
  - holdout : z ≈ 1,1 pour les recensements, 0,9 pour les enquêtes ;
  - leave-region-out : z ≈ 1,1 dans les deux cas ;
  - placebo : β = 0,10 ± 0,12.
- β (friction frontalière) = 0,66 ± 0,12, pour une vérité à 0,6 ; λ = 0,68 ± 0,04, pour 0,7.
- γ (attraction des capitales) est faiblement identifié : 2,5 ± 0,7 avec friction, 5,1 ± 1,6 sans. La forme sans friction compense par les capitales.

**Contre-factuel (60 tirages)**

| indicateur (2025) | écart contre-factuel − factuel [90 %] | vérité |
|---|---|---|
| identification à l'entité, est | +0,071 [+0,066 ; +0,075] | +0,072 |
| identification à l'entité, ouest | +0,005 [+0,002 ; +0,007] | +0,004 |
| part de la population à l'est | −0,010 [−0,014 ; −0,007] | −0,008 |
| liens qui traversent la ligne | +0,0006 [+0,0004 ; +0,0009] | +0,0007 |

Lecture, au sein de ce monde synthétique seulement : sans la partition de 1925, l'identification à l'entité d'appartenance serait plus forte à l'est (+7 points), et la population un peu moins concentrée à l'est, autour de la seconde capitale.

## Challenge
1. **Une validation factuelle ne valide pas un contre-factuel.** La forme sans friction passe le Gate H, mais ses intervalles manquent la vérité contre-factuelle sur 3 indicateurs sur 4. D'où les deux formes exigées et l'avertissement dans le rapport.
2. **Gate H fragile** : la première version (écart relatif maximal ≤ 9 %) rejetait la vraie forme 4 fois sur 10 graines de bruit, et le pilote passait par chance de graine. Avec le critère z, la vraie forme passe 10 fois sur 10.
3. **Pouvoir du gate** : une partition mal datée (1955) est rejetée, mais par un seul contrôle (leave-region-out des enquêtes, z = 2,73). Le gate a un pouvoir, modeste.
4. **Leave-region-out** : un découpage est-ouest rendait λ inidentifiable ; il est passé nord-sud.
5. **Vocabulaire** : « meilleur » dans la phrase même qui refuse de choisir une forme ; reformulé.

## Manquant
- **Données historiques réelles** et leur adaptateur. Sans vérité, aucune calibration n'est possible : le statut resterait au mieux exploratoire.
- **La vraie forme fait partie de l'ensemble** parce que le monde est généré par elle. Sur une histoire réelle, rien ne le garantit.
- **Formes plus riches** : infrastructure, langues véhiculaires, conflits. Transport du SCM entre régions.
- **Recomposer X_2026^cf dans le pipeline** (Map-C sur une société contre-factuelle) : délibérément non fait.

## Tests
- **Unitaires** (`test_historical_scm.py`) :
  - conservation de la population par la migration ;
  - friction frontalière ; absence de remise à zéro sans partition ;
  - β et λ retrouvés à 3 se ; placebo nul ;
  - histoire insuffisante non identifiable ;
  - contre-factuel couvert, signes retrouvés ;
  - forme fausse validée mais contre-factuel manqué (red-team) ;
  - partition mal datée rejetée.
- **Red-team** (`test_c_deep_redteam.py`) :
  - C_DEEP refusé comme mode du produit ;
  - aucune entrée contemporaine (sources, bibliothèque causale, manifeste normatif) ;
  - au moins deux formes ;
  - aucun déplacement de population ;
  - isolement du produit, vérité lue seulement à la calibration.
- **Intégration** : run de bout en bout ; statut ; calibration ; parts de groupes absentes du rapport ; aucun artefact du produit.
- **Suite complète** : 333 tests passés sur 334. L'échec venait du red-team M4 : il interdit le mot « composition » dans le module d'export de la carte, et mon nouveau message de refus le contenait. Message reformulé ; red-team M4 et Map-C-Deep relancés, ils passent.

## Benchmarks
Run complet : environ 70 s (estimation 4 à 7 s par forme ; bootstrap de 30 tirages, environ 30 s par forme).
