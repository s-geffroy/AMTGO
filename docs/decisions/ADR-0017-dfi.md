# ADR-0017 — Domination, fragmentation, intégration (M5)

*Statut : accepté — 2026-10-20.*

## Contexte
Prompt §22–27, 02 §9–12 : D par domaine avec contraintes de droits, F par canal
via la charge frontalière B = C·σ·(1 − μ), tenseur d'intégration et J_conn,
mobilité, infrastructures, hyperarêtes ; §18–21 : identités endogènes, risque de
réification, identité nationale séparée ; §56 : mondes synthétiques A–F.

## Décision
- **Fonctions pures sur tirages** : chaque métrique est une distribution
  (200 tirages de population × composition gelées), jamais un point.
- **Domination** : D_pot = A·X·(1 − C), avec X = 1 − pouvoir effectif. Le pouvoir
  découle de la règle de décision : min(1, r/(1 − q)), et 1 avec veto. D_real
  reste UNKNOWN sans observation. Contrainte P(d > τ) ≤ ε sur chaque composante
  connue ; drapeau d'urgence.
- **Fragmentation** : F^c_g est la part des liens valorisés de g coupés,
  T^g_ij = R^c_ij n_gi n_gj. **Le canal territorial exige un attachement
  observé** : la contiguïté seule mesurerait une présence, ce que le §23
  interdit. La cohésion culturelle est modulée par le partage d'identité
  nationale (§21) ; il n'existe aucun mapping ethnoculturel → national.
- **Intégration** : exposition, qualité, réciprocité par canal ;
  J_conn = connexions intergroupes valorisées coupées / **toute** la vie
  sociale (somme de 02 §11 ramenée à une échelle commune). κ_c sont des poids
  normatifs du manifeste.
- **Canal sans données = UNKNOWN**, jamais 0.
- **Noyau de liens** : moyenne de exp(−d/L) sur des points de quadrature des
  cellules, et non valeur au centroïde.
- **Réification** : alignement = dissimilarité multigroupe (descriptif, pour
  *signaler*). RRI = intervalle à partir de bornes exploratoires déclarées, ou
  CAUSAL_EFFECT_UNKNOWN.
- **Statu quo déclaré** : une baseline évaluée (STATUS_QUO), et non un
  candidat. La frontière entre États suit le gabarit du régime constitutionnel.
- **S^ontology et S^scale sur D/F/I** : 1 − écart relatif maximal des
  quantités principales, avec plancher numérique. Les écarts bruts sont
  rapportés, avec un drapeau « sous le plancher ».

## Ce que le challenge a cassé
| problème | correction |
|---|---|
| J_conn normalisé par les seules connexions intergroupes : A (séparés, « 84 % coupés ») au-dessus de B (intégrés, « 9 % ») | normalisation par toute la vie sociale : A 0,003 ≪ B 0,043 |
| canal territorial = adjacence × présence : monde F « fragmenté » parce que x vit des deux côtés | canal territorial seulement avec attachement observé ; test red-team |
| `UncertainValue` exigeait moyenne ∈ intervalle à 90 % : faux pour des tirages asymétriques | contrainte réservée aux lois non empiriques ; test de régression |
| noyau au centroïde : F variait d'un facteur 3 selon la maille ; S^scale = 0,94 masquait l'écart (plancher) | quadrature (facteur 2,2) ; écarts bruts et drapeau « sous le plancher » rapportés |
| overlay pastoral sans droits fonciers : fragmentation territoriale inchangée | μ territorial dans l'overlay pastoral |

## Conséquences
- Les six propriétés A–F sont vérifiées à chaque build (`amtgo validate worlds`)
  et publiées.
- σ* (prompt §56) relève de l'optimiseur : M5 fournit les composantes.
