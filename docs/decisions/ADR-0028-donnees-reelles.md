# ADR-0028 — Données réelles : pilote Ghana, données restreintes, WorldPop en prior (lots R0–R2)

*Statut : accepté — 2026-10-22. Décisions du [cadrage](../CADRAGE_DONNEES_REELLES.md) prises par le porteur du projet : Ghana, rasterio, `restricted/`.*

## Contexte
- **Où en est le projet** : jusqu'ici, tout tournait sur des mondes synthétiques.
- **Phase 1 (11)** : un prototype de mesure régional, sans optimisation politique. Gate : *posterior fields validés*.
- **Ce qu'impose la spec 03** :
  - WorldPop ne remplace pas un recensement (§5) ;
  - les données manquantes ne sont jamais neutres (§26) ;
  - le noyau public doit tourner sans données propriétaires (§33).
- **Demandes d'accès** : Afrobarometer R9 géocodé est demandé par le porteur du projet (délai annoncé : deux semaines) ; la demande DHS n'est pas encore confirmée. Ce lot n'utilise donc **que des données ouvertes**.

## Décision

### R0 — Données sous licence nominative
- **Où elles vivent** : `restricted/`, à la racine du projet.
  - Ignoré par Git et par Docker ; seul son README est versionné.
  - Monté **en lecture seule** sur `/restricted` dans `worker` et `cli`.
  - Sur l'hôte : mode 2750, ACL en lecture pour l'utilisateur du conteneur (uid 10001), défaut hérité ; aucun accès pour les autres utilisateurs.
- **Au schéma** : une source `RESTRICTED_LOCAL` ou `SENSITIVE` ne peut lire qu'un chemin absolu sous `/restricted/`. Un chemin relatif, un `..`, `/state` ou le dépôt sont refusés.
- **Red-team** (`test_restricted_data.py`) :
  - le montage est en lecture seule dans `worker` et `cli`, et absent de `db` et `gh` ;
  - le répertoire est bien ignoré par Git et par Docker ;
  - rien d'autre que le README n'est suivi dans `restricted/`.
- **Règle de conduite** : leur contenu n'est jamais affiché, ni dans une conversation, ni dans un log, ni dans un rapport.

### R1 — Unités administratives et totaux
- **Deux adapters génériques** (`data/adapters/admin.py`) :
  - `admin_boundaries` : polygones GeoJSON, éventuellement zippés ;
  - `admin_table` : un total par unité, joint aux polygones.
- **Jointure exhaustive dans les deux sens** :
  - une unité sans total ou une ligne sans polygone est une erreur ;
  - les écarts de découpage sont **déclarés** dans le manifeste (alias, fusions, suffixes de nommage), jamais devinés.
- **Licence par frontière** : geoBoundaries gbOpen mélange plusieurs licences. Celle de la frontière est donc lue dans ses métadonnées et comparée à celle déclarée par le manifeste, faute de quoi l'ingestion échoue (`DataLicenseError`).
- **Statut de preuve** : celui du manifeste, sans promotion. D pour un recensement, M pour une projection.

### R2 — WorldPop en prior, jamais en observation
- **Adapter** : `worldpop` produit **une** observation RASTER de statut M, qui référence le fichier épinglé (`nom@sha256`). Un WorldPop déclaré comme observation est refusé :
  - son manifeste interdit le rôle `population_measurement` ;
  - le run exige le rôle `population_prior` ;
  - une même source ne peut pas être à la fois prior et vraisemblance.
- **Prior** `raster_lognormal_density` : log ρ_i ~ N(log ρ̂_i, σ²), où ρ̂_i est la densité WorldPop agrégée à la cellule.
  - Une cellule sans bâti détecté reçoit un **plancher**, pas zéro : l'absence de détection n'est pas une absence prouvée.
- **Étape `raster_prior:<maillage>`** :
  - le raster est relu depuis le cache et son sha256 revérifié ;
  - lecture par bandes, somme par blocs de `block_pixels` ;
  - chaque bloc est affecté à la cellule qui contient son centre, en LAEA ;
  - la masse hors maillage est rapportée, jamais redistribuée ;
  - la mémoire est bornée quel que soit le pays.
- **Mesure** : chaque tirage est recalé sur les totaux administratifs (marges), eux-mêmes tirés selon leur erreur déclarée. C'est le mécanisme de désagrégation existant (ADR-0013) ; seul le prior change.
- **Dépendances** : rasterio 1.5 (wheels avec GDAL embarqué), plus `libexpat1` dans l'image slim.

### Sources retenues

| pays | limites | totaux (marges) | statut des totaux | WorldPop |
|---|---|---|---|---|
| **Ghana** (pilote) | COD-AB (GSS / OCHA), 16 régions, CC BY-IGO | COD-PS 2021, **recensement PHC 2021**, 16 régions (somme = 30 832 019) | **D** | 2021, R2025A |
| Zambie (préparée) | geoBoundaries ADM1, 10 provinces, CC BY 4.0 | COD-PS 2020, projection depuis 2010 | M | 2020 |
| Tanzanie (préparée) | geoBoundaries ADM1 (OSM 2015), 30 régions, **ODbL** | COD-PS 2020, projection depuis 2012 ; Mbeya + Songwe fusionnées | M | 2020 |
| Malawi (préparé) | geoBoundaries ADM2, 28 districts, CC BY 3.0 IGO | COD-PS 2023, projection depuis 2018 ; les 4 villes fusionnées dans leur district | M | 2023 |

**Écartés, et pourquoi** :
- **Districts du Ghana du COD-PS** : 216 lignes selon l'ancien découpage, sans pcode, total incomplet. Les 261 districts du PHC 2021 ne sont publiés qu'en PDF, ou en microdonnées sur demande.
- **Recensements 2022 de la Zambie et de la Tanzanie** : non trouvés sous une forme lisible par machine.
- **Tableaux du recensement 2018 du Malawi** : publiés en xlsx sur HDX. Il manque l'adapter.
- **GADM** : licence non redistribuable.

## Ce qui ne change pas
- **Aucune** composition, D/F/I, candidat ni optimisation sur données réelles. Les runs réels déclarent `NOT_IDENTIFIABLE`.
- **Pages** : rien n'est publié. La carte reste pays et maillages ; la couche candidats reste vide.
- **ODbL** (Tanzanie) : couche interne. Aucune couche dérivée n'est publiée sans décision sur le partage à l'identique (cadrage, décision 6, ouverte).

## Limites déclarées
- **Circularité de WorldPop** : ses totaux sont ajustés aux estimations des Nations unies, et ses covariables incluent des données de recensement. Un holdout des régions contre WorldPop n'est donc **pas** une validation indépendante.
- **Prior indépendant par cellule** : les erreurs de WorldPop sont spatialement corrélées, et un prior indépendant sous-estime l'incertitude des agrégats. Le holdout le mesure ; il ne le corrige pas.
- **Couverture** : avec 16 marges et aucune enquête, l'information sous l'échelle régionale vient du seul prior. La calculabilité par cellule le dit.
- **Paramètres provisoires** : `log_sd`, le plancher, l'erreur relative des totaux. L'erreur du recensement attend le taux de couverture de l'enquête post-censitaire (PES) du PHC 2021.
- **Zone du nord-est** : l'exclusion annoncée par le cadrage s'appliquera à la **composition** (lot R3). La population seule, en CONTROLLED, ne localise aucun groupe.

## Conséquences
Voir le rapport [R1–R2](../milestones/R2_REPORT.md) pour les résultats du run `gha_population_2021`.

## Révision R2b — 2026-10-22 : centrage et corrélation du prior
- **Erreur corrigée** : la première version centrait la **médiane** du prior sur WorldPop. WorldPop estime une espérance, ce qui gonflait chaque cellule de e^(σ²/2) ≈ 1,65. Désormais μ_i = log ρ̂_i − σ²/2.
- **Erreur corrélée, optionnelle et déclarée** (`correlation`) : un niveau commun, des blocs LAEA de taille fixe et un terme propre à la cellule. L'estimation se fait dans l'espace des facteurs latents (x = μ + M·z). Sans corrélation déclarée, M est l'identité et le comportement est inchangé.
- **Variance a priori des agrégats** (information selon l'échelle) : sous prior corrélé, elle est calculée par tirages, et non comme une somme de variances.
- **Résultat** : couverture complète du holdout régional dans les quatre pays, quel que soit le maillage. Les intervalles sont prudents (rms z de 0,02 à 0,42).
- **Attribution** : l'ablation montre que le centrage seul suffit à rétablir la couverture. La corrélation est retenue pour une raison théorique : l'incertitude des agrégats ne doit pas dépendre de la finesse du maillage (test `test_correlated_prior.py`). Les données ne permettent pas de trancher. Le détail est dans le [rapport](../milestones/R2_REPORT.md), section R2b et Challenge 1.
