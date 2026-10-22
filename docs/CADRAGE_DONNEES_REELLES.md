# Cadrage — passage aux données réelles

*Statut : **décisions en partie prises**, mise à jour du 2026-10-22. Région : Ghana ; rasterio accepté ; stockage `restricted/` accepté (voir [ADR-0028](decisions/ADR-0028-donnees-reelles.md)). Afrobarometer R9 géocodé demandé par le porteur (délai annoncé : deux semaines) ; demande DHS non encore confirmée. Restent ouvertes : le comité de gouvernance (décision 4) et les licences à partage à l'identique (décision 6). Lots R0 à R2 réalisés ([rapport](milestones/R2_REPORT.md)).*

## 1. Où en est le projet

- **Ce qui est fait.** Les milestones M0 à M15 ont construit et testé toute la chaîne, mais **sur des mondes synthétiques seulement**, placés en plein Atlantique Sud. Le seul jeu de données réel ingéré est le fond de carte Natural Earth.
- **Ce que montre la carte publique.**
  - Aujourd'hui : des pays, des maillages, et une couche candidats vide.
  - Ce qu'elle ne montrera pas : un découpage. Passer aux données réelles ne change pas cela à court terme.
- **Ce que la spec impose comme suite (11, phase 1).**
  - Le premier usage de données réelles est un **prototype de mesure régional**, sur « une région à données relativement riches ».
  - Contenu : ingestion, maillage, population, langues, identité, incertitude.
  - **Pas d'optimisation politique publique.**
  - Gate : *posterior fields validés*.
- **Ce qui ne repart pas de zéro.** Les phases 2 à 11 ont été validées sur synthétique ; elles ne sont pas refaites. Mais elles ne seront ré-appliquées à la région réelle que si le gate de la phase 1 passe, puis phase par phase, chacune avec son propre gate.

**Cible de ce cadrage** : une région pilote réelle, la population et la composition mesurées avec leur incertitude, validées, et classées par calculabilité (03 §32). Ce cadrage ne vise rien au-delà.

## 2. Ce qui ne change pas

Toute la doctrine reste en vigueur, et les données réelles la rendent plus contraignante, pas moins :

- **Les données sont des instruments.** Le schéma reste observations → modèle de mesure → champs latents → incertitude (03 §1). Aucune source n'est « la vraie carte ethnique ».
- **Composition** :
  - parts seulement, jamais d'étiquette ;
  - champs de groupe en CONTROLLED au minimum, **jamais publiés** ;
  - aucune géométrie calculée à partir des parts de groupes ne sort.
- **Inconnu** : UNKNOWN n'est jamais 0 ; une absence de données n'est jamais neutre (03 §26) ; on préfère « inconnu » à une précision fictive (03 §34).
- **Consentement et coercition** : aucun consentement n'est inféré (03 §23) ; on stocke PREF, pas CONSENT. Aucun déplacement de population n'est modélisé comme levier.
- **Conclusion** : NO TERRITORIAL CHANGE / NOT_IDENTIFIABLE reste toujours une conclusion possible, et c'est la plus probable au début.

## 3. Choix de la région pilote

### Critères (11, « choix du premier pilote »)
Il faut :
- de bonnes enquêtes ;
- un recensement exploitable ;
- une diversité suffisante ;
- pas de conflit aigu qui rendrait la publication dangereuse ;
- une variation institutionnelle.

La spec ajoute : le pilote ne doit pas être choisi « parce qu'il semble politiquement intéressant ».

S'y ajoutent deux critères pratiques :
- les enquêtes contiennent la **langue et l'ethnie** (DHS récentes avec ces modules) ;
- le recensement est publié en **tableaux par unité administrative** (au minimum admin-2).

### Options

| option | pour | contre / risque |
|---|---|---|
| **A. Ghana** (pays entier, ou un groupe de régions) | recensement 2021 ; DHS 2022 ; Afrobarometer ; forte diversité linguistique ; variation institutionnelle (régions recréées en 2018, district assemblies) | conflit localisé et prolongé dans le nord-est (Bawku) : la zone concernée doit être exclue ou traitée en SENSITIVE ; la recomposition de 2018 sert de variation, pas de motif de choix |
| **B. Zambie + Malawi** (bande frontalière Est / Centre-Nord) | expérience naturelle classique de la bibliographie (Posner 2004, Chewa / Tumbuka) ; deux systèmes institutionnels sur des populations proches ; DHS et Afrobarometer des deux côtés | deux recensements à harmoniser (03 §29), deux ontologies nationales des catégories : beaucoup plus de travail pour un *premier* pilote ; c'est plutôt un candidat pour la phase 8 ou pour la bibliothèque causale |
| **C. Tanzanie** | type « intégrée nationalement » (11, phase 8) ; recensement 2022, DHS 2022 | le recensement ne collecte pas l'ethnie : la composition reposerait sur les enquêtes seulement. Utile comme contraste, mauvais premier pilote |

**Recommandation : A (Ghana)**, sans la zone de conflit du nord-est, avec une revue de sécurité avant toute publication. Ce n'est qu'une recommandation de faisabilité ; **le choix revient au porteur du projet et, idéalement, à un spécialiste régional (06 §6)**.

Tous les faits ci-dessus sur les recensements et les enquêtes sont à vérifier pièce par pièce au moment d'écrire chaque manifeste de source.

## 4. Sources : rôles, zones et accès

Chaque source reçoit un `SourceManifest` (rôles autorisés et interdits, zone, licence, sha256). Ce mécanisme existe déjà ; il refuse :
- une source restreinte récupérée par http ;
- une zone ouverte sous licence non redistribuable ;
- une source historique sans contexte.

| source | rôle autorisé (proposé) | rôle interdit | zone / accès | licence (à confirmer dans le manifeste) | support |
|---|---|---|---|---|---|
| geoBoundaries gbOpen, admin-1/2 | `status_quo_geometry`, `analysis_extent` | `legal_boundary_truth` | OPEN_CORE, http | **par frontière** : CC BY, ODbL, CC BY-SA… selon les métadonnées. ODbL et BY-SA imposent le partage à l'identique | POLYGON |
| Tableaux du recensement (institut statistique national) | `population_measurement` (totaux, `use: margin`), `causal_transport_target` | `group_territory_inference` | dépend de la licence nationale : OPEN_CORE si redistribuable, sinon RESTRICTED_LOCAL | à lire sur la publication | ADMIN |
| WorldPop (contraint, 100 m) | **prior** de densité P^prior (03 §5) | `population_measurement` (c'est un produit M, pas une observation), toute inférence d'identité | OPEN_CORE, http | CC BY 4.0 (ODbL pour les produits dérivés d'OSM ou des emprises Microsoft) | RASTER |
| GHSL | morphologie urbaine, définition des métropoles (03 §15) | population directe | OPEN_CORE, http | CC BY 4.0 (à confirmer) | RASTER |
| DHS (ménages et individus, GPS) | `population_measurement`, `composition_measurement` (langue, ethnie, religion si présentes) | toute localisation fine, tout point-in-polygon naïf (03 §6) | **RESTRICTED_LOCAL**, accès sur demande nominative, pas de redistribution | conditions DHS | UNCERTAIN_POINT |
| Afrobarometer (non géocodé) | identité nationale et ethnique, confiance, préférences (PREF, pas CONSENT), à l'échelle admin-1 | surface fine (03 §22) | à décider selon la politique d'usage (données protégées par le droit d'auteur) ; par défaut RESTRICTED_LOCAL | conditions Afrobarometer | ADMIN |
| Afrobarometer géocodé (AidData) | idem, avec un support plus fin | idem | **RESTRICTED_LOCAL**, accès sur demande avec engagement personnel de sécurité | conditions Afrobarometer | UNCERTAIN_POINT |
| GREG ; carte Murdock numérisée | `ontology_validation` (instrument historique, statut H) | toute vérité de groupe ou de territoire ; jamais fusionnées entre elles (03 §9) | à décider selon les licences | à confirmer | POLYGON, avec `historical_context` obligatoire (01 §29) |
| EPR / GeoEPR | pertinence politique des groupes, accès à l'exécutif | frontière ethnique définitive | à décider (licence non confirmée) | à confirmer | POLYGON, NATIONAL |
| UCDP GED | validation, stress-test, **choix des zones à exclure** | `identity_primitive` (03 §11) | OPEN_CORE | CC BY 4.0 (à confirmer) | POINT |
| Glottolog | identifiants et généalogie des langues (crosswalks) | population locutrice | OPEN_CORE | CC BY 4.0 (à confirmer) | — |

Sources écartées pour ce pilote :
- **GADM** : non redistribuable, et le noyau ouvert doit pouvoir s'en passer (03 §33).
- **ACLED** : licence restrictive.
- **Ethnologue** : licencié, donc pas indispensable.
- **Données télécom** : SENSITIVE, hors périmètre.

Règle de 03 §33, appliquée telle quelle : **le pipeline public (CI, Pages) tourne sans aucune source restreinte**. Les sources restreintes améliorent le postérieur sur le VPS ; elles ne deviennent jamais une dépendance du noyau.

## 5. Données restreintes sur ce VPS

**Ce qui ne bouge pas** : la CI publique n'a jamais accès à ces fichiers, et aucun run qui en contient ne peut être exporté vers Pages (le privacy guard le refuse déjà au-dessus de PUBLIC).

**Ce qui reste à décider : où déposer les fichiers.** Proposition :
- **Dépôt** :
  - un répertoire `restricted/` à la racine du projet ;
  - ignoré par git **et** par Docker (`.gitignore`, `.dockerignore`), en mode 0700 ;
  - monté **en lecture seule** sur `/restricted` dans `worker` et `cli` ;
  - le montage reste dans le projet, donc autorisé par appctl.
- **Ce qui va dans le dépôt** : les manifestes de ces sources (chemin et sha256). L'empreinte d'un fichier ne révèle pas son contenu.
- **Qui dépose** : le titulaire de l'accès (DHS, Afrobarometer géocodé), lui-même. Ces accès sont **nominatifs** : je ne peux pas, et je ne dois pas, en faire la demande.
- **Sauvegardes** : vérifier que la politique de sauvegarde du VPS est compatible avec les conditions de licence, notamment sur la copie hors site.

**Règle pour moi (Claude) :**
- je ne lis **jamais** le contenu des microdonnées restreintes dans la conversation : ni `cat`, ni `head`, ni échantillon de lignes ;
- ce serait les envoyer à un service tiers, ce que les conditions d'usage interdisent, et CLAUDE.md l'interdit pour les secrets ;
- je travaille sur les **dictionnaires de variables publiés**, sur des fixtures synthétiques qui ont le même schéma, et sur des contrôles qui ne renvoient que des agrégats non sensibles (comptes de lignes, schémas, taux de valeurs manquantes) ;
- **les logs suivent la même règle** : ils sont déjà en liste blanche de champs.

## 6. Travail technique

### 6.1 Adapters
Par ordre de dépendance :
1. **`geoboundaries`** :
   - polygones admin ;
   - lecture de la licence **dans les métadonnées de chaque frontière**, avec refus si elle diffère de celle du manifeste.
2. **`census_tables`** :
   - un CSV transcrit à partir des tableaux publiés, une ligne par unité administrative ;
   - la transcription est elle-même une provenance : document source, page, tableau, date, sha256 du PDF ;
   - statut D pour les totaux.
3. **`worldpop`** :
   - un raster GeoTIFF découpé à l'emprise ;
   - il entre comme **prior** du modèle de mesure, pas comme vraisemblance.
4. **`dhs`** :
   - fichiers ménages et individus, plus le fichier GPS ;
   - le déplacement des grappes est modélisé : jusqu'à 2 km en urbain, 5 km en rural, 10 km pour 1 % des grappes rurales, contraint à une limite administrative dont le niveau dépend de l'enquête et doit être lu dans la documentation de chaque vague ;
   - les poids de sondage sont conservés ;
   - pour les catégories d'ethnie et de langue, ce sont les **codes du questionnaire** qui deviennent l'ontologie observée.
5. **`afrobarometer`** : à admin-1, sauf si l'accès géocodé est obtenu.
6. **`greg`, `murdock`, `geoepr`** : contexte historique et validation de l'ontologie, plus tard dans la phase.

### 6.2 Raster (nouveau)
Le type RASTER existe dans les enums, mais aucun code ne le lit : rasterio a été reporté par l'ADR-0002. Il faut :
- **une dépendance** : rasterio, avec ses wheels qui embarquent GDAL. L'image grossit d'environ 30 à 60 Mo ;
- **une agrégation par cellule** : somme et couverture du raster sur chaque cellule de maillage, en lecture par fenêtres. La limite mémoire du worker (768 Mo) interdit de charger un pays à 100 m d'un bloc ;
- **un modèle de mesure** dont le prior log-normal indépendant devient centré sur le raster, avec une dispersion à déclarer (paramètre de modèle PROVISOIRE, sensibilité rapportée).

### 6.3 Mesure
- **Vraisemblance DHS** : une nouvelle variante de `ea_count_density` qui intègre le noyau de déplacement, au lieu du disque générique du synthétique.
- **Modèle de manquants** (03 §26) : la couverture des enquêtes et l'exclusion de la zone de conflit sont des manquants **informatifs**, déclarés comme tels. Ces zones tombent en classe de calculabilité D, au lieu d'être interpolées.
- **Harmonisation temporelle** (03 §29) : d'abord, l'**année de référence est celle du recensement** (2021 pour l'option A) ; la DHS et WorldPop y sont rapportés avec une incertitude déclarée. Aucune projection vers 2026 dans ce pilote.
- **Invariance de mesure** (03 §28) : pour un pilote dans un seul pays, on compare les vagues et les langues de passation. Sur plusieurs pays (option B), elle devient bloquante.

### 6.4 Ontologies et crosswalks
- **Une ontologie par instrument** : codes ethnie et langue de la DHS, catégories du recensement, catégories d'Afrobarometer. Glottolog sert de pivot pour les langues, sans fusion autoritaire.
- **Crosswalks déclarés** : partiels et incertains, avec la mention UNKNOWN là où une catégorie ne se projette pas.
- **Relecture** : ce travail demande un spécialiste régional (06 §6). Je peux le préparer, pas le valider.

### 6.5 Volume et calcul
- **Disque** : environ 51 Go libres sur le VPS. Un pays en raster 100 m (WorldPop plus GHSL) occupe de quelques centaines de Mo à quelques Go. Ça passe.
- **Mémoire** : la contrainte est la RAM du worker, pas le disque. L'agrégation raster doit être découpée en étapes de file reprenables (ADR-0012), comme les autres.

## 7. Validation : le gate de la phase 1

Les champs postérieurs sont validés si **tout** ce qui suit passe :

1. **Holdout du recensement** :
   - estimation sans une fraction des unités admin-2, puis prédiction de ces unités ;
   - critère : z des résidus standardisés, comme le Gate H de M15 ; c'est le critère prévu, pas un critère réglé après coup.
2. **Ablation des sources** :
   - retirer chaque source tour à tour ;
   - aucune conclusion majeure ne doit dépendre d'une seule source (A4).
3. **Stabilité multi-échelle** : stabilité sur les deux familles de maillage et les deux résolutions (A3).
4. **Calculabilité** :
   - une carte des classes A à D par unité, avec la part de la population pilote en D ;
   - **elle est publiée telle quelle**, même si elle est mauvaise (03 §32).
5. **Composition** :
   - couverture des intervalles en validation croisée par grappes DHS ;
   - accord ou désaccord avec l'ontologie historique, rapporté comme tel, sans arbitrage.

**Si le gate échoue**, le pilote s'arrête là et le rapport le dit : c'est un résultat (11, stop conditions). On ne passe pas à D/F/I réel.

## 8. Gouvernance et publication

- **Calculer n'est pas publier.** Les runs réels tournent sur le VPS, et leurs sorties sont en CONTROLLED par défaut.
- **Avant toute publication qui dépasse ce que la carte montre déjà**, il faut :
  - un **comité**, au minimum un statisticien, un spécialiste régional et une personne privacy/sécurité (06 §6) ;
  - un **modèle de menace révisé** pour la région réelle (`threat_model.md`), en particulier :
    - le seuil k ;
    - la liste des proxies sensibles ;
    - la différenciation entre supports emboîtés, encore traitée de façon conservatrice ;
  - un **canal de recours** (06 §13) : contester des données, signaler une classification, proposer des sources ;
  - un **kill switch** documenté (06 §17).
- **Ce qui pourrait devenir PUBLIC dans ce pilote** :
  - la **carte de calculabilité** par unité admin, qui ne contient ni population ni groupe ;
  - la population **agrégée** à admin-2, avec ses intervalles, si les licences le permettent.
  - Rien sur les groupes.
- **La couche candidats reste vide**, et son message reste calculé (pages_map). Le texte « aucun run sur données réelles » changera pour dire où en est le pilote réel.

## 9. Découpage proposé

| lot | contenu | gate de sortie |
|---|---|---|
| R0 | ADR, `restricted/` (montage ro), choix de la région, demandes d'accès DHS et Afrobarometer **par le porteur** | décisions du §10 prises |
| R1 | geoBoundaries et recensement : status quo admin et totaux, maillages réels | totaux conservés entre maillages ; licence par frontière vérifiée |
| R2 | rasterio, WorldPop en prior, agrégation fenêtrée | ressources du worker tenues ; étapes reprenables |
| R3 | DHS : noyau de déplacement, poids, composition par instrument | fixtures synthétiques au schéma DHS ; zéro lecture de microdonnées dans la conversation |
| R4 | validation du §7, classes de calculabilité, rapport | gate de la phase 1 |
| R5 | (si le comité existe) publication de la carte de calculabilité | revue du comité |

Les lots R1 et R2 ne touchent que des données ouvertes : ils peuvent avancer **avant** que les accès restreints soient obtenus. Les demandes DHS ou Afrobarometer prennent de quelques jours à quelques semaines.

## 10. Décisions attendues

1. **Région pilote** : A (Ghana, recommandée), B, C, ou une autre ; et qui la relit côté spécialiste régional.
2. **Données restreintes** : est-ce que tu demandes les accès DHS et Afrobarometer (géocodé ou non) ? Sinon, le pilote reste ouvert (recensement et WorldPop) et la composition est déclarée NOT_IDENTIFIABLE.
3. **Stockage** : `restricted/` dans le projet, monté en ro, convient-il ? Compatibilité des sauvegardes du VPS avec les licences.
4. **Comité de gouvernance** : existe-t-il, ou doit-il être constitué ? Sans lui, rien de réel ne sort au-delà des maillages.
5. **Rasterio dans l'image** : la reprise de la dépendance reportée par l'ADR-0002 est-elle acceptée ?
6. **Licences ShareAlike** (ODbL, CC BY-SA) : sont-elles acceptables pour les couches dérivées publiées ? Sinon, les frontières sous ces licences restent internes.
