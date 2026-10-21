# ADR-0025 — Map-C-Shallow : contre-factuel contemporain sans privilège juridique (M13)

*Statut : accepté — 2026-10-21.*

## Contexte
- **02 §21** : C_legal_legacy = 0, mais X = X_2026 observé. La carte répond à une question contemporaine.
- **01 §6** : retirer la légitimité des frontières en gardant ce qu'elles ont produit (routes, capitales, identités, fiscalité) fabrique un hybride. Il faut le déclarer, et réserver la dépendance historique à Map-C-Deep.
- **08 §18** : « si les frontières actuelles n'avaient aucune priorité juridique, quelle architecture choisirions-nous avec la société de 2026 ? »
- **11 phase 9** : « seulement après réussite des phases précédentes ».
- **Prompt §55, §77** : Map-C-Deep reste une branche de recherche.
- **ADR-0023** : J_P inconnu, axiome de fusion.

## Décision

### Ce que « sans privilège juridique » retire
Un run peut être en mode `C_SHALLOW`. On y retire du vecteur d'objectifs le seul terme qui exprime le privilège de la géométrie actuelle : **J_T**, la part de la population qui changerait d'État par rapport à elle.

Il n'y a pas de trajectoires : sans G_0 privilégié, le point de départ n'est pas un coût. Un manifeste C_SHALLOW avec `transition_model` est refusé.

Restent les droits, la viabilité, les coûts institutionnels réels, la réification et les baselines. Le statu quo reste une option, évaluée comme les autres.

### Ce qui est conservé : X_2026, déclaré
Le produit conserve, et le dit :
- population et composition observées ;
- districts actuels, en juridictions locales emboîtées ;
- comptes fiscaux par district et régime observé ;
- réseau fonctionnel ;
- identités nationales, si le run en mesure.

Le produit les déclare hybrides par construction (01 §6).

### Dominance bloquée par une connaissance structurelle
Premier run C-Shallow : sans J_T, l'union faisait mieux que la géométrie actuelle sur tous les objectifs connus, et l'en chassait du front (rang 2). Or l'axiome de fusion (ADR-0023) dit que J_P ne peut, pour une fusion, qu'être pire : l'union ne domine donc pas la géométrie actuelle. La classer ainsi en ignorant cette connaissance réintroduisait le biais d'union de M10.

Correction générale :
- une ε-dominance de a sur b n'est **pas établie** si un objectif inconnu est NOT_BETTER pour a face à b ;
- les relations d'emboîtement sont calculées **par paire** de géométries, sur tous les maillages, et pas seulement face au statu quo ;
- l'incertitude symétrique (UNDETERMINED, par exemple J_R) reste ignorée pour le classement, comme en M10 ;
- la règle vaut pour tous les modes et pour les trajectoires Map-R (géométrie d'une trajectoire = sa cible).

### Produit
- Conclusion, front, et rang de la géométrie actuelle sans privilège.
- Dominances non résolues.
- **Prime de l'existant** : comparaison avec l'archive Map-R sur les mêmes évaluations. Elle donne les options qui entrent au front ou en sortent quand on retire J_T.
- Inventaire hybride.
- **Gate de phase 9** : `INTERPRETABLE` si tous les gates sont passés et qu'aucune falsification n'échoue, `RESEARCH_ONLY` sinon.
- Formulation contrefactuelle non prescriptive, dérivée de 06 §15.
- `valid_as_of`.
- Aucune géométrie exportée.

## Ce que le challenge a cassé
| problème | correction |
|---|---|
| Sans J_T, la fusion chassait la géométrie actuelle du front en ignorant J_P, que l'axiome dit défavorable à la fusion | dominance bloquée par toute borne NOT_BETTER ; relations par paire |
| Map-C-Shallow présentée comme la carte « sans l'histoire » | inventaire hybride obligatoire ; Map-C-Deep refusé |
| Trajectoires depuis G_0 en mode C | refusées au manifeste |
| Produit lu comme une conclusion alors que M et R échouent | gate de phase 9 : RESEARCH_ONLY |

## Conséquences
- Pilote C-Shallow (2 maillages grille) : DOMINANCE_UNRESOLVED_UNKNOWN_OBJECTIVES.
  - La géométrie actuelle reste au front.
  - Les unions la dominent sur les objectifs connus, mais J_P est NOT_BETTER et J_R UNDETERMINED.
  - **Prime de l'existant nulle** : retirer J_T ne fait entrer ni sortir aucune option du front. Sur ce monde, le privilège juridique ne protège rien que le reste du vecteur ne protège déjà.
  - Phase 9 : RESEARCH_ONLY (M FAILED, R NOT_EVALUABLE).
- Le blocage s'applique aussi à Map-R. Sur le pilote, les fronts M10–M12 sont inchangés (8 variantes ; 6 trajectoires).
- Restent : Map-C-Deep (SCM historique, 04 §325) ; des données réelles où la prime de l'existant serait non triviale.
