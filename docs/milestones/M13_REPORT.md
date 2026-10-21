# M13 — Map-C-Shallow

## Fait

### Mode C_SHALLOW ([ADR-0025](../decisions/ADR-0025-map-c-shallow.md))
- **Ce qui est retiré** : `objectives_for(map_mode)` enlève du vecteur J le seul terme qui exprime le privilège juridique de la géométrie actuelle, **J_T** (02 §21 : C_legal_legacy = 0).
- **Ce qui est conservé** : droits, viabilité, coûts institutionnels réels, réification et baselines. Le statu quo reste une option comme les autres.
- **Manifeste** :
  - C_SHALLOW exige l'optimiseur ;
  - `transition_model` est refusé, car sans G_0 privilégié, le point de départ n'est pas un coût ;
  - Map-C-Deep reste refusé (branche de recherche).

### Dominance bloquée par une connaissance structurelle
- Une ε-dominance de a sur b n'est plus établie si un objectif inconnu est NOT_BETTER pour a face à b. C'est le cas de l'axiome de fusion sur J_P.
- Les relations d'emboîtement sont calculées **par paire** de géométries, sur tous les maillages, et pas seulement face au statu quo.
- L'incertitude symétrique (J_R, UNDETERMINED) ne départage toujours pas le classement.
- La règle vaut pour tous les modes, y compris les trajectoires Map-R : la géométrie d'une trajectoire est sa cible.

### Produit (`artifacts/map_c_shallow.json`, étape `map_c`)
- Conclusion, front, et rang de la géométrie actuelle sans privilège.
- Dominances non résolues.
- **Prime de l'existant** : les options qui entrent au front ou en sortent quand on retire J_T, sur les mêmes évaluations que Map-R.
- **Inventaire hybride** (01 §6) : ce qui est conservé de X_2026 (population, districts, fiscalité, réseau, identités).
- **Gate de phase 9** : INTERPRETABLE seulement si tous les gates sont passés et qu'aucune falsification n'échoue ; RESEARCH_ONLY sinon.
- Formulation contrefactuelle non prescriptive (06 §15), `valid_as_of`, aucune géométrie exportée.

## Résultats (`synthetic_c_shallow`, 2 maillages grille, run worker `6d22c2c9…`)
**Conclusion : DOMINANCE_UNRESOLVED_UNKNOWN_OBJECTIVES.** Front de 8, géométrie actuelle au rang 1.
- Les unions dominent la géométrie actuelle sur les objectifs connus. Mais J_P est NOT_BETTER pour elles (axiome de fusion) et J_R est UNDETERMINED : la dominance n'est pas établie.
- **Prime de l'existant nulle** : retirer J_T ne fait entrer ni sortir aucune option du front. Sur ce monde synthétique, le privilège juridique ne protège rien que le reste du vecteur ne protège déjà.
- **Phase 9 : RESEARCH_ONLY.** Le gate M échoue (calculabilité de D) et R n'est pas évaluable (S^time inconnu).
- Pilote Map-R inchangé : front Pareto de 8, front map_r de 6.

## Challenge
| problème | correction |
|---|---|
| Premier run : sans J_T, l'union chassait la géométrie actuelle du front (rang 2) en ignorant J_P, que l'axiome dit défavorable à la fusion. C'était le biais d'union de M10, réintroduit. | dominance bloquée par toute borne NOT_BETTER ; relations par paire |
| Map-C-Shallow présentée comme « la carte sans l'histoire » | inventaire hybride obligatoire ; Map-C-Deep refusé |
| Trajectoires depuis G_0 en mode C | refusées au manifeste |
| Produit lu comme une conclusion alors que les gates M et R échouent | gate de phase 9 : RESEARCH_ONLY |

## Manquant
- **Map-C-Deep** : SCM historique (04 §325), branche de recherche séparée.
- **Données réelles** : une prime de l'existant non triviale suppose un monde où J_T départage effectivement.
- **S^time et calculabilité de D** : tant qu'ils manquent, la phase 9 reste RESEARCH_ONLY.

## Tests
- **Unitaires** (`test_counterfactual.py`) :
  - objectifs par mode ;
  - une fusion ne chasse pas le statu quo du front ;
  - prime de l'existant et gate de phase 9 ;
  - formulation contemporaine et non prescriptive.
- **Red-team** (`test_m13_redteam.py`) :
  - le retrait porte exactement sur le terme de transition ;
  - trajectoires depuis G_0 refusées ;
  - Map-C-Deep refusé ;
  - aucune géométrie exportée.
- **Intégration** (`test_map_c_shallow_end_to_end`) : run complet, produit, rapport.
- **Suite complète** : 301 tests passés.

## Benchmarks
Étape `map_c` : moins de 0,1 s (elle réutilise les évaluations). Suite complète : 26 min.

## Prochain milestone
M14 — composition continentale : décomposition local → régional → macro → coordination, sans solve monolithique (07 §13).
