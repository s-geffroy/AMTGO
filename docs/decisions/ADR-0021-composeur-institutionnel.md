# ADR-0021 — Composeur institutionnel à géométrie fixe (M9)

*Statut : accepté — 2026-10-20.*

## Contexte
- **Prompt §39** : rechercher des solutions institutionnelles avant de toucher aux frontières, dans un ordre donné.
- **Prompt §40** : un test de nécessité de la souveraineté.
- **07 §12** : optimiser compétences, overlays et frontières vectorielles à territoire fixe.
- **11, phase 4** : le gate du composeur est de pouvoir conclure `NO BORDER CHANGE`.
- **01 §31** : NO TERRITORIAL CHANGE comme meilleur résultat possible.
- **01 §16 et 05 §14** : Goodhart, par exemple un overlay vide qui réduirait F.

## Décision

**Leviers.** Ce sont des changements de vecteurs primitifs, testés dans l'ordre du §39 :

| levier | vecteur modifié |
|---|---|
| application des droits | garde-fous C |
| représentation | seuil de décision qualifié, sans groupe nommé (égalité civique) |
| droits linguistiques | C sur `culture_language` |
| overlay fonctionnel | hyperarête frontalière, μ par canal |
| autonomie fiscale, autonomie territoriale, fédération | transfert de compétences A vers le niveau local, exclusivité préservée |

Confédération et souveraineté changent la géométrie de la souveraineté. Elles sont renvoyées à M10, jamais simulées ici.

**Efficacité.** Chaque levier a une efficacité tirée de la bibliothèque gelée : la part du changement nominal réellement réalisée, ou μ pour un overlay.
- Le levier est évalué **aux deux bornes** de cette efficacité, ce qui forme l'ensemble d'ambiguïté (04 §11).
- Un effet inconnu donne un levier non évalué, qui ne « résout » jamais rien.

**Évaluation de chaque option** (levier seul, puis cumul des leviers dans l'ordre) :
- domination : violations et P(D > τ) maximal ;
- fragmentation réseau et J_conn, overlays compris ;
- indice d'institutionnalisation (Σ A · alignement du niveau) ;
- risque de réification, via l'effet gelé « institutionnalisation → saillance » ;
- C_inst : coordination, application, seuils, overlay ;
- complexité effective.

C_inst et la complexité sont des **objectifs rapportés**, jamais additionnés à D/F/I.

**Conclusions :**

| conclusion | condition |
|---|---|
| `NO_CHANGE` | le statu quo satisfait déjà la contrainte de droits |
| `NO_TERRITORIAL_CHANGE_SUFFICIENT` | une option lève toute violation à la borne basse |
| `INSTITUTIONAL_UNCERTAIN` | une option ne lève les violations qu'à la borne haute |
| `INSTITUTIONAL_INSUFFICIENT_AT_FIXED_GEOMETRY` | aucune option ne suffit ; ce n'est **pas** une recommandation de frontière |

Avec des efficacités I7, la preuve reste EXPLORATORY.
- L'ensemble non dominé (vue robuste) inclut le statu quo.
- Entre ontologies et maillages, la conclusion n'est retenue que si elle est identique partout ; sinon elle vaut CONDITIONAL.

## Ce que le challenge a cassé
| problème | correction |
|---|---|
| Une représentation garantie par groupe (veto ethnique) aurait attaché un droit à l'origine — contraire au hard right `civic_equality` | seuil qualifié sans groupe nommé |
| Un overlay sans effet identifié réduisait F mécaniquement (μ déclaré) | μ vient de la bibliothèque ; inconnu ⇒ levier non évalué (monde I, red-team) |
| Statut « RESOLVES_ROBUSTLY » affiché quand il n'y avait rien à résoudre | `NOT_NEEDED` / `CREATES_VIOLATION` si le statu quo est conforme |
| La dévolution paraissait gratuite | elle accroît le risque de réification quand les districts sont alignés sur un groupe (monde I) |

## Conséquences
- Le monde I vérifie les cinq propriétés à chaque build, et la page est publiée.
- Pilote : NO_CHANGE stable (le statu quo fictif ne viole aucun droit). Les leviers de dévolution montrent un RRI positif.
- M10 compare les candidats territoriaux, chacun avec sa meilleure composition institutionnelle, aux baselines.
