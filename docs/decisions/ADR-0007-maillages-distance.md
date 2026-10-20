# ADR-0007 — Deux familles de maillage et distance de partitions

*Statut : accepté — 2026-10-20.*

## Contexte
Le MAUP (01 §3) concerne la taille **et la forme** du zonage. Changer seulement
la résolution H3 ne teste pas la forme. Par ailleurs $S_{scale} = 1 -
E[d(G^{r_a}, G^{r_b})]$ (02 §6) exige une distance entre partitions portées par
des maillages différents, que la spec ne définit pas.

## Décision
- Deux familles : `h3` (hexagones, imbrication approximative, index analytique
  seulement — jamais géométrie juridique) et `grid_laea` (carrés en projection
  équivalente, imbrication exacte).
- **Appartenance** (révisée pendant le challenge M2) : une cellule appartient au
  maillage si elle **intersecte** l'emprise, et sa géométrie est **découpée** sur
  l'emprise (`clipped=True`). L'union des cellules égale l'emprise — invariant
  testé. La première version (« centre dans l'emprise ») laissait une bande non
  couverte différente pour chaque maillage : 2 à 6 % de la masse du pilote
  disparaissait dans les transferts, ce qui est un artefact de maillage et non
  un fait des données.
- **Voisinage** : deux cellules sont voisines si leurs géométries (découpées)
  partagent une frontière de longueur positive, pas seulement si l'index les
  déclare adjacentes.
- **Distance entre partitions**, évaluée sur une grille de référence plus fine
  que les deux maillages comparés, chaque cellule de référence prenant
  l'étiquette de la cellule qui contient son centre :
  - `TRANSFER` (défaut) : part minimale de surface à réaffecter après le
    meilleur appariement des étiquettes. Interprétable (« 6 % de la surface
    change d'affectation »), invariante au renommage, métrique.
  - `VI` : variation d'information normalisée par l'entropie jointe. Conservée
    comme variante de sensibilité. **Elle est très sévère aux bords** : sur le
    test « même découpage, deux zonages », elle vaut ≈ 0,49 quand TRANSFER vaut
    < 0,15 ; avec τ_scale = 0,8, presque tout serait déclaré instable.

## Conséquences
`partition_distance` existe dès M2 et est testée (identité, symétrie, bornes,
invariance au renommage, ordre entre découpages proches et orthogonaux).
$S_{scale}$ attend des partitions candidates (M8). Le choix de métrique est un
paramètre de modèle enregistré, dont la sensibilité devra être rapportée.
