# ADR-0003 — Nomenclatures canoniques

*Statut : accepté — 2026-10-20.*

## Contexte
Le corpus nomme différemment les mêmes objets.

## Décision
- Régimes : `R0_CURRENT_LIKE`, `R1_COMMON_MARKET`, `R2_CONFEDERAL`,
  `R3_FEDERAL_CONTINENTAL` (noms du prompt §28). Alias acceptés et normalisés :
  `R0`, `R0_CURRENT`, `R3_FEDERAL`, `R2_CONFEDERATION`…
- `EvidenceStatus` : membres `DIRECT/PROXY/MODEL/HISTORICAL/UNKNOWN`, valeurs
  `D/P/M/H/U`. `U` signifie **UNKNOWN** (« unidentified » en 03 §2 est lu comme
  synonyme).
- Hyperarêtes (M5) : **union** des listes du prompt §27 et de 02 §4 —
  `river, lake, corridor, pastoral, metro, cultural, industrial, energy, trade,
  security, historical` — mais l'ensemble effectif est piloté par la
  configuration. Aucun type ne donne automatiquement une souveraineté.

## Conséquences
Un seul vocabulaire en code ; les documents anciens restent lisibles.
