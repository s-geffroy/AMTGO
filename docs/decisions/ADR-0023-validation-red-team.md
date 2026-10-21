# ADR-0023 — Validation et red-team : stabilité, ablations, Goodhart, confidentialité, gates (M11)

*Statut : accepté — 2026-10-21.*

## Contexte
- **Prompt §45** (multi-échelle), **§55** (M11 : multi-scale, ablation, Goodhart, privacy), **§57** (red-team permanents).
- **02 §19** : S^publish = min(S^ontology, S^scale, S^time, S^parameter).
- **05 §5-21** : multi-échelle, stabilité temporelle, falsification, ablations, Goodhart, confidentialité, mésusage, sensibilités normative et de régime, gates, catégories de publication.
- **01 §17** : Goodhart ; **03 §25** : pas de seuil universel de confidentialité ; **03 §31** : préférence locale non identifiable.
- **ADR-0022** : biais déclarés en M10 — union favorisée faute de coût d'hétérogénéité, institutions non recomposées, S_publish inconnu.

## Décision

### Biais M10

**Coût d'hétérogénéité des préférences J_P.** Il est ajouté à J et reste **UNKNOWN**.
- La préférence réelle est un input externe, non identifiable sans enquête (03 §31, 08).
- Il n'est **jamais** déduit des parts de groupes : ce serait optimiser l'homogénéité ethnique. Un test l'interdit.

**Conclure exige les inconnus.** Un objectif UNKNOWN ne départage pas l'archive, mais il interdit de conclure qu'une option domine le statu quo, sauf si un axiome structurel le tranche.
- **Axiome** : tout coût d'hétérogénéité est monotone par fusion. Fusionner n'abaisse jamais l'hétérogénéité interne.
- Conséquence : un raffinement du statu quo n'est jamais pire sur J_P (NOT_WORSE), une fusion n'y est jamais meilleure (NOT_BETTER), un croisement reste UNDETERMINED.
- J_R n'a pas d'axiome : il reste UNDETERMINED hors géométrie identique.
- Nouvelle conclusion : **DOMINANCE_UNRESOLVED_UNKNOWN_OBJECTIVES**.

**Recomposition par candidat.** Un candidat qui viole la contrainte de droits passe par le composeur M9.
- S'il existe un paquet qui lève la violation à la borne basse, le candidat est évalué avec ce paquet.
- Le coût du paquet devient **J_pkg**, un objectif séparé : ses unités sont celles du composeur, et convertir vers les unités fiscales demanderait un taux inventé.
- Sinon la violation reste. Aucune relaxation.

### Stabilité et sensibilités
- **S^parameter** : part des réglages normatifs alternatifs où l'état (faisable, au front) d'une variante est inchangé.
  - Les paramètres varient un à la fois : τ et ε de domination, poids de robustesse, échelle de ε, coût de frontière.
  - La faisabilité est relue sur J_D(τ) ≤ ε, à configuration institutionnelle fixée au nominal.
  - Un paramètre qui change la conclusion est un **choix politique** (05 §18).
- **Régimes** (05 §19) : J_V et J_inst sont recalculés sous chaque régime de la sensibilité. Les frontières σ et la domination restent au régime du run (limite déclarée).
- **S^time** : il faut au moins deux millésimes de données. Sinon il vaut UNKNOWN, et S^publish avec lui.
- **Multi-échelle** (§45) : une archive par maillage seul. Une variante au front d'un seul maillage est « dépendante d'une résolution » et bloque Gate R.

### Ablations (05 §13)
- Archive recalculée sans :
  - J_D et la contrainte de droits ;
  - J_F ;
  - J_conn ;
  - l'incertitude (ρ = E) ;
  - les objectifs dépendant de la bibliothèque gelée ;
  - J_reif.
- Identité nationale, mobilité et infrastructure potentielle : **NOT_APPLICABLE** quand le run n'en a pas. C'est un constat, pas un succès.

### Goodhart (05 §14)
Trois attaques sont construites sur le statu quo et évaluées comme des candidats, hors archive nominale : micro-territoire, métropole artificielle, frontière en dents de scie.

Quatre détecteurs **signalent** pour revue humaine, sans rien exclure ni pondérer :
- part de population ;
- part de surface ;
- compacité de Polsby–Popper ;
- part de cellules frontalières en saillie.

Règles :
- une attaque au front sans signalement est une **faille** et fait échouer Gate O ;
- une variante signalée au front nominal bloque Gate R.

Overlay vide et transfert de coûts au niveau continental : tests de régression sur les modules.

### Falsification (05 §11)
- Mondes B, D et C : la partition alignée sur les groupes, la métropole coupée et le corridor devenu État ne dominent jamais l'option attendue.
- Rwanda, Afrique du Sud, Sahara et EPR : NOT_APPLICABLE sans données réelles, jamais réputés passés.

### Confidentialité (05 §15-16)
`evaluate_release` évalue une publication entière :
- petit effectif (< k, défini par le modèle de menace du manifeste normatif) ;
- différenciation entre supports ;
- inférence par proxy déclaré ;
- géométrie dérivée des groupes ;
- routes.

Gate S exige deux choses :
- les 6 attaques sont bloquées, en PUBLIC comme en CONTROLLED, et les 2 contrôles bénins sortent (un garde qui bloque tout ne prouve rien) ;
- aucune couche sensible de l'inventaire du run n'est publiable telle quelle.

### Gates et catégorie (05 §20-21)
- **M** : calculabilité A ou B, et totaux couverts.
- **C** : bibliothèque causale (M7).
- **O** : benchmark exact et Goodhart.
- **S** : confidentialité.
- **R** : S^publish ≥ τ, aucune dépendance à un seul maillage, falsification, aucune variante signalée au front.

Catégorie de publication :
- **NOT_IDENTIFIABLE** : S^publish inconnu, calculabilité D, ou dominance non résolue ;
- **DATA_LIMITED** : calculabilité C ;
- **EXPLORATORY** : un gate échoue ou S^publish < τ ;
- **CONDITIONAL** : la conclusion dépend d'un choix politique ou du régime ;
- **ROBUST** : sinon.

Publication seulement en ROBUST ou CONDITIONAL, tous gates passés. La base (0012) refuse une solution ROBUST ou CONDITIONAL sans gates passés.

## Ce que le challenge a cassé
| problème | correction |
|---|---|
| L'union « dominait » le statu quo hors transition parce qu'un objectif inconnu était ignoré aussi pour conclure | un inconnu bloque la conclusion, sauf axiome ; l'union est NOT_BETTER sur J_P |
| Tentation de mesurer J_P par la diversité des groupes | interdit (homogénéité ethnique) ; test AST |
| **Faille trouvée sur le pilote** : la frontière en dents de scie atteignait le front sans signalement, en améliorant J_V par des transferts de cellules fiscalement riches ; sa compacité (0,35) ne la distinguait pas des communautés de Louvain (0,32–0,41) | détecteur de cellules en saillie (≥ 0,37 contre ≤ 0,07 pour les candidats générés) ; test de régression |
| Suite d'attaques de confidentialité trivialement bloquée en PUBLIC (la population y est toujours « à agréger ») | attaques évaluées aussi en CONTROLLED, et contrôles bénins |
| S^publish « calculé » avec un S^time absent | S^time UNKNOWN sans deux millésimes, donc S^publish UNKNOWN |

## Conséquences
- Pilote : NOT_IDENTIFIABLE. Gate M échoue (calculabilité D) et Gate R n'est pas évaluable (S^time). Aucune publication.
- La conclusion de l'archive dépend du régime constitutionnel : c'est un résultat à mettre au centre de toute lecture (05 §19).
- Restent : S^time (deux millésimes), régimes appliqués aux frontières σ et à la domination, ablations amont (identité, mobilité), modèle de menace validé par la gouvernance (06).
