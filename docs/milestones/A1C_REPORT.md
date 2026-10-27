# A1c — Troisième test du modèle spatial de population (Kenya, recensement 2019)

*Statut : test préenregistré dans l'[ADR-0029 § 7](../decisions/ADR-0029-elg-seg-gates-feuille-de-route.md) (commit `e2efb1b`), avant toute lecture des totaux kényans. Le test est **évaluable**, mais le **gate A1c n'est pas passé**, et cela se joue à 0,003 nat. Selon les conséquences fixées d'avance : le modèle en place reste, aucun autre tour n'est fait sur les comtés kényans, et la suite d'A2 revient au porteur. Rien n'est publié.*

## Fait
- **Run** : `e3470ee6…`, exécuté par le worker.
- **Unités notées** : 46 comtés du recensement 2019 (KNBS, via COD-PS, CC BY-IGO).
  - Il s'agit de dénombrements, et non de projections.
  - Nairobi (KE047) est exclu, parce que ce comté est identique à une marge.
  - Les polygones viennent de COD-AB ADM1, joints par code.
- **Marges** : 8 anciennes provinces.
  - Chacune est la somme de ses comtés, sur leurs polygones regroupés.
  - L'appartenance comté → province vient du fichier de sous-comtés de l'American Red Cross (CC BY).
- **Prior** : WorldPop R2025A, Kenya 2019. **Maillages** : H3 r5 et r6, grilles l5 et l6.
- **Code** :
  - gate `a1c`, pour un seul pays : seules les unités d'au moins 4 cellules sont notées, avec un seuil de maillage et un contrôle de circularité ;
  - exclusion d'unités déclarée (`exclude_units`) ;
  - erreur du raster seul conservée par unité.

## Résultats (agrégats seulement)
- **Les quatre maillages sont retenus.** Les unités notées représentent 93 à 100 % de l'ensemble, au-dessus du seuil déclaré de 75 %.
- **Pas de circularité** : l'erreur log médiane du raster seul, recalé sur les provinces, vaut **0,062**, au-dessus du seuil de 0,02. WorldPop ne reproduit donc pas les comtés du recensement. Il en est proche : les erreurs vont de 5 à 7 % en médiane et de 14 à 22 % au 90ᵉ centile.

| variante | écart max. à la meilleure (δ = 0,05) | où | couverture tenue (4 maillages) | score log moyen | admissible |
|---|---|---|---|---|---|
| `multiscale_s050` | **+0,053** | grille l5, moitié 1 | oui | −0,515 | non |
| `laea50_s050` | **+0,063** | H3 r5, moitié 1 | oui | −0,522 | non |
| `district_s050` | +0,408 | 7 dépassements sur 8 | oui | −0,318 | non |
| `laea50_s100` (en place) | +0,410 | 8 sur 8 | oui | −0,259 | non |

- **Couverture à 95 % : 93 à 100 % pour toutes les variantes.** Toutes sur-couvrent à 80 et 95 %. À 50 %, `laea50_s050` et `multiscale_s050` couvrent 67 à 78 %, `district_s050` 76 à 93 %.
- **Toutes les variantes échouent à la non-infériorité.** Les deux variantes de tête sont `multiscale_s050` et `laea50_s050`. Chacune passe en tête sur une moitié et dépasse δ de 0,003 et 0,013 nat sur l'autre, à chaque fois sur un seul maillage et une seule moitié, d'environ 23 comtés.
- **Biais habituel** : le z moyen va de +0,05 à +0,18.

**Gate A1c : non passé** (aucune variante admissible).

## Lecture
1. **Cet échec est un quasi-ex æquo entre les deux variantes de tête, et non une mauvaise calibration.** C'est la réserve déclarée dans le préenregistrement : le critère est ponctuel, sur environ 23 unités par moitié. Le seuil de δ a été fixé avant le run. Le relever maintenant reviendrait à changer la règle après avoir vu le résultat : je ne le fais pas.
2. **Le constat descriptif de quatre pays (Ghana, Tanzanie, Malawi, Kenya) est désormais très régulier, sans valoir gate.**
   - Le modèle en place (`laea50_s100`) est prudent : il ne sous-couvre jamais là où le maillage résout les unités. Il perd pourtant de 0,1 à 0,5 nat face aux variantes à σ = 0,5 avec structure spatiale.
   - `multiscale_s050` et `laea50_s050` sont en tête ou presque partout, sans surconfiance sur les maillages fins.
3. **Ce que le gate ne peut pas trancher.** Le choix entre les deux variantes de tête est de l'ordre du bruit d'échantillonnage. Une règle exigeant qu'une variante domine **partout** à 0,05 près échoue donc mécaniquement quand deux variantes sont équivalentes.

## Ce qu'on ne fait pas
- **Relever δ et renoter le Kenya.** Ce serait changer la règle après avoir vu le résultat.
- **Promouvoir une variante.** Le gate n'est pas passé.

## Réserves
- 46 unités seulement ; les comtés sont grands, et le test ne dit rien sous l'échelle du comté.
- Le bruit déclaré est de 2 %, provisoire.
- Une circularité partielle de WorldPop reste possible : l'erreur médiane de 6 % est faible, mais au-dessus du seuil.
