# Évaluation d'implémentation — AMTGO V1.0-RC1

*Étape 2 du prompt maître (§94). Rédigée avant le code, mise à jour à la fin de M2.*

## 1. Source de vérité

Le corpus V1.0-RC1 a été lu intégralement (fichiers `00` à `14`, plus le prompt
d'implémentation). Il n'est **pas publié** dans ce dépôt public ; seule son
empreinte l'identifie :

| fichier | sha256 |
|---|---|
| `00_README.md` | `c23cfa33580b916c17ce21cff0439f1fbcb2f8ad6b3f1c782c52493d72711440` |
| `01_CHALLENGE_GLOBAL_ET_REVISIONS.md` | `5907e490c588127ef2c92007917ca08860c6b520c8e0e03db3e23a397a03acf3` |
| `02_MASTER_MATHEMATICAL_SPECIFICATION.md` | `ba01969bd7e2e2f56816aba7481d4c349146408d386911c7e67c3f34a5e50ed9` |
| `03_MASTER_DATA_EVIDENCE_SPECIFICATION.md` | `3b3a3032daf1c2f957f9dce5a208e63aa36100809a8638c359868b7b8400c6ae` |
| `04_CAUSAL_IDENTIFICATION_COUNTERFACTUALS.md` | `64833ec23d5b194f04af93e94c08b4e5a3bda079343676cf96978c3ccf0c0c6b` |
| `05_VALIDATION_FALSIFICATION_REDTEAM.md` | `2dbdafd3e84d73852d21f25bef1553e66e4e5ac1986ef4494f9c6ee4412554c0` |
| `06_GOVERNANCE_ETHICS_SAFETY.md` | `44c9fb623f9d0fde286efb25858dac03fb73aea337df7d798e8861dfc17b5310` |
| `07_IMPLEMENTATION_ARCHITECTURE.md` | `b65cf65ada9aaea43f2cad6fcadb81b8046df47c27570a9cbf059563aa0f7717` |
| `08_METHODOLOGIE_HYPERDETAILLEE.md` | `89c12bc7a9eba3fb4a5a3e5b027aa2829cea9be6ce286187d323e92d613afd29` |
| `09_CONTINENTAL_STRESS_TESTS.md` | `5f92f771e876facd61e58afeb9a7f4f755183b03c8ff45bb28f94eb89d3d4d85` |
| `10_DATA_DICTIONARY_AND_SCHEMAS.md` | `c16754a2e41898417e954ceecc079a2a4943066b8f2fc49b2de012cdf485810e` |
| `11_ROADMAP_AND_ACCEPTANCE_CRITERIA.md` | `e9bc6d6bc2ac809eaf47729ea8078b70831f739cf8f82a391e6e9c1db7cfd7d1` |
| `12_BIBLIOGRAPHY_SOURCE_REGISTER.md` | `a7520ebc500b0d97fc10816c2d638f38a0247447efae65caf98ca9d10d788c9c` |
| `13_CHANGELOG_V0x_TO_V1_0_RC1.md` | `49b9204014a14b0107f59ecf7e203fa1bdfa7e0ece997ff59dc8338c04c20aba` |
| `14_NORMATIVE_REGIMES_AND_CONSENT.md` | `dfdee7be49bc21c4413a588be4e00fb00ddbb1dbecd25e76c96cd3583f9064e3` |
| `15_AMTGO_V1_0_RC1_ALL_IN_ONE.md` | `2449a999bac4e42ea5601e1b7f483ef81e5d96f7d03de7f545176505c0420ba1` |
| `ARCHIVE_AMTGO_Methodologie_Hyperdetaillee_V0.3.md` | `9fb4c841dac01c9f36967a42b50ceec31150c057e320d534c87e7cc352331e5d` |
| `AMTGO_PROMPT_IMPLEMENTATION_LLM_V1_0_RC1.md` | `8cbfbce1adbd6319cbc1ec60c62350ee26ec10c24431dcc5087c3c350e468552` |
| `AMTGO_V1_0_RC1_Markdown_Package.zip` | `9085eb126cd78f2323f4472b309b996e35e8217362d5f4ea3434a3658c8d297c` |

Aucun fichier n'est manquant (voir [lacunes](implementation_gaps.md)). Les
archives V0.x n'ont servi qu'à comprendre l'historique ; V1.0-RC1 prévaut.

## 2. Compréhension

AMTGO n'est ni une carte ethnique, ni un générateur d'États. C'est un
**laboratoire de géométries constitutionnelles multi-couches** dont le résultat
principal est un ensemble de Pareto robuste conditionnel
$\mathcal P^*(R, O, S, \Theta)$ — régime constitutionnel, ontologie, scénario,
paramètres normatifs — et qui doit toujours pouvoir conclure
**NO TERRITORIAL CHANGE** ou **NOT IDENTIFIABLE**.

Le pipeline canonique (prompt §8) est implémenté comme une suite d'étapes
séparées en code. M0–M2 couvrent : registre de sources → ingestion →
normalisation → maillages multi-échelles. Tout le reste est explicitement
absent et déclaré comme tel dans chaque rapport de run.

## 3. Incohérences relevées et tranchées

| # | incohérence | décision |
|---|---|---|
| 1 | Layout de la spec (`docker-compose.yml`, `src/amtgo/`) vs plateforme appctl (`compose.yaml`, worker) | [ADR-0001](decisions/ADR-0001-layout-appctl.md) |
| 2 | Pile GIS incompatible avec Alpine/musl et 256 Mo | [ADR-0002](decisions/ADR-0002-image-dependances.md) |
| 3 | Noms de régimes (`R0_CURRENT` / `R0_CURRENT_LIKE`, `R3_FEDERAL` / `R3_FEDERAL_CONTINENTAL`), statut `U` (unidentified / UNKNOWN), deux listes d'hyperarêtes différentes (prompt §27 / 02 §4) | [ADR-0003](decisions/ADR-0003-nomenclatures.md) |
| 4 | 7 canaux de cohésion, 5 de fragmentation, 7 d'intégration, 6 dimensions σ : la correspondance `d(c)` n'est définie nulle part | [ADR-0004](decisions/ADR-0004-correspondance-canaux.md) |
| 5 | `UncertainValue(mean, std, lower, upper)` ne permet ni `P(d>τ)≤ε` ni CVaR | [ADR-0005](decisions/ADR-0005-incertitude-echantillons.md) |
| 6 | `D = max(D_pot, D_real)` mêle capacité et domination observée | [ADR-0006](decisions/ADR-0006-domination-composantes.md) |
| 7 | `S_scale = 1 − E[d(G^a, G^b)]` exige une distance entre partitions sur maillages différents, non définie | [ADR-0007](decisions/ADR-0007-maillages-distance.md) |
| 8 | Calcul métrique : la spec interdit le 4326 mais ne fixe pas la projection | [ADR-0008](decisions/ADR-0008-projection.md) |
| 9 | Pareto à 9 objectifs quasi dégénéré ; Map-R écrite en `argmin` alors que `best_solution` est interdit | [ADR-0009](decisions/ADR-0009-pareto-map-r.md) |
| 10 | Les mondes synthétiques A–F encodent la conclusion attendue (risque de *teaching to the test*) | [ADR-0010](decisions/ADR-0010-mondes-synthetiques.md) |
| 11 | Carte publique demandée vs doctrine (pas de « vraie carte », pas de ligne nette sans support) | [ADR-0011](decisions/ADR-0011-carte-publique.md) |
| 12 | Batch scientifique vs worker périodique reprenable | [ADR-0012](decisions/ADR-0012-file-de-runs.md) |
| 13 | Fusion 03 §27 : famille de lois, positivité, contraintes de somme, représentativité | [ADR-0013](decisions/ADR-0013-modele-de-mesure.md) |
| 14 | Validation de la mesure sans vérité terrain | [ADR-0014](decisions/ADR-0014-monde-synthetique.md) |
| 15 | Performances sous quota CPU | [ADR-0015](decisions/ADR-0015-ressources-calcul.md) |
| 16 | Ontologies concurrentes, crosswalks, composition et vie privée de groupe | [ADR-0016](decisions/ADR-0016-ontologies-composition.md) |
| 17 | D/F/I : normalisation de J_conn, présence ≠ fragmentation, discrétisation des noyaux | [ADR-0017](decisions/ADR-0017-dfi.md) |

Autres points relevés, sans décision nécessaire à ce stade :

- **EvidenceStatus — ordre de force.** La spec interdit la promotion silencieuse
  mais n'ordonne pas `HISTORICAL` et `MODEL`. Choix conservateur :
  DIRECT > PROXY > HISTORICAL > MODEL > UNKNOWN, agrégation = minimum. À
  rediscuter en M3.
- **`cells.cell_id` clé primaire seule** (schéma 10 §3) : impossible, une cellule
  H3 appartient à plusieurs maillages. Clé `(mesh_id, definition_hash, cell_id)`.
- **Seuils normatifs** : la spec ne fixe que `severe_domination_probability_max
  = 0.05`. Les autres valeurs de `configs/normative/default.yaml` sont marquées
  **provisoires** en attente du comité de gouvernance (06 §6).

## 4. Risques

| risque | effet | mitigation |
|---|---|---|
| Données de mobilité, intégration, consentement non identifiables à maille continentale (03 §31) | M5+ produira surtout `UNKNOWN` | c'est un résultat valide (§91) ; jamais de coefficient inventé |
| Mésusage de la carte publique | double usage (06 §7) | aucune couche de population ou de groupe publique ; privacy guard avant tout export |
| Explosion combinatoire (ontologies × maillages × scénarios × régimes) | coûts | parallélisme seulement après profilage (§81) |
| Mémoire du VPS (worker 768 Mo, base 512 Mo) | maillages fins impossibles | pilote régional d'abord ; résolution continentale grossière |
| Réseau sortant des conteneurs | ingestion http impossible localement | sources épinglées par sha256, cache adressé par contenu, ingestion en CI |
| Licence du projet | dépôt public | tranché : code Apache-2.0, documentation et rapports CC BY 4.0 |

## 5. Plan et avancement

| milestone | contenu | statut |
|---|---|---|
| M0 | bootstrap : pyproject, CI, config, logs, migrations, manifestes, file de runs | **fait** |
| M1 | registre de sources : modèle de source, licences, contrat d'ingestion, provenance | **fait** |
| M2 | cœur spatial : cellules, deux familles de maillage, opérations multi-échelles | **fait** |
| M3 | mesure : interface de likelihood, champs latents, fusion bayésienne simple, incertitude | **fait** |
| M4 | ontologies : concepts, crosswalks probabilistes, exécution en ensemble | **fait** |
| M5 | domination, fragmentation, intégration ; mondes A–F | **fait** |
| M6 | scénarios, régimes typés, viabilité contextuelle ; monde V | **fait** |
| M7 | bibliothèque causale : grades, DiD échelonné, transport, gel ; Gate C | **fait** |
| M8 | candidats : baselines, familles, contiguïté, S^scale | **fait** |
