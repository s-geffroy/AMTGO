"""Rapport Markdown automatique d'un run (prompt §73).

Les sections absentes à ce stade du projet sont présentes et déclarées
« non disponible » : un rapport qui omet une section laisse croire qu'elle a
été traitée. Formulation conforme à 06 §15 (jamais « AMTGO prouve que… »).
"""

from __future__ import annotations

from typing import Any

from amtgo.core.enums import ComputabilityClass, RecommendationStatus
from amtgo.core.provenance import ProvenanceRecord
from amtgo.manifests.run import RunManifest

_NA = "_Non disponible à ce stade (milestone {m}) — rien n'est supposé à la place._"


def render_report(
    manifest: RunManifest,
    sources: dict[str, Any],
    meshes: dict[str, Any],
    multiscale: dict[str, Any],
    status: RecommendationStatus,
    computability: ComputabilityClass,
    outputs_hash: str,
    provenance: list[ProvenanceRecord],
    measurement: dict[str, Any] | None = None,
) -> str:
    req = manifest.request
    L: list[str] = []
    a = L.append
    a(f"# Rapport de run — `{req.name}`\n")
    a("> Rapport généré automatiquement. AMTGO est un outil d'aide à la décision : il ne "
      "possède aucune autorité constitutionnelle, et aucune adoption ne peut être inférée "
      "par le modèle.\n")

    a("## Run identity\n")
    a("| champ | valeur |\n|---|---|")
    a(f"| run_id | `{manifest.run_id}` |")
    a(f"| manifest_hash | `{manifest.manifest_hash}` |")
    a(f"| outputs_hash | `{outputs_hash}` |")
    a(f"| code_version | `{manifest.code_version}` |")
    a(f"| région | {req.region} |")
    a(f"| mode de carte | {req.map_mode.value} |")
    a(f"| seeds | {list(manifest.seeds)} |\n")
    a(req.description.strip() + "\n")

    a("## Data coverage\n")
    a("| source | release | licence | zone | classe d'accès | observations | empreinte |")
    a("|---|---|---|---|---|---|---|")
    for rs in manifest.data_manifest:
        m = rs.manifest
        s = sources[m.source_id]
        a(f"| {m.name} | {m.release} | {m.license.license_id} | {m.data_zone.value} | "
          f"{m.privacy_class.value} | {s['observation_count']} | `{s['observations_hash'][:19]}…` |")
    a("")

    a("## Computability class\n")
    if measurement is None:
        a(f"**{computability.value}** — aucun modèle de mesure dans ce run : aucune "
          "recommandation territoriale n'est possible.\n")
    else:
        per = ", ".join(f"`{k}` {v['field']['computability']}" for k, v in measurement["per_mesh"].items())
        a(f"**{computability.value}** pour la variable mesurée (classe la plus défavorable entre "
          f"maillages : {per}). La calculabilité porte ici sur la seule mesure de population ; "
          "elle ne vaut pas recommandation.\n")

    nm = manifest.normative_manifest
    a("## Normative regime\n")
    a(f"Manifeste `{nm.manifest_id}` v{nm.version} (`{manifest.normative_manifest_hash[:19]}…`). "
      f"Hard rights non relaxables : {', '.join(h.right_id for h in nm.hard_rights)}. "
      f"Accès par défaut : {nm.privacy.default_access.value}.\n")

    r = manifest.constitutional_regime
    a("## Constitutional regime\n")
    a(f"`{r.regime_id.value}` — {r.name} v{r.version}. {r.description} "
      "Toute conclusion de ce run est conditionnelle à ce régime.\n")

    a("## Scenario set\n")
    a(_NA.format(m="M6") + "\n")
    a("## Ontology set\n")
    a(_NA.format(m="M4") + "\n")

    a("## Meshes and multi-scale checks\n")
    a("| maillage | famille | résolution | cellules | surface (km²) | couverture emprise "
      "| masse ponctuelle (entrée) | non affectée |")
    a("|---|---|---|---|---|---|---|---|")
    for mid, meta in meshes.items():
        d = meta["definition"]
        ms = multiscale["meshes"][mid]
        mass_in = ms.get("point_mass_in")
        unalloc = ms.get("point_mass_unallocated")
        a(f"| {mid} | {d['family']} | {d['resolution']} | {meta['cell_count']} | "
          f"{meta['total_area_km2']:.0f} | {ms['extent_coverage']:.3f} | "
          f"{'—' if mass_in is None else f'{mass_in:.1f}'} | "
          f"{'—' if unalloc is None else f'{unalloc:.1f}'} |")
    a("")
    for t in multiscale["transfers"]:
        a(f"- transfert `{t['from']}` → `{t['to']}` : masse {t['mass_in']:.1f} → "
          f"{t['mass_out']:.1f} (non affectée : {t['unallocated']:.1f})")
    a("\nS_scale n'est pas calculé : il porte sur des partitions candidates, qui n'existent "
      "qu'à partir de M8.\n")

    a("## Measurement uncertainty\n")
    if measurement is None:
        a("_Aucun modèle de mesure dans ce run._\n")
    else:
        _measurement_section(a, manifest, measurement)
    a("## Causal support\n")
    a("`CAUSAL_EFFECT_UNKNOWN` — bibliothèque causale non construite (M7).\n")
    a("## Pareto summary\n")
    a("Aucun archive de Pareto : aucun candidat n'a été généré (M8–M10). Baselines prévues : "
      "STATUS_QUO, NO_TERRITORIAL_CHANGE, INSTITUTIONAL_ONLY_REFORM.\n")
    a("## Stability summary\n")
    a(_NA.format(m="M8+") + "\n")
    a("## Privacy status\n")
    worst = max((rs.manifest.privacy_class for rs in manifest.data_manifest), key=lambda c: c.rank)
    a(f"Classe la plus restrictive parmi les sources : **{worst.value}**. Ce rapport ne contient "
      "que des comptes agrégés et des empreintes.\n")

    a("## Recommendation status\n")
    a(f"**{status.value}**. Aucune frontière n'est proposée par ce run.\n")

    a("## Provenance\n")
    a(f"{len(provenance)} transformations enregistrées : "
      + ", ".join(sorted({p.transformation for p in provenance})) + ".\n")

    a("## Epistemic ledger\n")
    a("| | contenu |\n|---|---|")
    know = ["sources, licences, empreintes et provenance de chaque transformation",
            "géométrie des maillages et conservation des transferts"]
    infer = []
    assume = ["les seuils normatifs provisoires du manifeste", "le régime constitutionnel "
              f"`{manifest.constitutional_regime.regime_id.value}` (scénario, non doctrine)"]
    unknown = ["tout effet causal (`CAUSAL_EFFECT_UNKNOWN`)", "toute ontologie identitaire (M4)",
               "toute configuration territoriale préférable"]
    if measurement is not None:
        infer.append("population par cellule (statut MODEL), avec intervalles et ratio d'information")
        assume += ["densité homogène à l'intérieur d'une cellule",
                   "prior de densité indépendant entre cellules (aucune corrélation spatiale)",
                   "données manquantes ignorables (MAR) : aucun modèle de sélection"]
    a(f"| WE KNOW | {'; '.join(know)} |")
    a(f"| WE INFER | {'; '.join(infer) or '—'} |")
    a(f"| WE ASSUME | {'; '.join(assume)} |")
    a(f"| WE DO NOT KNOW | {'; '.join(unknown)} |\n")

    a("## Known limitations\n")
    a("- Le noyau de géomasquage est uniforme et déterministe (64 positions).")
    if measurement is not None:
        a("- Modèle gaussien sur des comptes : des tirages négatifs sont possibles ; les cellules "
          "concernées au-delà du seuil sont classées D.")
        a("- Pas de corrélation spatiale a priori : une cellule sans observation garde son prior.")
    a("- Les cellules H3 ne s'emboîtent qu'approximativement d'un niveau à l'autre.")
    a("- Les seuils normatifs du manifeste par défaut sont provisoires (gouvernance, 06 §6).")
    return "\n".join(L) + "\n"


def _fmt(x: float | None) -> str:
    return "—" if x is None else f"{x:,.0f}".replace(",", " ")


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{100 * x:.1f} %"


def _measurement_section(a: Any, manifest: RunManifest, m: dict[str, Any]) -> None:
    mm = manifest.measurement_model
    assert mm is not None
    a(f"Modèle `{mm.model_id}` v{mm.version} (`{mm.content_hash[:19]}…`), statut de preuve "
      f"**MODEL**, période {mm.target_period.start} → {mm.target_period.end}. "
      f"Gel de mesure : `{m['freeze']['freeze_hash'][:19]}…`.\n")
    a("| maillage | cellules | total (moyenne) | intervalle | ratio d'information médian "
      "| cellules mal spécifiées | observations utilisées | exclues |")
    a("|---|---|---|---|---|---|---|---|")
    for mid, v in m["per_mesh"].items():
        f = v["field"]
        t = f["total"]
        used = ", ".join(f"{k} {n}" for k, n in f["used"].items())
        excl = ", ".join(f"{k} {n}" for k, n in f["excluded"].items()) or "—"
        a(f"| {mid} | {f['cells']} | {_fmt(t['mean'])} | [{_fmt(t['lower'])} ; {_fmt(t['upper'])}] | "
          f"{f['median_information_ratio']:.2f} | {f['misspecified_cells']} | {used} | {excl} |")
    a("")
    a("### Validation (05 §4)\n")
    a("| maillage | holdout : couverture | calibration (vérité) : couverture cellules | "
      "cellules informées | total vrai couvert | erreur relative du total |")
    a("|---|---|---|---|---|---|")
    for mid, v in m["per_mesh"].items():
        h, c = v["validation"]["holdout"], v["validation"]["calibration"]
        hc = _pct(h.get("coverage")) if h.get("status") == "done" else "n/d"
        if c.get("status") == "done":
            a(f"| {mid} | {hc} | {_pct(c['cell_coverage'])} | {_pct(c['cell_coverage_informed'])} "
              f"({c['informed_cells']}) | {'oui' if c['total_covered'] else '**non**'} | "
              f"{_pct(c['total_relative_error'])} |")
        else:
            a(f"| {mid} | {hc} | n/d ({c.get('reason')}) | — | — | — |")
    a("")
    first = next(iter(m["per_mesh"].values()))["validation"]
    a("**Ablation de sources** (premier maillage) :\n")
    a("| sources | total | intervalle | ratio d'information médian |\n|---|---|---|---|")
    for k, v in first["ablation"].items():
        lo, hi = v["total_interval"]
        a(f"| {k} | {_fmt(v['total_mean'])} | [{_fmt(lo)} ; {_fmt(hi)}] | {v['median_information_ratio']:.2f} |")
    a("")
    dis = first["disagreement"]
    if dis.get("status") == "not_available":
        a(f"**Désaccord inter-sources** : non disponible ({dis.get('reason')}).\n")
    else:
        a("**Désaccord inter-sources** (chaque source prédite par les autres) : " + "; ".join(
            f"`{k}` |z|>2 : {_pct(v['share_abs_z_gt_2'])}, max |z| {v['max_abs_z']:.1f}" for k, v in dis.items())
          + ".\n")
    cmp_ = m["comparison"]
    if cmp_.get("status") == "done":
        a("**Information selon l'échelle** — ratio d'information médian des totaux sur la grille "
          "de référence de 100 km, et classe correspondante : " + "; ".join(
              f"`{k}` {v['median']:.2f} ({v['computability']})"
              for k, v in cmp_["reference_scale_information"].items()) + ". Une population non "
          "identifiée par cellule peut l'être à une échelle plus large : la classe de zone ci-dessus "
          "porte sur la cellule.\n")
        a(f"**Comparaison entre maillages** (totaux des {cmp_['polygons']} cellules d'une grille de "
          f"référence de 100 km, indépendante des marges, reconstruits depuis chaque maillage) : "
          f"écart standardisé maximal **{cmp_['max_abs_z']:.2f}**.\n")
