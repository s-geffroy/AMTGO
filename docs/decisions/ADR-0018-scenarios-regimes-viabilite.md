# ADR-0018 — Scénarios, régimes typés, viabilité contextuelle (M6)

*Statut : accepté — 2026-10-20.*

## Contexte
- **Prompt §28-29, §34-37, §86, §93** : régimes exogènes et pilotés par la configuration ; viabilité toujours conditionnelle ; scénarios versionnés selon sept axes ; S1 sans déplacement induit, S2A volontaire, S2C diagnostic agrégé ; interface sûre du diagnostic de coercition.
- **02 §14, §23-25** : V_k(r) = f(capacité de service, base fiscale, transferts(r), accès au marché(r), infrastructure(r), sécurité(r)).
- **01 §8** : pas de biais vers l'autarcie.
- **Spec 14** : R0–R3, et V_k(R0) ≠ V_k(R3).
- **10 §16-17** : schémas des régimes et des scénarios.

## Décision

### Régimes typés
- Les règles ne sont plus des dictionnaires libres. Ce sont des modèles stricts à valeurs dans [0, 1] : libre circulation, péréquation, recettes mises en commun, défense mutualisée, intégration du marché, ressources partagées et **infrastructures communes**. Ce dernier bloc étend le schéma 10 §16, puisque 02 §14 fait dépendre la viabilité de l'infrastructure sous le régime.
- **Les dimensions E, M, R, S de la frontière entre États dérivent des règles**, par exemple σ^M = 1 − libre circulation. Seules P et C restent déclarées. Un régime ne peut donc plus déclarer à la fois un marché commun complet et une frontière économique forte.
- Les valeurs reproduisent les gabarits de M5 : la frontière du pilote est inchangée.

### Scénarios
- Les sept axes sont des intervalles déclarés, tirés de façon déterministe à partir de la graine et de l'empreinte du scénario.
- Un intervalle réduit à un point est une hypothèse de maintien, reportée comme telle.
- **Aucun scénario climatique unique** : il faut au moins deux trajectoires, sinon le climat est marqué « non modélisé ».
- `forced_migration` et `reform_induced_relocation` ne sont pas des paramètres. Ils sont vérifiés nuls à quatre moments : au chargement du scénario, à la soumission du run, à l'exécution (variation totale de la répartition spatiale < 10⁻⁹) et en base (contrainte CHECK).

### Mobilité volontaire (S2A)
- La réponse volontaire à une réforme est un effet causal. Sans bibliothèque causale (M7), elle vaut `CAUSAL_EFFECT_UNKNOWN`.
- La décomposition direct / composition / spillover est exacte : la somme des trois effets égale le total. Ses deux derniers termes restent `None`, jamais 0, tant que la réponse est inconnue.

### Diagnostic de coercition (S2C)
- Le diagnostic `CoercionDependencyDiagnostic` porte exactement les quatre champs du §93.
- Ses entrées sont des effectifs par **juridiction**, jamais par cellule.
- La borne de population déplacée vaut Σ max(0, c − t). Elle se calcule sans aucun appariement origine/destination.
- Aucune fonction ne cherche ni ne maximise une répartition.
- Sur le statu quo, le diagnostic est NOT_APPLICABLE : son bénéfice par rapport à lui-même est nul par construction.

### Viabilité
- `compute_viability(territory, regime, scenario, context)` calcule la couverture du panier de services : cov = (R + T − O) / C, avec les recettes R, les transferts T, les surcoûts fixes O et le coût des services C.
- **Accès au marché** : MA_k = s_k + (1 − s_k)·intégration. Il relève la base fiscale par (MA(r)/MA(r_obs))^γ.
- **Transferts** : péréquation et mise en commun, budgétairement neutres.
- **Surcoûts fixes de souveraineté** : administration, plus la part de sécurité non mutualisée. La part mutualisée n'est payée qu'une fois par l'union.
- **Statut** : VIABLE si P(cov < τ_V) ≤ ε_V, NOT_VIABLE dans le cas symétrique, UNCERTAIN sinon, UNKNOWN sans comptes. τ_V et ε_V sont normatifs (manifeste).
- **Aucun seuil de taille** : le schéma les refuse.
- `bool()` lève, et l'énoncé nomme toujours le régime et le scénario.
- **γ et δ** sont des coefficients exploratoires (I7) dont les bornes incluent 0. Un statut qui change entre ces bornes est signalé « dépend de coefficients exploratoires ».

### Sensibilité au régime (05 §19)
- Le statu quo est évalué sous R0–R3.
- Un statut qui varie selon le régime est marqué « dépend du régime ».

## Ce que le challenge a cassé
| problème | correction |
|---|---|
| Gabarits de frontière déclarés à côté de règles textuelles (« common_market: strong ») : rien n'empêchait l'incohérence | règles typées ; E, M, R, S dérivées |
| Comptes fiscaux observés traités comme régime-neutres : sous R0, l'accès au marché aurait « amélioré » le statu quo | effets relatifs au régime d'observation déclaré ; au régime d'observation, les coefficients exploratoires n'ont aucun effet (vérifié, monde V) |
| Un premier jeu de surcoûts fixes rendait tout petit territoire non viable sous tout régime : l'autarcie revenait par les paramètres | monde V : la propriété « non viable sous R0, viable sous R3 » doit tenir et est vérifiée à chaque build |
| S2C pouvait être appelé sur le statu quo, sans bénéfice à expliquer (ratio 0/0) | `InsufficientEvidence` ; le pipeline rend NOT_APPLICABLE |

## Conséquences
- Le monde V s'ajoute aux mondes A–F (`amtgo validate worlds`, page publiée).
- La valeur de souveraineté MV_S(k, R) exige de comparer des vecteurs de compétences sous régime : c'est le composeur institutionnel (M9).
- Les coefficients γ et δ seront remplacés par la bibliothèque causale (M7).
