# M11 — Validation et red-team

## Fait

### Biais déclarés en M10 ([ADR-0023](../decisions/ADR-0023-validation-red-team.md))
- **J_P** (hétérogénéité des préférences) est ajouté à J et reste UNKNOWN : aucune enquête de préférences. Il n'est jamais déduit des parts de groupes (test AST).
- **Conclure exige les inconnus.** Un objectif inconnu ne départage pas l'archive, mais il bloque toute conclusion de dominance sur le statu quo, sauf si un axiome le tranche. Axiome de fusion : une fusion n'est jamais meilleure sur J_P, un raffinement jamais pire. Nouvelle conclusion : `DOMINANCE_UNRESOLVED_UNKNOWN_OBJECTIVES`.
- **Recomposition par candidat** : un candidat qui viole la contrainte de droits passe par le composeur M9. Le coût du paquet devient l'objectif J_pkg. Sans paquet robuste, il reste infaisable, sans relaxation.

### Étape `validation`, après `pareto`
- **S^parameter** : 10 réglages normatifs alternatifs, un à la fois.
- **Régimes** R0–R3, sur J_V et J_inst.
- **Archive par maillage** (§45).
- **9 ablations** (05 §13).
- **3 attaques Goodhart** et 4 détecteurs.
- **Contrôles de falsification** sur les mondes B, C, D.
- **Red-team de confidentialité** : publication évaluée en entier, 6 attaques, 2 contrôles bénins.
- **Gates M, C, O, S, R** et catégorie de publication (05 §21).

### Base
Migration 0012 : table `validation_gates`. Un déclencheur refuse une solution ROBUST ou CONDITIONAL sans tous les gates passés.

## Résultats (pilote, run worker `c7261f83…`)

### Conclusion de l'archive
`DOMINANCE_UNRESOLVED_UNKNOWN_OBJECTIVES`.
- L'union (k = 1, deux familles) domine le statu quo sur les objectifs connus, hors transition.
- Mais J_P est NOT_BETTER (fusion) et J_R UNDETERMINED : la conclusion M10 « l'union domine » est retirée.
- Le front compte 8 variantes, inchangé.

### Gates

| gate | statut | raison |
|---|---|---|
| M | **FAILED** | calculabilité D |
| C | PASSED | |
| O | PASSED | benchmark exact et Goodhart |
| S | PASSED | 6/6 attaques bloquées ; seuls les 4 maillages sont publiables |
| R | NOT_EVALUABLE | S^time UNKNOWN (un seul millésime, 2025) |

Catégorie : **NOT_IDENTIFIABLE**, aucune publication.

### Régimes
- Sous R2 (confédéral) et R3 (fédéral continental), la conclusion devient NO_TERRITORIAL_CHANGE.
- Sous R0 et R1, la dominance reste non résolue.
- La conclusion **dépend donc du régime** (05 §19), et c'est central pour toute lecture.

### Sensibilité normative
- Aucun des 10 réglages ne change la conclusion.
- À τ = 0,4, le statu quo, ses deux baselines et la bipartition spectrale sortent du front.

### Multi-échelle
- Même conclusion et front de 8 sur les 4 maillages.
- Aucune variante ne dépend d'un seul maillage.

### Ablations
- Retirer D, F, I, l'incertitude ou la réification ne change rien : le pilote ne départage presque rien.
- Retirer la couche causale fait sortir 2 variantes du front.
- Identité nationale, mobilité et infrastructure potentielle sont NOT_APPLICABLE : le pilote ne les mesure pas.

### Goodhart
**Faille trouvée** : la frontière en dents de scie atteignait le front sans signalement.
- Elle gagne sur J_V (0,48 contre 0,50) en déplaçant des cellules fiscalement riches.
- La compacité globale ne la distinguait pas des communautés de Louvain (0,35 contre 0,32–0,41).

Correction : un détecteur de cellules en saillie (≥ 0,37 contre ≤ 0,07 pour tous les candidats générés), et un test de régression.

Bilan : les 3 attaques sont signalées. Les 3 variantes de Louvain sont signalées micro-États, pour revue.

### Falsification
- 3 contrôles PASSED.
- 4 NOT_APPLICABLE, qui exigent des données réelles.

## Challenge
Cinq défauts traités (ADR-0023) :
- une conclusion tirée en ignorant les inconnus ;
- la tentation de mesurer J_P par la diversité des groupes ;
- la faille de la dent de scie ;
- une suite de confidentialité trivialement bloquée en PUBLIC ;
- un S^publish calculé sans S^time.

## Manquant
- **S^time** : il faut un second millésime de données ; d'ici là, aucune publication n'est possible.
- Régimes appliqués aux frontières σ et à la domination (seuls J_V et J_inst varient).
- Ablations amont (identité, mobilité) : exigent des canaux mesurés et une réévaluation.
- k, proxies sensibles et seuils Goodhart : choix provisoires, à valider par la gouvernance (06).
- Différenciation exacte entre supports emboîtés.
- Contrôles de falsification réels (Rwanda, Afrique du Sud, Sahara, EPR) : pilote réel.

## Tests
- **Unitaires** :
  - relation au statu quo et axiome de fusion ;
  - conclusion bloquée par un inconnu ;
  - dépendance à un seul maillage ;
  - recomposition, ou violation qui reste ;
  - seuils alternatifs monotones ;
  - S^publish et catégories ;
  - détecteurs Goodhart ;
  - règles de publication, red-team, garde dégénéré qui échoue à Gate S ;
  - falsification.
- **Red-team** :
  - dent de scie signalée ;
  - overlay vide sans effet et coûteux ;
  - transfert de coûts continental compté ;
  - J_P jamais calculé ;
  - inconnus qui ne concluent jamais ;
  - sensibilité sans droits relaxables ;
  - attaques bloquées sous le manifeste par défaut ;
  - carte publique inutile au ciblage.
- **Intégration** :
  - gates et catégorie, Goodhart et Gate S passés ;
  - en base : 5 gates, et le déclencheur refuse une solution ROBUST.
- Suite complète : 281 tests.

## Benchmarks
- Évaluation : 29 à 38 s par maillage grille ou H3 r5, et 64 s sur H3 r6 (contre 8 et 25 s en M10). Le surcoût vient des attaques, des seuils et régimes alternatifs, et des formes.
- Validation : moins d'une seconde.
- Suite complète : 21 min.

## Prochain milestone
M12 — Map-R régional (après revue).
