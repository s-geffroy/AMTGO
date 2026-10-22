# ADR-0029 — ELG-Seg descriptif, gates E et P, feuille de route des données réelles

*Statut : accepté — 2026-10-22. Fait suite à une revue critique du projet remise au porteur le 2026-10-22 (« recommandations challengées et prochaines cibles », document de travail non publié). Cet ADR en retient les décisions, avec les amendements issus de la confrontation au code et au [rapport R0–R2](../milestones/R2_REPORT.md).*

## Contexte
- **Ce qui existe** : l'architecture M0–M15 tourne de bout en bout, mais sur des mondes synthétiques. Sur données réelles, seule la mesure de population régionale existe (ADR-0028). Son gate n'est passé que pour la couverture régionale.
- **Ce que la revue identifie comme verrou** : la mesure réelle, la validation empirique et la comparabilité transfrontalière, et non plus l'architecture.
- **Ce que la revue retire d'elle-même** : un objectif `MAP_E` d'homogénéité ethnolinguistique. Optimiser l'homogénéité revient à minimiser le mélange. Cela favorise les micro-territoires, multiplie les frontières, isole les métropoles et exploite les erreurs de mesure.

## Décision

### 1. ELG-Seg est un module descriptif
ELG-Seg (*ethnolinguistic-geographic segmentation*) produit des **zones candidates de cohérence** ethnolinguistique et géographique. Il ne produit ni État, ni souveraineté, ni recommandation, ni légitimité.

\[
\text{frontière ELG} \not\Rightarrow \text{frontière politique}
\]

- **Ce qu'il ne cherche pas à réduire : la diversité locale.** H_local = Σ_i (P_i/P) H_i est l'entropie de composition des cellules. Aucune frontière ne la réduit sans déplacer des personnes. Elle n'entre jamais dans l'objectif.
- **Ce qu'il mesure : l'incohérence entre les cellules regroupées.** H_between(Z) = Σ_k Σ_{i,j∈Z_k} w_ij d(i,j), avec d_ij = w_E d_E + w_L d_L + w_G d_G + w_H d_H. Les termes :
  - d_E : distance de composition, calculée sur des **parts** (jamais sur une étiquette ni une majorité) ;
  - d_L : distance linguistique, sur des profils fonctionnels ;
  - d_G : résistance géographique ;
  - d_H : mémoire historique, de poids nul par défaut. Elle ne sert qu'à des analyses de sensibilité déclarées.
- **K, le nombre de zones, n'est jamais fixé ni pénalisé arbitrairement.** On balaie K de K_min à K_max, et on rapporte :
  - les plateaux et les coudes du gain marginal ;
  - les zones persistantes ;
  - la stabilité selon le maillage, l'ontologie et la période.
  
  La sortie est **hiérarchique** (macro-région, région, sous-région), pas une partition unique.
- **La sortie principale est la probabilité de frontière**, P(b ∈ segmentation), pas une ligne. Quand une frontière est faible, la sortie est une bande, un gradient ou une zone mixte.
- **Garde métropolitaine** : ELG-Seg ne découpe jamais une agglomération selon ses quartiers. Une métropole détectée devient un candidat civique à part entière, M_k.
- **ELG est une famille de candidats parmi d'autres, sans privilège.** Elle s'ajoute à STATUS_QUO, NO_TERRITORIAL_CHANGE, INSTITUTIONAL_ONLY_REFORM, GEOGRAPHIC, GRAPH_*, HISTORICAL, LANGUAGE et MOBILITY, et à METRO à venir. Les baselines restent toujours présentes (ADR-0021).
- **Vocabulaire** : le contrôle existant s'applique aux sorties d'ELG-Seg. Pas de « meilleure segmentation », pas d'`argmin`, pas d'« optimal ».

### 2. Confidentialité des sorties de groupe
Le profil ethnoculturel d'une zone, la composition probabiliste et les langues identitaires sont des **champs de groupe**. Ils restent **au minimum CONTROLLED et ne sont jamais publiés** : c'est la règle en vigueur, et la revue la reprend elle-même (Y1, Y2).

- **Ce qui peut être public, après le privacy guard** :
  - la probabilité de frontière ;
  - la stabilité ;
  - des zones **sans étiquette de groupe** ;
  - la géographie ;
  - les métropoles.
- **Conséquence pour l'atlas continental** : les cartes A (composition) et B (langues identitaires) proposées par la revue seront CONTROLLED, jamais publiques.

### 3. Deux gates successifs, Gate E puis Gate P
- **Gate E (segmentation descriptive)**. Il autorise ELG-Seg si six conditions sont réunies :
  - population calibrée ;
  - composition validée sur holdout ;
  - langue disponible, au moins de façon minimale ;
  - géographie réelle intégrée ;
  - stabilité multi-échelle évaluée ;
  - sensibilité ontologique évaluée.
  
  En échec, le run conclut `NOT_IDENTIFIABLE` (statut existant). En succès, il n'autorise **aucune** conclusion politique.
- **Gate P (optimisation institutionnelle)**. Il exige :
  - D, F et I mesurés avec une classe de calculabilité suffisante ;
  - la viabilité évaluée ;
  - un support causal suffisant ;
  - des scénarios constitués ;
  - le consentement, explicitement **externe** au modèle.
  
  En échec, le run conclut `INSTITUTIONAL_OPTIMIZATION_BLOCKED`. Ce statut sera ajouté à `RecommendationStatus` quand la phase P sera atteinte ; il n'est pas codé avant.
- **Les modules M9–M15 restent exécutables sur mondes synthétiques**, pour les tests. Sur données réelles, ils restent bloqués tant que le Gate P n'est pas passé.

### 4. Feuille de route adoptée, avec ses amendements
L'ordre de la revue est adopté :
1. A1 : benchmark du modèle spatial de population ;
2. A2 : propagation de l'incertitude ;
3. B1 : PHC Ghana 2021 ;
4. B2 : posterior de composition ;
5. C1 : registre des sources linguistiques ;
6. E1 à E6 : géographie ;
7. F : Gate E ;
8. G : ELG-Seg au Ghana ;
9. I : sélection du pilote transfrontalier ;
10. ensuite F, D et I réels, Gate P, puis candidats, optimisation, Map-R et Map-C-Shallow.

La revue apporte quatre amendements :

- **A1 change de cible.** La revue partait du premier rapport R2, qui décrivait un prior surconfiant. La correction R2b (centrage sur l'espérance, erreur corrélée) a inversé le constat : les intervalles sont désormais **trop prudents** (rms z de 0,02 à 0,42). Surtout, deux à onze régions retenues ne peuvent départager aucun modèle.
  - A1 est donc d'abord un **problème de validation** : les **districts du PHC 2021** (données ouvertes) servent de holdout, par validation croisée en blocs spatiaux.
  - Mesures : couverture à 50, 80 et 95 %, CRPS, log-score, stabilité multi-maillage.
  - Modèles comparés : le prior indépendant (centré), le prior corrélé actuel, un hiérarchique administratif et une variante de voisinage de type BYM2.
  - SPDE et processus gaussien ne seront testés que s'ils tiennent dans la mémoire du worker. Sinon, ils seront déclarés non testés.
- **B1 suppose un accès nominatif.** L'échantillon de 10 % du PHC est une microdonnée, de classe RESTRICTED_LOCAL, à ranger sous `restricted/` (ADR-0028). Seul le porteur peut demander l'accès.
  - Deux points restent à vérifier sur la documentation officielle : la présence du code de district dans l'échantillon public ; le champ de la question d'ethnicité (posée aux seuls Ghanéens).
  - L'adapter sera écrit d'abord sur une fixture synthétique au schéma du dictionnaire public.
- **Le pilote transfrontalier sera choisi par un score.** Zambie–Malawi n'est plus fixé d'avance. Les pays préparés (Zambie, Malawi, Tanzanie) deviennent des entrées de ce score, aux côtés du Ghana–Togo, du Ghana–Côte d'Ivoire, du Bénin–Nigeria et du Kenya–Tanzanie.
- **La phase E est soumise aux licences.** OSM (ODbL) et V-Dem (CC BY-SA) sont des licences à partage à l'identique. La décision n° 6 du [cadrage](../CADRAGE_DONNEES_REELLES.md) devient bloquante pour E4. Les licences de HydroSHEDS et de LEDA restent à vérifier. Glottolog ne sert que de taxonomie : il n'est jamais une source de p(langue | cellule).

### 5. Recommandations retirées par la revue, et confirmées ici
- `MAP_E` comme objectif ;
- le choix immédiat d'un CAR ou ICAR : celui-ci devient un modèle candidat du benchmark ;
- la présupposition d'un Afrobarometer récent géocodé finement ;
- un second pilote fixé d'avance ;
- un M16 (raffinement des interfaces régionales) immédiat ;
- un nombre d'États fixé ou pénalisé.

## Conséquences
- **Pas encore de code ELG-Seg.** Il ne commence qu'après le Gate E. Les lots suivants sont A1, puis A2, puis B1 (sur fixture tant que l'accès manque).
- **Une zone ELG n'est robuste** que si elle tient sous trois stabilités, chacune au-dessus de son seuil : S_mesh > τ_m, S_ontology > τ_o et S_time > τ_t. Son posterior doit en plus être concentré. Elle ne doit dépendre ni d'un seul jeu de données, ni d'une seule ontologie, ni d'un seul maillage, ni d'une seule période. Les seuils seront fixés dans le manifeste normatif avant tout run réel, et non après.
- **Les critères d'une nouvelle frontière politique restent ceux de la spécification** : nécessité, alternatives moins séparatrices testées d'abord, consentement externe. ELG-Seg n'en est qu'une entrée.
