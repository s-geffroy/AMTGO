# ADR-0014 — Monde synthétique à vérité connue

*Statut : accepté — 2026-10-20.*

## Contexte
Valider un modèle de mesure exige une vérité. Aucune donnée réelle n'en a.

## Décision
- Un **monde** (densité vraie : fond uniforme + bourgs gaussiens, graine fixée)
  est décrit dans le bloc `world` des manifestes de source synthétiques ; deux
  **instruments** l'observent : enquête (EA comptées puis géomasquées) et
  recensement (totaux de districts, erreur relative).
- La vérité (quadrature à 2 km) ne sert qu'à la calibration. Elle n'est jamais
  écrite dans les observations, et `ground_truth_world` renvoie `None` dès
  qu'une seule source n'est pas synthétique : aucun chemin de code ne peut
  associer une « vérité » à des données réelles (test red-team).
- Tous les instruments d'un run doivent venir du même monde (refus à la soumission).
- Le territoire est placé en plein Atlantique Sud.
- Les tests vérifient des **propriétés** (couverture dans [0,8 ; 0,99], total
  couvert, ablation plus large que la fusion, information croissante avec
  l'échelle), pas des valeurs figées (ADR-0010).
