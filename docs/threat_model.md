# Modèle de menace (préliminaire)

*Version M11. Le red-team de reconstruction et Gate S sont en place ; le modèle de
menace reste à valider par la gouvernance (06).*

## Actifs sensibles

Cartes fines de minorités, religions, mobilités ou vulnérabilités (01 §20) ;
corridors pastoraux ; microdonnées ; toute intersection de couches publiques
permettant de reconstruire un petit groupe.

## Adversaires considérés (05 §16)

- gouvernement cherchant à identifier une minorité vulnérable ;
- acteur armé cherchant des routes ;
- campagne cherchant à cibler spatialement ;
- ingénierie démographique.

Objectif : le système **public** doit rester inutile à ces usages opérationnels.

## Mesures en place (M0–M2)

| mesure | effet |
|---|---|
| classes d'accès PUBLIC / CONTROLLED / SENSITIVE / PROHIBITED, défaut CONTROLLED | rien n'est public par défaut |
| zones de données ; sources restreintes jamais récupérées par http ni versionnées | pas de fuite par le dépôt (public) |
| observation jamais moins protégée que sa source | pas de déclassement silencieux |
| privacy guard : seules les couches sans population ni groupe sortent en PUBLIC | la carte publique ne contient que pays et maillages |
| logs en liste blanche de champs, sans valeur d'observation | pas de fuite par les logs |
| monde synthétique placé en plein océan | aucune confusion avec une population réelle |
| interdictions structurelles (prompt §92) testées par introspection | pas de fonction de ciblage ou d'homogénéisation |

## Red-team M11 (Gate S, 05 §15-16)

Une publication est évaluée **en entier** (`privacy.guard.evaluate_release`), couche par couche, dans l'ordre de priorité.

| règle | attaque bloquée |
|---|---|
| comptage < k (manifeste normatif, `privacy.min_group_count`) → supprimé | reconstruction d'un petit groupe |
| même comptage sur deux supports différents → seul le premier sort | intersection de couches publiques (différenciation) |
| attribut proxy déclaré (`privacy.sensitive_proxies` : religion, langue, étiquette historique, parts de groupes, route) → restreint | inférence de religion |
| mobilité ou route → restreinte | route pastorale sensible, acteur armé |
| géométrie calculée à partir des parts de groupes → restreinte | frontière candidate révélant les groupes |
| attributs de groupe → restreints | localisation d'une minorité, ciblage |

Chaque attaque est rejouée deux fois :
- pour une cible PUBLIC, où la population n'est jamais publiée telle quelle ;
- pour une cible CONTROLLED, où la population peut sortir : les règles de petit effectif et de différenciation doivent alors tenir seules.

Deux contrôles bénins doivent sortir, un maillage en PUBLIC et une population agrégée en CONTROLLED : un garde qui bloque tout passerait la suite sans rien prouver.

**Gate S** passe si toutes les attaques sont bloquées, si les contrôles bénins sortent, et si aucune couche sensible de l'inventaire du run n'est publiable telle quelle. Sur le pilote, seuls les maillages le sont.

## Non couvert

- k et la liste des proxies sont un **choix déclaré** (03 §25 : pas de seuil universel), en attente du comité de gouvernance (06).
- La différenciation est traitée de façon conservatrice : un attribut, un support. Un calcul exact des cellules reconstructibles entre supports emboîtés reste à faire.
- Aucune couche de population ou de groupe n'est exportée : la carte publique ne porte que pays et maillages.
