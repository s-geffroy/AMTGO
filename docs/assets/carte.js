// Carte AMTGO : rendu des couches exportees par `amtgo export pages-map`.
// Aucun fond de tuiles externe : seules nos couches, avec leur provenance.
(function () {
  "use strict";
  const el = document.getElementById("amtgo-map");
  if (!el || typeof maplibregl === "undefined") return;
  const base = el.dataset.base;
  // URL absolue : MapLibre charge les GeoJSON dans un web worker, qui ne résout pas un chemin
  // relatif par rapport à la page (couches vides, sans erreur visible).
  const url = (f) => new URL(base + f, document.baseURI).href;
  const css = (name) => getComputedStyle(document.body).getPropertyValue(name).trim() ||
    getComputedStyle(document.documentElement).getPropertyValue(name).trim();

  const fetchJSON = (f) => fetch(url(f)).then((r) => {
    if (!r.ok) throw new Error(f + " : HTTP " + r.status);
    return r.json();
  });

  const text = (node, s) => { node.textContent = s; return node; };

  fetchJSON("index.json").then((index) => {
    renderMeta(index);
    return Promise.all([index, fetchJSON("candidates.json")]);
  }).then(([index, candidates]) => {
    renderCandidates(candidates);
    buildMap(index);
  }).catch((err) => {
    text(document.getElementById("amtgo-meta"), "Couches non générées dans cette version du site (" + err.message + ").");
    text(document.getElementById("amtgo-candidates"), "—");
  });

  function renderMeta(index) {
    const m = document.getElementById("amtgo-meta");
    m.innerHTML = "";
    const a = index.attribution[0];
    const p1 = document.createElement("p");
    text(p1, a.citation + " Licence : " + a.license + ".");
    const p2 = document.createElement("p");
    text(p2, "run " + index.run_id + " — " + index.outputs_hash.slice(0, 19) + "…");
    m.append(p1, p2);
  }

  function renderCandidates(c) {
    const box = document.getElementById("amtgo-candidates");
    box.innerHTML = "";
    const status = document.createElement("p");
    status.innerHTML = "Statut : <code></code>";
    text(status.querySelector("code"), c.status);
    const msg = document.createElement("p");
    text(msg, c.candidates.length ? c.candidates.length + " configuration(s)." : c.message);
    box.append(status, msg);
  }

  function buildMap(index) {
    const map = new maplibregl.Map({
      container: el,
      style: { version: 8, sources: {}, layers: [
        { id: "bg", type: "background", paint: { "background-color": css("--amtgo-bg") } },
      ] },
      center: [20, 3], zoom: 2.3, minZoom: 1.5, maxZoom: 8,
      attributionControl: { customAttribution: "Natural Earth (domaine public) · AMTGO" },
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.addControl(new maplibregl.ScaleControl({ unit: "metric" }));

    map.on("load", () => {
      const toggles = [];
      const files = Object.fromEntries(index.layers.map((l) => [l.id, l]));
      map.addSource("countries", { type: "geojson", data: url(files.countries.file) });
      map.addSource("boundaries", { type: "geojson", data: url(files.boundaries.file) });
      map.addLayer({ id: "countries-fill", type: "fill", source: "countries",
        paint: { "fill-color": css("--amtgo-country-fill") } });
      map.addLayer({ id: "countries-outline", type: "line", source: "countries",
        paint: { "line-color": css("--amtgo-country"), "line-width": 0.6 } });
      map.addLayer({ id: "boundaries-defacto", type: "line", source: "boundaries",
        filter: ["!", ["get", "disputed"]],
        paint: { "line-color": css("--amtgo-border"), "line-width": 1.1 } });
      map.addLayer({ id: "boundaries-disputed", type: "line", source: "boundaries",
        filter: ["get", "disputed"],
        paint: { "line-color": css("--amtgo-disputed"), "line-width": 1.4, "line-dasharray": [2, 2] } });
      toggles.push(["Pays actuels (de facto)", ["countries-fill", "countries-outline", "boundaries-defacto"], css("--amtgo-border"), true, false]);
      toggles.push(["Frontières disputées / indéfinies", ["boundaries-disputed"], css("--amtgo-disputed"), true, true]);

      index.layers.filter((l) => l.id.startsWith("mesh_")).forEach((l) => {
        const color = l.family === "h3" ? css("--amtgo-h3") : css("--amtgo-grid");
        map.addSource(l.id, { type: "geojson", data: url(l.file) });
        map.addLayer({ id: l.id, type: "line", source: l.id,
          layout: { visibility: "none" }, paint: { "line-color": color, "line-width": 0.5, "line-opacity": 0.8 } });
        const label = (l.family === "h3" ? "Maillage H3 r" : "Grille LAEA niv. ") + l.resolution +
          " (" + l.count + " cellules, analyse)";
        toggles.push([label, [l.id], color, false, false]);
      });

      const holder = document.getElementById("amtgo-layers");
      holder.innerHTML = "";
      toggles.forEach(([label, ids, color, on, dashed]) => {
        const row = document.createElement("label");
        const cb = document.createElement("input");
        cb.type = "checkbox"; cb.checked = on;
        cb.addEventListener("change", () => ids.forEach((id) =>
          map.setLayoutProperty(id, "visibility", cb.checked ? "visible" : "none")));
        const sw = document.createElement("span");
        sw.className = "amtgo-swatch" + (dashed ? " dashed" : "");
        if (!dashed) sw.style.background = color;
        row.append(cb, sw, document.createTextNode(label));
        holder.append(row);
      });

      map.on("click", "countries-fill", (e) => {
        const p = e.features[0].properties;
        const div = document.createElement("div");
        const b = document.createElement("strong");
        text(b, p.name_fr || p.name);
        div.append(b);
        if (p.note) { const n = document.createElement("div"); text(n, "Note Natural Earth : " + p.note); div.append(n); }
        new maplibregl.Popup().setLngLat(e.lngLat).setDOMContent(div).addTo(map);
      });
    });
  }
})();
