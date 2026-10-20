# Modèle de menace (préliminaire)

*Version M2. Le modèle complet et le red-team de reconstruction sont l'objet de
M11 (Gate S).*

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

## Non couvert à ce stade

Reconstruction par intersection de couches, inférence de religion ou de route
pastorale, seuils de petites cellules : sans objet tant qu'aucune couche de
population ou de groupe n'est exportée. **Bloquant** pour toute publication
future de telles couches.
