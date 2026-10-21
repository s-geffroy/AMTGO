# AMTGO

**African Multilayer Territorial Geometry Optimization** — implémentation de la
spécification V1.0-RC1.

AMTGO **n'est pas** une carte ethnique, un outil de partition automatique, un
générateur d'États, ni un système qui inférerait une « vraie frontière
naturelle ». C'est un **laboratoire de géométries constitutionnelles
multi-couches** : il compare des configurations institutionnelles sous
incertitude, contraintes de droits, causalité explicite, plusieurs ontologies,
plusieurs maillages et plusieurs régimes constitutionnels.

Son résultat principal n'est pas une carte unique, mais un ensemble de solutions
de Pareto robustes **conditionnelles** :

$$
\mathcal P^*(R, O, S, \Theta)
$$

à un régime constitutionnel $R$, une ontologie $O$, un scénario $S$ et des
paramètres normatifs $\Theta$. Il doit toujours pouvoir conclure **aucun
changement territorial** ou **non identifiable** — c'est un succès scientifique,
pas un échec.

!!! note "Formulation"
    AMTGO ne « prouve » jamais qu'une région devrait changer de statut. La seule
    formulation admise est : *sous le régime R, l'ontologie O et les hypothèses
    causales C, cette configuration appartient à l'ensemble de Pareto ; sa
    robustesse est X et son adoption exige un consentement politique externe au
    modèle.*

## État d'avancement

| milestone | contenu | état |
|---|---|---|
| M0 | bootstrap : configuration, logs, migrations, manifestes, file de runs, CI | fait |
| M1 | registre de sources, licences, ingestion, provenance | fait |
| M2 | maillages H3 et grille équivalente, opérations multi-échelles | fait |
| M3 | modèles de mesure, champs latents, incertitude, validation, gel | fait |
| M4 | ontologies concurrentes, crosswalks probabilistes, composition en ensemble | fait |
| M5 | domination / fragmentation / intégration, mondes A–F, statu quo évalué | fait |
| M6 | scénarios S1/S2A/S2C, régimes typés, viabilité contextuelle, monde V | fait |
| M7 | bibliothèque causale, DiD échelonné validé, transport, gel | fait |
| M8 | candidats : baselines, familles géographiques et de graphe, stabilité multi-échelle | fait |
| M9 | composeur institutionnel à géométrie fixe, monde I, conclusion NO_CHANGE possible | fait |
| M10 | optimiseur régional : archive de Pareto robuste, ε-dominance, Gate O | fait |
| M11 | validation et red-team : S^parameter, régimes, multi-échelle, ablations, Goodhart, falsification, confidentialité, gates | fait |
| M12 | Map-R régional : trajectoires depuis le statu quo, transition comprise, explications, lecture conditionnelle | fait |
| M13 | Map-C-Shallow : contre-factuel contemporain sans privilège juridique, prime de l'existant | fait |
| M14 | composition continentale | à venir |

La mesure de population du pilote synthétique est validée contre la vérité :
non identifiée à la maille de la cellule, identifiée à 100 km. La composition
fictive est mesurée sous deux ontologies concurrentes — parts seulement, jamais
d'étiquette — et sa dépendance à l'ontologie est quantifiée. Domination,
fragmentation et intégration sont évaluées pour le statu quo déclaré, et
vérifiées sur les mondes A–F. Sa viabilité est évaluée sous chaque régime et
chaque scénario — jamais hors contexte — et vérifiée sur le monde V. Les effets
causaux viennent d'une bibliothèque gelée : un effet estimé sur un panel fictif
est admis, un autre, à adoption endogène, est rejeté. Des candidats territoriaux
sont générés comme unités analytiques — non évalués, non publiés. À géométrie
fixe, le composeur institutionnel conclut : aucun changement requis. Une archive de
Pareto robuste compare les candidats ; ses biais sont déclarés et aucune solution
n'est publiable. La validation recalcule cette archive sous chaque paramètre
normatif, chaque régime et chaque maillage, l'attaque (Goodhart, confidentialité)
et applique les gates de publication : le pilote reste NOT_IDENTIFIABLE. Map-R
compare enfin des trajectoires depuis le statu quo, transition comprise : aucune ne
fait mieux que rester partout. Map-C-Shallow retire le privilège juridique de la
géométrie actuelle : elle reste au front, et ce privilège ne protège ici rien de plus. À ce stade,
**aucun découpage n'existe** : la [carte](carte.md) montre les pays
actuels et les maillages d'analyse, et sa couche de candidats affiche
*NOT_IDENTIFIABLE*.

## Lire ensuite

- [Évaluation d'implémentation](IMPLEMENTATION_ASSESSMENT.md) — compréhension, incohérences tranchées, risques.
- [Architecture](architecture.md) et [décisions](decisions/index.md).
- [Rapports de milestone](milestones/M0_REPORT.md) et [runs synthétiques](runs/index.md).

## Licence

Cette documentation, les rapports de run et les couches de la carte sont publiés
sous [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.fr). Le code est sous
[Apache-2.0](https://github.com/s-geffroy/AMTGO/blob/main/LICENSE). Le fond de
carte Natural Earth est dans le domaine public.
