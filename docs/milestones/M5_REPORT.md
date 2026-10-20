# M5 — Domination, fragmentation, intégration

## Fait

- **Types** :
  - compétences (10 domaines, invariant d'exclusivité §84), règles de décision (seuil, veto), garde-fous, représentation ;
  - partitions multi-niveaux (sans orphelin, emboîtées) et vecteurs de frontière σ ∈ [0,1]⁶ ;
  - hyperarêtes (union des types §27/02 §4) avec atténuation μ par canal ;
  - flux de mobilité typés ; infrastructure K_obs / K_pot séparées.
- **Moteurs** ([ADR-0017](../decisions/ADR-0017-dfi.md)) :
  - **domination** D_pot / D_real, avec contrainte de droits et drapeau d'urgence ;
  - **fragmentation** par canal (liens coupés, jamais présence) ;
  - **intégration** (tenseur, J_conn) ;
  - **alignement** et **risque de réification** (intervalle ou UNKNOWN).
- **État social** : effectifs, noyaux de liens, qualité, identité nationale séparée ; classe CONTROLLED minimale ; canaux sans données = UNKNOWN.
- **Mondes A–F** : six propriétés vérifiées à chaque build et publiées.
- **Pilote** : D/F/I du statu quo déclaré (16 districts, 2 États fictifs) sous chaque ontologie et sur chaque maillage ; S^ontology et S^scale portent désormais sur D/F/I.
- **Configuration** : poids κ_c (manifeste normatif), gabarits de frontière par régime, modèle D/F/I, statu quo déclaré.

## Résultats

### Mondes A–F

| propriété | valeurs |
|---|---|
| A ≪ B : couper deux populations séparées rompt bien moins que couper deux populations intégrées | J_conn 0,003 vs 0,043 |
| C : l'overlay de corridor atténue la fragmentation de mobilité des pastoraux | 0,51 → 0,05 (régime de mobilité : 0,10) |
| D : couper la métropole mixte rompt plus que la laisser entière | 0,140 vs 0,022 |
| E : majorité exclue → violation ; levée par des garde-fous | D_pot 0,80 → 0,05 |
| F : même ethnonyme, identités distinctes, liens faibles → F ≈ 0 | réseau 0,002, culturel 0, territorial UNKNOWN |
| F' : identité partagée, liens forts → F > 0 | 0,094 |

### Pilote (statu quo, régime R1)

- aucune violation de droits sur aucun domaine ; D_real UNKNOWN (aucune observation) ;
- J_conn ≈ 3–5×10⁻⁴ ; alignement frontières/groupes 0,14–0,18 ;
- S^ontology (D/F/I) = 0,99 ; S^scale (D/F/I) = 0,95 avec plancher, mais écart relatif brut 0,42–0,54 sur des quantités sous le plancher : stabilité jugée en absolu seulement, et le rapport le dit.

## Challenge

Cinq défauts trouvés et corrigés (détail dans ADR-0017), dont deux erreurs de conception : la normalisation de J_conn et le canal territorial fondé sur la seule présence. S'y ajoutent un bug latent de M0 (validation d'`UncertainValue`) et un artefact MAUP de discrétisation.

## Manquant

- D_real : aucune source synthétique d'observation de discrimination.
- Canaux de mobilité, culturel, institutionnel, territorial dans le pilote : sans données, donc UNKNOWN.
- Qualité des contacts : supposée uniforme.
- Effets causaux de l'institutionnalisation sur la saillance : M7 (bornes I7 à ce stade).
- σ* et sélection de géométries : M8–M10.

## Tests

- **Unitaires** : règles de décision, exclusivité des compétences, absence de frontière, canaux inconnus, atténuation totale, monotonie en σ (hypothesis), formule de domination, urgence, alignement, réification, classe d'accès, vecteur de frontière.
- **Red-team** : propriétés A–F, présence ≠ fragmentation, pas de canal territorial sans attachement.
- **Intégration** : propriétés du pilote.

## Benchmarks

Pilote complet (31 étapes) ≈ 35 s, dont D/F/I sur H3 r6 (4 777 cellules, quadrature) ≈ 11 s. Suite de tests : 157 s.

## Dette technique

- Noyau par quadrature en boucle Python sur les paires de cellules : à vectoriser si les maillages grossissent.
- S^ontology et S^scale reposent sur trois quantités principales ; à élargir quand les candidats existeront (M8).

## Prochain milestone

M6 — scénarios, régimes constitutionnels détaillés, viabilité contextuelle (après revue).
