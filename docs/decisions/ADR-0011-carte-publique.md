# ADR-0011 — Carte publique sur GitHub Pages

*Statut : accepté — 2026-10-20.*

## Contexte
Le porteur du projet souhaite une carte de l'Afrique montrant les pays actuels
et « le nouveau découpage ». La doctrine interdit toute « vraie carte de
l'Afrique » (00), le solve continental en V1 (07 §13), les lignes nettes sans
support (§75-76), et impose l'alternative NO_CHANGE (§78) et les règles de
communication de 06 §15. À M0–M2, aucun découpage n'existe.

## Décision (validée avec le porteur du projet)
Carte **évolutive** :
- pays actuels — Natural Earth admin-0 1:50m v5.1.2, domaine public, frontières
  *de facto*, lignes disputées / indéfinies en pointillé ; déclarés comme Source
  M1 avec sha256 et rôles (`basemap_display` autorisé ; `legal_boundary_truth`
  interdit) ;
- maillages d'analyse (H3 r3, grille LAEA 200 km), explicitement « pas des
  propositions » ;
- couche « découpages candidats » alimentée **uniquement** par `candidates.json`,
  produit par un export passé au privacy guard et aux gates. Vide aujourd'hui,
  elle affiche *NOT_IDENTIFIABLE*. Quand elle sera remplie : affichage par
  régime/ontologie/scénario, bandes d'incertitude, lignes nettes seulement si le
  statut l'autorise, alternative NO_CHANGE toujours visible.

Aucun découpage n'est inventé ni repris des bassins L2/L3 de V0.x (09 §15).
