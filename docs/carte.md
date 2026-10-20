# Carte

<link rel="stylesheet" href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css">
<link rel="stylesheet" href="../assets/carte.css">

!!! warning "Ce que montre — et ne montre pas — cette carte"
    **Pays actuels** : frontières *de facto* selon Natural Earth (domaine public),
    qui n'est ni une source juridique ni une prise de position. Les frontières
    disputées ou indéfinies sont en pointillé.

    **Maillages d'analyse** : unités de calcul. Ce ne sont **pas** des propositions
    de territoires.

    **Découpages candidats** : vide à ce stade. Une configuration n'apparaîtra ici
    qu'après validation complète (mesure, causalité, optimiseur, robustesse,
    privacy). Elle sera alors toujours affichée sous un régime constitutionnel,
    une ontologie et un scénario donnés, avec ses bandes d'incertitude et
    l'alternative *aucun changement territorial*. Son adoption exigerait un
    processus politique extérieur au modèle.

<div class="amtgo-map-wrap" markdown="0">
  <div id="amtgo-map" data-base="../assets/generated/map/" role="region" aria-label="Carte de l'Afrique : pays actuels et maillages d'analyse"></div>
  <aside id="amtgo-panel" class="amtgo-panel">
    <h3>Couches</h3>
    <div id="amtgo-layers"></div>
    <h3>Découpages candidats</h3>
    <div id="amtgo-candidates" class="amtgo-status">chargement…</div>
    <h3>Provenance</h3>
    <div id="amtgo-meta" class="amtgo-meta">chargement…</div>
  </aside>
</div>

<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
<script src="../assets/carte.js"></script>
