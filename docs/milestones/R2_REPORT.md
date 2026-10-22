# R0–R2 — Premières données réelles : Ghana (pilote), Zambie, Malawi, Tanzanie

*Statut : phase 1 (11), prototype de mesure de la population, sur données ouvertes seulement. **Le gate de la phase 1 n'est pas passé** : voir « Challenge ». Rien n'est publié. Décisions : [ADR-0028](../decisions/ADR-0028-donnees-reelles.md) ; cadrage : [données réelles](../CADRAGE_DONNEES_REELLES.md).*

## Fait

### R0 — Données sous licence nominative
`restricted/` est prêt à recevoir Afrobarometer R9 géocodé et DHS :
- hors Git et hors image ;
- monté en lecture seule dans `worker` et `cli` ;
- ACL limitée à l'uid du conteneur.

Une source restreinte ne peut lire qu'un chemin sous `/restricted/`, refus au schéma sinon. Le red-team vérifie le montage, les exclusions et les chemins.

### R1 — Unités administratives et totaux
- **Adapters `admin_boundaries` et `admin_table`** :
  - lecture des GeoJSON, éventuellement zippés ;
  - **licence de chaque frontière** geoBoundaries lue dans ses métadonnées et comparée à celle déclarée ;
  - jointure tableau-polygones **exhaustive dans les deux sens**.
- **Écarts de découpage déclarés dans les manifestes**, jamais devinés :
  - Tanzanie : alias (Coast → Pwani), fusion Mbeya + Songwe (les polygones datent de 2015, Songwe de 2016), regroupement des cinq régions de Zanzibar et Pemba ;
  - Malawi : quatre villes fusionnées dans leur district, suffixe « District » retiré.

### R2 — WorldPop en prior
- **Adapter `worldpop`** : une seule observation RASTER, de statut M. WorldPop ne peut pas être déclaré comme observation (rôle interdit, refusé à la résolution du run).
- **Prior `raster_lognormal_density`** : densité WorldPop par cellule, avec un plancher là où aucun bâti n'est détecté.
- **Étape `raster_prior`** : lecture par bandes, sha256 revérifié, masse hors maillage rapportée.
- **Mesure** : chaque tirage est recalé sur les totaux administratifs. Dépendances : rasterio 1.5 et `libexpat1`.

## Résultats

### Ghana 2021 (`gha_population_2021`) : recensement PHC 2021, 16 régions, statut D

| | |
|---|---|
| maillages | H3 r5 (1 341 cellules), H3 r6 (8 950), grille 12,5 km (1 649), grille 6,25 km (6 385) |
| durée, mémoire | 48 s ; pic 494 Mo, pour une limite de 768 Mo |
| total mesuré | 30,86 M [30,52 ; 31,19] (recensement : 30 832 019) |
| calculabilité par cellule | **D** sur les quatre maillages (ratio d'information médian 0,00) |
| information à 100 km | 0,80 à 0,82 (**B**) sur les quatre maillages |
| écart entre maillages (grille de référence de 100 km) | z max 0,49 |
| masse WorldPop hors limites COD-AB | 118 834 personnes (0,4 %) |

**WorldPop comparé au recensement, par région** : WorldPop 2021 compte **32,21 M, soit +4,5 %** par rapport au recensement. L'écart va de +0,6 % (Oti) à +5,8 % (Western North), et atteint **+10,9 % dans Savannah**. La répartition entre régions est donc très proche de celle du recensement, avec un biais de niveau quasi uniforme. Elle n'est pas indépendante pour autant (voir Challenge 2).

**Holdout** : Northern East et Central, prédites sans leur marge.

| maillage | couverture à 90 % | z moyen |
|---|---|---|
| H3 r5 | 2/2 | −1,40 |
| grille 12,5 km | 1/2 | −1,69 |
| grille 6,25 km | 0/2 | −2,51 |
| H3 r6 | 0/2 | −2,60 |

### Pays préparés : marges = projections, statut M

| run | unités | durée, pic mémoire | WorldPop / projection (total) | même rapport, par unité (min – médiane – max) | couverture du holdout, maillage grossier → fin |
|---|---|---|---|---|---|
| `mwi_population_2023` | 28 districts | 68 s | 1,052 | 0,73 – 1,05 – 1,12 | H3 7/7 → 3/7 ; grille 6/7 → 2/7 |
| `zmb_population_2020` | 10 provinces | 134 s, 582 Mo | 1,078 | 0,85 – 1,08 – 1,42 | H3 1/1 → 0/1 ; grille 0/1 → 0/1 |
| `tza_population_2020` | 26 marges (dont Zanzibar et Pemba regroupés) | 104 s, 552 Mo | 1,026 | 0,66 – 1,08 – 1,86 | H3 11/11 → 4/11 ; grille 7/11 → 3/11 |

## Challenge

1. **Le prior indépendant rend l'incertitude des agrégats dépendante du maillage.**
   - **Le mécanisme** : un total régional somme des cellules dont les erreurs a priori sont indépendantes. Son incertitude relative décroît donc comme 1/√n. Plus le maillage est fin, plus l'intervalle prédit est étroit, sans aucune information nouvelle.
   - **Ce qu'on observe** : sur les quatre pays, la couverture du holdout chute du maillage grossier au maillage fin.
   - **Pourquoi c'est faux** : les erreurs de WorldPop sont spatialement corrélées, et contiennent au moins un biais de niveau (+4,5 % au Ghana).
   - **Conséquence** : le gate de la phase 1, *posterior fields validés*, **n'est pas passé**. Le run conclut correctement `NOT_IDENTIFIABLE`, mais ses intervalles sous l'échelle des marges ne sont pas fiables.
   - **Correction à écrire** : un prior avec une composante commune de niveau et une corrélation spatiale. Elle ne doit pas être réglée sur ce holdout.
2. **Le holdout contre WorldPop n'est pas une validation indépendante.**
   - WorldPop ajuste ses totaux aux estimations des Nations unies, et ses covariables incluent des recensements.
   - L'accord régional à ±6 % au Ghana mesure donc en partie cette circularité.
   - Seules les enquêtes (DHS, Afrobarometer) apporteront une information locale indépendante.
3. **Unités plus petites qu'une cellule.** En Tanzanie, le recalage exact échouait sur les régions insulaires, et l'échec était signalé, pas avalé. Il fallait choisir entre :
   - affiner le maillage, ce qui pousse la mémoire à 697 Mo pour une limite de 768 Mo ;
   - ou regrouper ces régions en une seule marge.
   
   Le regroupement a été retenu, déclaré dans le manifeste.
4. **Projections et recensement ne se valent pas.** En Zambie, en Tanzanie et au Malawi, les marges sont des projections (M) et non des dénombrements. Les écarts à WorldPop vont jusqu'à +86 % pour une région tanzanienne et +42 % pour une province zambienne. Ce sont des désaccords entre deux modèles, pas des erreurs mesurées.
5. **Districts du Ghana.** Le jeu de districts du COD-PS est inutilisable : ancien découpage, sans pcode, total incomplet. Il a été écarté, pas réparé.

## Manquant
- **Prior corrélé** (Challenge 1) : condition pour passer le gate de la phase 1.
- **Données locales** :
  - les 261 districts du PHC 2021 ;
  - les recensements 2022 de la Zambie et de la Tanzanie ;
  - un adapter xlsx pour le recensement 2018 du Malawi ;
  - le taux de couverture des enquêtes post-censitaires (PES).
- **R3** : DHS et Afrobarometer R9, en attente d'accès ; composition ; exclusion de la zone de conflit du nord-est du Ghana.

## Tests
- **Unitaires** (`test_real_data_adapters.py`) :
  - polygones zippés ;
  - licence lue dans les métadonnées ;
  - jointure exhaustive, alias, fusions, suffixes, regroupement ;
  - statut M conservé ;
  - WorldPop en EPSG:4326 seulement ;
  - conservation de la masse du raster vers les cellules, pour trois tailles de bloc.
- **Intégration** (`test_real_population_run.py`) :
  - run complet au format réel sur un mini-jeu fictif, hors ligne ;
  - WorldPop refusé en observation ;
  - les quatre runs réels se résolvent.
- **Red-team** (`test_restricted_data.py`) : chemins hors `/restricted/` refusés ; montage, exclusions Git et Docker, aucun fichier suivi.
- **Suite complète** : 353 tests passés sur 354, plus 3 ignorés dans le conteneur, qui tournent en CI.
  - L'échec venait du test d'export de la carte : il vérifiait l'ancien message « aucun run sur données réelles ». L'assertion a été mise à jour, et le test, les tests des nouveaux modules et le smoke test repassent.
