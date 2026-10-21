# M14 — Coordination continentale

## Fait

### Composition, sans solve monolithique ([ADR-0026](../decisions/ADR-0026-continental-coordination.md))
- Une requête `kind: continental` nomme des runs régionaux Map-R et un modèle de coordination.
- Les régions sont soumises comme des runs ordinaires, avant la composition. Le worker suit l'ordre de soumission, et une région en échec fait échouer la composition avec son message.
- Étapes : `regional_check` → `interfaces` → `regional_options` → `coordination` → `report`.
- Aucune étape ne génère ni n'évalue de partition. Une option continentale est un tuple : une trajectoire Map-R par région, un ensemble de couches par interface.
- Aucune frontière ne traverse une interface.

### Commensurabilité et double comptage
Le manifeste est refusé dans deux cas :
- les régions diffèrent sur le manifeste normatif, le régime, l'optimiseur, le modèle de transition, le noyau de liens, les ontologies, les familles de maillage ou les ε ;
- deux régions partagent un contexte, ou leurs emprises se recouvrent.

### Interfaces
- **Liens** : les liens fonctionnels qui traversent chaque interface sont calculés avec le noyau des régions (quadrature par paire de cellules), sur chaque paire de maillages appariés.
- **Totaux** : population et poids total des liens de chaque région.
- **Coût** : le coût de gestion de la frontière d'interface est invisible au niveau régional ; il est compté ici.

### Couches de coordination (11 phase 10)
- Les couches : marché, mobilité, corridor (bande de 25 km) et sécurité (coût de frontière).
- **Bassin** : refusé sans hydrographie ingérée.
- **Coût** : chaque couche a un coût annuel déclaré, strictement positif.
- **Effet** : il vient d'une bibliothèque continentale gelée. Ce sont des hypothèses déclarées I7, avec une borne basse nulle, et aucune estimation n'est admise sans panel continental.
- **Archive** : chaque couche est une étape d'affaiblissement de frontière (§79), pénalisée selon 02 §26, et évaluée à la borne robuste.

### Agrégation, archive, exactitude
- **Agrégation** :
  - maximum pour J_D, J_V, J_reif ;
  - moyennes pondérées par la population pour J_F, J_conn, J_T ;
  - coupe fonctionnelle continentale pour J_G ;
  - sommes pour J_inst (avec les interfaces et les couches), J_pkg, J_path ;
  - J_R et J_P inconnus, avec l'axiome de fusion appliqué aux relations composées.
- **Élagage** : fronts régionaux × fronts de couches.
- **Contrôle** : deux énumérations exhaustives vérifient les deux élagages (07 §14). Une option manquée est réintégrée et l'archive reconstruite.
- **Produit** : conclusion, catégorie (la moins publiable des régions), régimes de conclusion de 09 §14 par région et par interface, priorités de recherche (borne haute), formulation conditionnelle. Aucune géométrie.

### Base
- **Migration 0014** : `continental_compositions`, `continental_regions`, rattachée aux manifestes régionaux.
- **Migration 0015** : provenance rattachée à la composition (`continental_run_id`), exclusive de `run_id`.

### Région synthétique Est
- Monde adjacent à l'ouest le long de 21° O : autre graine, 20 bourgs, autre composition de fond.
- Six instruments, mesure, composition, statu quo, D/F/I, viabilité, bibliothèque causale propre (hypothèses déclarées pour ce contexte, jamais transportées), candidats.
- Même chaîne Map-R que le smoke.

## Résultats (`synthetic_continental`, run worker `4d979c29…` ; régimes de conclusion recalculés avec le code final)
**Conclusion : STATUS_QUO_NOT_DOMINATED.** Catégorie NOT_IDENTIFIABLE : les deux régions ont M FAILED et R NOT_EVALUABLE.

**Les régions**
- Ouest : 6 trajectoires au front sur 19.
- Est : 8 sur 21.
- Chacune conclut STATUS_QUO_NOT_DOMINATED.

**L'interface ouest–est**
- 467 km de frontière ; son coût de gestion (23,4 M) est compté au niveau continental.
- 1 895 liens inter-régionaux, soit 2,0 % (maille 25 km) et 1,6 % (maille 12,5 km) des liens fonctionnels.

**Les couches**
- Borne robuste : aucune n'entre au front ; une couche n'y ajoute que du coût.
- Borne haute : **mobilité, sécurité et mobilité + sécurité** entreraient au front. C'est ce qu'il faudrait mesurer.

**L'archive et son contrôle**
- 48 options composées, front de 34 compromis. Le statu quo composé est au rang 1.
- Contrôle d'exactitude :
  - fronts régionaux × tous les ensembles de couches : 768 options énumérées, front identique ;
  - toutes les trajectoires × fronts de couches : 399 options, front identique ;
  - aucune réparation nécessaire.

**Régimes de conclusion (indicatifs, catégorie NOT_IDENTIFIABLE)**
- Est : aucun régime établi. **Signal** de réification : les deux trajectoires qui créent un troisième État sont pires que le statu quo sur J_reif, borne haute tirée d'un effet déclaré I7. Leurs droits (J_D) ne sont pas dégradés, et `GEOGRAPHIC(k=3)` reste un compromis au front composé.
- Ouest : aucun régime établi.
- Interface : aucune couche ne domine l'absence de couche.

## Challenge
Neuf défauts traités (ADR-0026) :
- coût d'interface caché ;
- couche gratuite ou bassin inventé ;
- perte d'option à l'élagage, démontrée par un cas construit : contrôle et réparation ;
- régions incommensurables ;
- double comptage ;
- couche « utile » sur hypothèse d'expert ;
- provenance continentale refusée par la clé étrangère de `run_manifests`, trouvé par le test en base ;
- régime de conclusion lu sur un compromis ;
- « séparation dangereuse » établie au premier pilote sur la seule borne haute de J_reif : le régime exige désormais infaisabilité ou droits dégradés, et J_reif devient un signal.

## Manquant
- **Liens de groupe transfrontaliers** dans J_F et J_conn. Le bénéfice des couches pour les groupes répartis de part et d'autre (09 §2) est sous-estimé, au détriment des couches.
- **Élagage intermédiaire entre fusions successives** : au-delà de deux ou trois régions, le produit des fronts croît vite.
- **Recomposition continentale sous R0–R3** : la dépendance au régime est lue sur les validations régionales.
- **Stress-tests continentaux** (09) sur géographies réelles ; hydrographie pour les bassins.
- **Map-C-Deep** : branche de recherche séparée (prompt §55).

## Tests
- **Unitaires** (`test_continental.py`) :
  - règles d'agrégation et coût d'interface ;
  - bornes robuste et optimiste des couches ;
  - couche à effet nul jamais retenue ;
  - composition des relations et blocage par l'axiome de fusion ;
  - décomposition = énumération exhaustive sur trois mondes aléatoires ;
  - front vectorisé = archive ;
  - régimes de conclusion (dominance exigée ; séparation par les droits, réification en signal) ;
  - perte d'élagage détectée puis réparée.
- **Red-team** (`test_m14_redteam.py`) :
  - couche gratuite et bassin refusés ;
  - régime ou maillages différents refusés ;
  - même contexte deux fois refusé ;
  - bibliothèque continentale sans estimation, bornes basses nulles ;
  - Map-R seulement ;
  - aucune partition générée ou évaluée, aucune géométrie exportée, aucun vocabulaire interdit.
- **Intégration** :
  - composition de bout en bout : ordre de la file, exactitude, statu quo au front, coût d'interface, couche vide, rapport, idempotence ;
  - en base : composition, régions rattachées aux manifestes, provenance, migrations 0014–0015.
- **Suite complète** : 319 tests passés sur 320. L'échec, un rejeu en base qui dupliquait la provenance, est corrigé (enregistrement idempotent) ; les tests continentaux (base, intégration, unitaires, red-team) ont été relancés et passent.

## Benchmarks
- Étapes continentales : environ 2 s au total (dont `interfaces` 0,8 s, `coordination` 0,8 s).
- Région Est : 120 s ; smoke : 110 s.

## Prochain milestone
M14 clôt les milestones obligatoires du prompt (§55). Suite proposée, après revue :
- liens de groupe transfrontaliers ;
- élagage entre fusions ;
- recomposition sous les régimes ;
- passage aux données réelles.
