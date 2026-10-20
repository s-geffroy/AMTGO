# ADR-0013 — Modèle de mesure de la population (M3)

*Statut : accepté — 2026-10-20.*

## Contexte
03 §27 demande une fusion $p(Z\mid D) \propto p(Z)\prod_o p(o \mid Z, Q_o)$ où chaque
source garde sa vraisemblance ; 07 §8 un moteur qui produit moyenne,
incertitude et provenance. Le prototype doit tourner sur 768 Mo et un CPU.

## Ce que le challenge a cassé, dans l'ordre

| version | problème mesuré sur le monde synthétique | correction |
|---|---|---|
| 1. linéaire-gaussien, prior N(m, (3m)²) | jusqu'à 97 % des cellules avec tirages négatifs ; total vrai non couvert (−16 %) ; maillages incompatibles (z = 8,6) | prior positif |
| 1. idem | EA trop confiantes : une EA en centre de bourg impose sa densité à toute la cellule (holdout 74–89 % pour 90 %) | **erreur de représentativité** explicite |
| 2. log-normal, Gauss-Newton sans recherche linéaire | non convergé (oscillation) | **recherche linéaire d'Armijo** |
| 3. log-normal convergé, Laplace sur toutes les observations | total +47 à +108 % : en grande dimension faiblement contrainte, la linéarisation au mode ne tient pas les contraintes de somme (queue de l'exponentielle) | totaux administratifs en **marges** |
| 4. **retenue** | total vrai couvert partout (erreur 0,4 %), couverture cellules 92–94 %, holdout 91–100 %, maillages compatibles (z ≤ 1,8) | — |

## Décision
Estimateur en deux étapes, déclaré dans le manifeste de mesure :

1. **Structure relative** — prior log-normal indépendant sur la densité
   ($\log\rho_i \sim N(\log m, \sigma^2)$) ; vraisemblances de type
   `likelihood` (zones d'énumération : $y = a\,\bar\rho_{\text{noyau}}$,
   bruit de Poisson + $(\mathrm{cv}\cdot y)^2$) ; mode par Gauss-Newton avec
   recherche linéaire, postérieure de Laplace, tirages par la règle de Matheron
   au mode (sans covariance N × N, matrices creuses).
2. **Marges** — vraisemblances `area_total` déclarées `use: margin` : pour
   chaque tirage, un total est tiré selon le bruit propre de la source, puis le
   tirage est recalé sur ces totaux par point fixe (IPF à appartenance
   fractionnaire). Marges disjointes obligatoires.

Le modèle linéaire-gaussien exact reste disponible (`independent_density`) comme
référence de test.

Hypothèses déclarées dans chaque rapport (*WE ASSUME*) : densité homogène dans
une cellule ; prior indépendant entre cellules ; données manquantes ignorables.

Diagnostics : convergence de Gauss-Newton (non convergé ⇒ classe D) ; tirages
négatifs (modèle gaussien) ; ratio d'information **par cellule et à 100 km** ;
holdout prédictif ; ablation ; désaccord inter-sources ; comparaison entre
maillages sur une grille de référence indépendante des marges.

## Conséquences
- Un champ latent est toujours de statut **MODEL**, contrainte vérifiée jusqu'en base.
- À la maille de la cellule, la population du pilote n'est **pas identifiée**
  (classe D) ; elle l'est à 100 km (A/B). Le système le dit au lieu de
  produire une précision fictive.
- Paramètres de modèle provisoires (`median_density_per_km2`, `log_sd`,
  `representativeness_cv`) : leur sensibilité devra être rapportée (05 §18).
- Corrélation spatiale a priori, modèle de sélection (MNAR) et harmonisation
  temporelle : non implémentés, déclarés en lacunes.
