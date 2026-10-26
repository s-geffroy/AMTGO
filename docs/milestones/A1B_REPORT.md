# A1b — Second test du modèle spatial de population (Tanzanie, Malawi)

*Statut : test préenregistré dans l'[ADR-0029 § 6](../decisions/ADR-0029-elg-seg-gates-feuille-de-route.md) (commit `d8d91dc`), avant toute lecture des totaux de district. **Gate A1b non passé.** Selon les conséquences fixées d'avance : le modèle en place reste, et il n'y a pas de troisième tour sur ces données. Rien n'est publié.*

## Fait
- **Candidates** : `laea50_s100` (modèle en place), `laea50_s050`, `district_s050`, `multiscale_s050`. Paramètres identiques à [A1](A1_REPORT.md).
- **Tanzanie** (run `f3749577…`) :
  - marges : régions COD-PS 2020 ;
  - unités notées : 169 districts COD-PS 2020 v2 (CC BY-IGO), polygones geoBoundaries ADM2 ;
  - jointure : 29 alias de conseils urbains (noms seulement), et le district de Songwe (créé en 2016, sans ligne dans le tableau) regroupé avec Chunya, avec qui il partage la plus longue frontière (296 km sur 747).
- **Malawi** (run `dd9847ba…`) :
  - marges : 3 régions COD-PS 2023, sur les polygones de district regroupés (le ADM1 de geoBoundaries est sous ODbL) ;
  - unités notées : 28 districts.
- **Zambie : retirée avant toute lecture de valeur.** C'est le cas « pays inutilisable » prévu par la règle :
  - le tableau COD-PS 2020 porte les 74 districts de 2010 (projection du US Census Bureau) ;
  - les seuls polygones ouverts en ont 116 ;
  - la table de correspondance fournie par la source est cassée (`#REF!`).
  
  La couverture devait donc tenir sur les **deux** pays restants.
- **Code** :
  - lecteur xlsx en bibliothèque standard (adapter `admin_table`, paramètre `sheet`) ;
  - pièces A1b écrites par run (`benchmark_summary`) ;
  - gate combiné entre pays : `amtgo benchmark gate-a1b <runs> --removed pays=raison`, qui écrit `/state/benchmarks/a1b_gate.json`.

## Résultats (agrégats seulement)

### Couverture à 50 / 80 / 95 %, toutes unités

| maillage (part des districts < 4 cellules) | `laea50_s100` | `laea50_s050` | `district_s050` | `multiscale_s050` |
|---|---|---|---|---|
| TZA H3 r4 (138 / 169) | 56 / 76 / **83** | 41 / 63 / **73** | 41 / 62 / **77** | 43 / 61 / **76** |
| TZA grille l4 (73 / 169) | 66 / 85 / 88 | 49 / 72 / **83** | 56 / 76 / **83** | 53 / 72 / **83** |
| TZA H3 r5 (45 / 169) | 70 / 88 / 96 | 59 / 81 / 89 | 66 / 83 / 91 | 60 / 80 / 91 |
| TZA grille l5 (31 / 169) | 71 / 89 / 96 | 65 / 82 / 89 | 67 / 86 / 92 | 63 / 80 / 91 |
| MWI (4 maillages, 1 à 3 / 28) | 89–100 / 100 / 100 | 79–96 / 96–100 / 100 | 89–96 / 100 / 100 | 93–96 / 96–100 / 100 |

En gras : les couvertures sous le seuil, fixé au niveau moins 10 points.

### Non-infériorité (δ = 0,05 nat par unité)

| variante | échecs (pays, maillage, moitié) | écart maximal |
|---|---|---|
| `multiscale_s050` | TZA H3 r4 (moitié 1) ; MWI H3 r6 (moitié 1, +0,074) | +0,45 |
| `laea50_s050` | TZA H3 r4 (moitié 1) ; TZA grille l4 (moitié 0, +0,09) | +0,47 |
| `district_s050` | 14 sur 16 | +0,56 |
| `laea50_s100` | 14 sur 16 | +0,51 |

**Gate A1b : non passé.** Aucune variante n'est admissible. Toutes ne tiennent la couverture qu'au Malawi, et toutes échouent à la non-infériorité au moins une fois.

## Lecture
1. **L'échec vient des maillages grossiers de la Tanzanie, et non du choix de la variante.**
   - Sur H3 r4, 138 districts sur 169 font moins de 4 cellules. Leur total prédit repose alors sur l'hypothèse d'une densité homogène dans la cellule : c'est un défaut de support (MAUP), qu'aucune variance du prior ne corrige.
   - Restreintes aux districts d'au moins 4 cellules, les variantes à σ = 0,5 couvrent à 95 % entre 81 et 97 %, y compris sur les maillages grossiers.
2. **Sur les maillages fins de la Tanzanie (H3 r5, grille l5)** :
   - les trois variantes à σ = 0,5 couvrent entre 89 et 92 % à 95 %, c'est-à-dire dans la tolérance ;
   - `multiscale_s050` et `laea50_s050` restent à moins de 0,04 nat de la meilleure candidate ;
   - le modèle en place couvre 96 %, mais il perd 0,18 à 0,32 nat.
3. **Le Malawi ne départage presque rien.**
   - Avec 3 marges et un bruit déclaré de 5 %, toutes les variantes sur-couvrent (100 % à 95 %).
   - Seule la non-infériorité y joue : `laea50_s050` et `multiscale_s050` sont en tête, et le modèle en place recule de 0,34 à 0,51 nat.
4. **Le biais de A1 se retrouve.** Le z moyen va de +0,00 à +0,17 : le total publié dépasse en moyenne la prédiction médiane.
5. **Constat commun au Ghana, à la Tanzanie et au Malawi.** Le modèle en place est prudent et n'est jamais en tête. Une erreur à σ = 0,5 avec structure spatiale (blocs de 50 km ou multi-échelles) fait mieux partout où le maillage résout les unités.
   - Ce constat est **descriptif**. Il ne vaut pas gate, puisque la règle déclarée échoue.

## Ce qu'on ne fait pas
- **Changer la règle et renoter ces données.** On pourrait exclure les maillages où la plupart des unités sont plus petites que 4 cellules, ou ne noter que la strate des districts d'au moins 4 cellules. Ce critère est suggéré par le résultat lui-même : il ne peut être déclaré que pour une **donnée nouvelle**.
- **Promouvoir `multiscale_s050` ou `laea50_s050`.** Ce serait la promotion après coup que le préenregistrement exclut.

## Réserves
- Les unités notées sont des **projections**, et non des recensements.
- Au Malawi, l'indépendance est plus faible : ses districts servaient de marges au run `mwi_population_2023`.
- Le bruit déclaré (5 et 10 %) élargit les intervalles prédits.
- La non-infériorité repose sur une estimation ponctuelle, bruitée pour les moitiés d'environ 14 districts du Malawi.
- Les maillages de la Tanzanie (H3 r4, grille l4) ont été déclarés pour un pays de 945 000 km², avant A1b, et non pour ce test.
