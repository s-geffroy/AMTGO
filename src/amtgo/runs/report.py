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
    s2c: dict[str, Any] | None = None,
    causal: dict[str, Any] | None = None,
    candidates: dict[str, Any] | None = None,
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
    a(f"Règles : libre circulation {r.mobility_rules.free_movement:.2f}, intégration du marché "
      f"{r.market_rules.market_integration:.2f}, péréquation {r.fiscal_transfer_rules.equalization_rate:.2f}, "
      f"recettes mises en commun {r.fiscal_transfer_rules.pooled_revenue_share:.2f}, défense mutualisée "
      f"{r.defence_rules.common_defence_share:.2f}, infrastructures communes "
      f"{r.infrastructure_rules.common_infrastructure_share:.2f} (valeurs provisoires). Frontière entre États "
      "σ = " + ", ".join(f"{k} {v:.2f}" for k, v in r.border_template.items())
      + " (E, M, R, S dérivées des règles).\n")

    a("## Scenario set\n")
    if not manifest.scenario_set:
        a("_Aucun scénario dans ce run : aucune conclusion de viabilité n'est possible (prompt §29)._\n")
    else:
        _scenario_section(a, manifest, s2c)
    a("## Ontology set\n")
    comp_ = None if measurement is None else measurement.get("composition")
    if not manifest.ontology_set:
        a("_Aucune ontologie dans ce run._\n")
    else:
        a("| ontologie | dimension | type | statut de preuve | concepts |\n|---|---|---|---|---|")
        for o in manifest.ontology_set:
            a(f"| `{o.ontology_id}` v{o.version} | {o.dimension.value} | {o.kind.value} | "
              f"{o.evidence_status.name} | {len(o.leaf_ids)} |")
        a("")
        for cw in manifest.crosswalks:
            a(f"Crosswalk `{cw.crosswalk_id}` : `{cw.source_ontology}` → `{cw.target_ontology}`, "
              f"statut {cw.evidence_status.name}, probabiliste (Dirichlet), masse non attribuée conservée.\n")
        if comp_ is not None:
            _composition_section(a, manifest, comp_)

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
    a("## Domination, fragmentation, integration\n")
    dfi = None if measurement is None else measurement.get("dfi")
    if dfi is None:
        a(_NA.format(m="M5") + "\n")
    else:
        _dfi_section(a, manifest, dfi)
    a("## Contextual viability\n")
    via = None if measurement is None else measurement.get("viability")
    if via is None:
        a("_Aucun modèle de viabilité dans ce run. Aucune viabilité n'est jamais énoncée hors "
          "(régime, scénario)._\n")
    else:
        _viability_section(a, manifest, via)

    a("## Candidate generation\n")
    if candidates is None:
        a("_Aucun générateur de candidats dans ce run._\n")
    else:
        _candidate_section(a, manifest, candidates)

    a("## Institutional composition (fixed geometry)\n")
    if candidates is None or "composer" not in candidates:
        a("_Aucun composeur institutionnel dans ce run._\n")
    else:
        _composer_section(a, manifest, candidates["composer"])

    a("## Causal support\n")
    if causal is None:
        a("`CAUSAL_EFFECT_UNKNOWN` — aucune bibliothèque causale dans ce run.\n")
    else:
        _causal_section(a, manifest, causal)
    a("## Pareto summary\n")
    if candidates is None:
        a("Aucune archive de Pareto : aucun candidat n'a été généré. Baselines prévues : "
          "STATUS_QUO, NO_TERRITORIAL_CHANGE, INSTITUTIONAL_ONLY_REFORM.\n")
    elif "pareto" not in candidates:
        a("Aucune archive de Pareto : les candidats sont générés mais **non évalués**. Les trois baselines "
          "sont présentes.\n")
    else:
        _pareto_section(a, manifest, candidates["pareto"])
    if candidates is not None and "validation" in candidates:
        a("## Validation & red-team\n")
        _validation_section(a, candidates["validation"])
    if candidates is not None and "map_r" in candidates:
        a("## Map-R (régional)\n")
        _map_r_section(a, candidates["map_r"])
    a("## Stability summary\n")
    if candidates is None:
        a(_NA.format(m="M8+") + "\n")
    else:
        e = candidates["ensemble"]
        n = len(e["variants"])
        stable = sum(1 for v in e["variants"].values() if v["stable"])
        a(f"{stable} variante(s) sur {n} atteignent S^scale ≥ τ_scale = {e['scale_min']} (distance TRANSFER "
          f"entre maillages, grille `{e['reference_mesh']}`). La stabilité est nécessaire, jamais suffisante : "
          "elle ne dit rien de la valeur d'un candidat.\n")
    a("## Privacy status\n")
    worst = max((rs.manifest.privacy_class for rs in manifest.data_manifest), key=lambda c: c.rank)
    a(f"Classe la plus restrictive parmi les sources : **{worst.value}**. Ce rapport ne contient "
      "que des comptes agrégés et des empreintes.\n")
    if manifest.composition_model is not None:
        a("Les champs de composition portent des attributs de groupe : classe **CONTROLLED** au "
          "minimum, jamais exportés publiquement. Seuls des agrégats de domaine et des mesures "
          "entre ontologies figurent ici ; aucune part par cellule.\n")

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
    unknown = ["tout effet causal hors bibliothèque gelée (`CAUSAL_EFFECT_UNKNOWN`)",
               "toute ontologie identitaire (M4)",
               "toute configuration territoriale préférable"]
    if manifest.viability_model is not None:
        vm = manifest.viability_model
        infer.append("couverture du panier de services des juridictions du statu quo, par (régime, scénario)")
        assume += [f"comptes fiscaux observés sous `{vm.observed_regime}`", vm.union_closure,
                   "coûts fixes de souveraineté déclarés (provisoires)",
                   "scénarios : axes uniformes sur la région, intervalles déclarés"]
        unknown += ["élasticité de la base fiscale à l'accès au marché et effet des infrastructures "
                    "communes (bornes exploratoires I7, non causales)",
                    "réponse de mobilité volontaire à une réforme (S2A : CAUSAL_EFFECT_UNKNOWN)"]
    if any(not sc.climate.modelled for sc in manifest.scenario_set):
        unknown.append("climat dans les scénarios où il n'est pas modélisé")
    if causal is not None:
        facts = [k for k, v in causal["effects"].items() if v["status"] == "CAUSAL_FACT"]
        if facts:
            infer.append("effets estimés et admis de la bibliothèque gelée : " + ", ".join(f"`{k}`" for k in facts))
        assume.append("tendances parallèles et absence d'anticipation des designs DiD (testées, non prouvées)")
        rejected = [k for k, v in causal["effects"].items() if v["status"] == "CAUSAL_EFFECT_UNKNOWN"]
        if rejected:
            unknown.append("effets rejetés ou non transportables : " + ", ".join(f"`{k}`" for k in rejected))
    if manifest.dfi_model is not None:
        infer.append("D/F/I du statu quo déclaré (statut MODEL)")
        assume += ["qualité des contacts intergroupes uniforme (non mesurée)",
                   "liens sociaux décrits par un noyau de distance déclaré",
                   "identités statiques sur l'horizon évalué"]
        unknown += ["D^real (aucune observation de discrimination)",
                    "fragmentation territoriale, de mobilité, culturelle, institutionnelle (canaux sans données)"]
    if manifest.composition_model is not None:
        infer.append("parts de catégories par cellule sous chaque ontologie (statut MODEL)")
        assume += ["indépendance a posteriori entre population et composition",
                   "réponses d'une cellule comptées aux niveaux cellule et région (approximation)",
                   "crosswalks entre ontologies (statut MODEL, preuve déclarée)"]
        unknown = [u for u in unknown if "ontologie" not in u] + [
            "la « bonne » ontologie : aucune n'est canonique"]
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


def _composition_section(a: Any, manifest: RunManifest, comp: dict[str, Any]) -> None:
    cm = manifest.composition_model
    assert cm is not None
    a(f"Composition : modèle `{cm.model_id}` v{cm.version}, dimension {cm.dimension.value}, "
      f"observée sous `{cm.observed_ontology}`. **Parts seulement** : aucune étiquette, aucune "
      "majorité, aucun « groupe de la cellule ».\n")
    first = next(iter(comp["per_mesh"].values()))
    if first["calibration"].get("status") == "done":
        # Monde synthétique (vérité disponible) : catégories fictives, agrégats de domaine publiables.
        a("Parts au niveau du domaine (premier maillage, monde synthétique) :\n")
        for oid, v in first["ontologies"].items():
            parts = ", ".join(f"{k} {100 * x['mean']:.1f} %" for k, x in v["domain_shares"].items())
            a(f"- `{oid}` : {parts}")
        a("")
    else:
        a("_Parts de groupes non reproduites : sources réelles, champs CONTROLLED._\n")
    a("| maillage | S^ontology | calibration à 100 km (couverture) | erreur absolue moyenne | "
      "part couverte par l'étiquette historique |")
    a("|---|---|---|---|---|")
    for mid, v in comp["per_mesh"].items():
        c, h = v["calibration"], v["historical_label_check"]
        cov = f"{100 * c['reference_coverage']:.1f} %" if c.get("status") == "done" else "n/d"
        mae = f"{c['reference_mean_abs_error']:.3f}" if c.get("status") == "done" else "n/d"
        lab = next((x for k, x in h.items() if isinstance(x, dict)), None) if h.get("status") == "done" else None
        labs = f"{100 * lab['mean_label_share']:.0f} % (min {100 * lab['min_label_share']:.0f} %)" if lab else "n/d"
        a(f"| {mid} | {v['ontology_stability']['s_ontology']:.2f} | {cov} | {mae} | {labs} |")
    a("")
    s = comp["ensemble"]["s_ontology"]
    a(f"**S^ontology = {s:.2f}** (corrélation de rang du motif de diversité entre ontologies, "
      "minimum sur les maillages). Toute conclusion portant sur des catégories est conditionnelle "
      "à l'ontologie ; une carte historique à étiquette unique ne représente qu'une fraction de la "
      "population de chaque bloc.\n")


def _dfi_section(a: Any, manifest: RunManifest, dfi: dict[str, Any]) -> None:
    sq = manifest.status_quo
    assert sq is not None
    first = next(iter(dfi["per_mesh"].values()))
    levels = ", ".join(f"{v} {k}" for k, v in first["jurisdictions"].items())
    a(f"Évaluation du **statu quo déclaré** `{sq.status_quo_id}` ({levels}) "
      f"sous le régime `{first['regime']}`. Ce n'est pas une proposition : c'est la baseline "
      "STATUS_QUO / NO_TERRITORIAL_CHANGE. Champs de groupe : CONTROLLED ; seuls des agrégats figurent ici.\n")
    a("| maillage | ontologie | J_conn | F réseau (pondéré) | max P(D > τ) | violations | alignement |")
    a("|---|---|---|---|---|---|---|")
    for mid, v in dfi["per_mesh"].items():
        for oid, x in v["ontologies"].items():
            h = x["headline"]
            a(f"| {mid} | `{oid}` | {h['j_conn']:.2e} | {h['f_network_popweighted']:.2e} | "
              f"{h['max_p_exceed']:.2f} | {x['domination']['violations']} | {x['alignment']['mean']:.2f} |")
    a("")
    unknown = sorted(set(first["ontologies"][next(iter(first["ontologies"]))]["unknown_fragmentation_channels"]))
    a(f"Canaux de fragmentation **UNKNOWN** (sans données, jamais comptés comme nuls) : {', '.join(unknown)}. "
      "Composante réalisée de la domination : **UNKNOWN** (aucune observation de discrimination).\n")
    e = dfi["ensemble"]
    a(f"**S^ontology (D/F/I) = {e['s_ontology_dfi']:.2f}**, **S^scale (D/F/I) = {e['s_scale_dfi']:.2f}** "
      f"(1 − écart relatif maximal, plancher numérique {e['relative_floor']}).")
    for o, gaps in e["scale_gaps_raw"].items():
        flagged = [f"{k} : écart relatif brut {g['relative']:.2f}" for k, g in gaps.items()
                   if g["below_floor"] and g["relative"] > 0]
        if flagged:
            a(f"- `{o}` — sous le plancher, la stabilité n'est jugée qu'en absolu : " + "; ".join(flagged) + ".")
    a("")
    rri = next(iter(first["ontologies"].values()))["reification"]
    a(f"Risque de réification du statu quo par rapport à lui-même : {rri['status']} "
      "(Δ d'alignement nul par construction ; les bornes sont exploratoires, non causales).\n")


def _scenario_section(a: Any, manifest: RunManifest, s2c: dict[str, Any] | None) -> None:
    a("| scénario | mobilité | horizon | climat | axes maintenus | garde-fous |")
    a("|---|---|---|---|---|---|")
    for sc in manifest.scenario_set:
        climate = (", ".join(sorted(sc.climate.pathways)) if sc.climate.modelled else "**non modélisé**")
        guards = {"S1": "aucun déplacement induit", "S2A": "volontaire seulement ; réponse CAUSAL_EFFECT_UNKNOWN"
                  if sc.migration.voluntary_response is None else "volontaire seulement",
                  "S2C": "diagnostic agrégé uniquement"}[sc.mobility_regime.value]
        a(f"| `{sc.scenario_id}` v{sc.version} | {sc.mobility_regime.value} | {sc.horizon_years} ans | {climate} | "
          f"{', '.join(sc.held_axes()) or '—'} | {guards} |")
    a("")
    a("Déplacement forcé et relocalisation induite par une réforme : **0**, vérifiés au chargement et à "
      "l'exécution (prompt §35). Un axe maintenu est une hypothèse de scénario, déclarée.\n")
    if s2c:
        for sid, d in s2c.items():
            a(f"S2C `{sid}` : **{d['status']}** — {d['reason']}. Sorties possibles : agrégats seulement "
              f"({', '.join(d['outputs_allowed'])}). Jamais : {', '.join(d['outputs_forbidden'])}.\n")


def _viability_section(a: Any, manifest: RunManifest, via: dict[str, Any]) -> None:
    vm = manifest.viability_model
    assert vm is not None
    e = via["ensemble"]
    first = next(iter(via["per_mesh"].values()))
    th = first["thresholds"]
    a(f"Couverture du panier de services des juridictions de niveau `{vm.level}` du statu quo : "
      f"viable si P(couverture < {th['service_coverage_min']}) ≤ {th['shortfall_probability_max']}. "
      "Aucun seuil de taille, de surface ni d'autarcie. Chaque statut ne vaut que sous son régime et son scénario.\n")
    regimes = e["regimes"]
    a("| scénario | territoire | " + " | ".join(f"`{r}`" for r in regimes) + " | dépend du régime |")
    a("|---|---|" + "---|" * len(regimes) + "---|")
    for sid, by_t in e["status_by_scenario_territory_regime"].items():
        for t, by_r in by_t.items():
            a(f"| `{sid}` | {t} | " + " | ".join(by_r[r] for r in regimes)
              + f" | {'**oui**' if e['regime_dependent'][sid][t] else 'non'} |")
    a("")
    mid = next(iter(via["per_mesh"]))
    a(f"Détail sur `{mid}` (couverture moyenne et intervalle à 90 %, transferts nets en part du coût des services) :\n")
    for by_r in first["assessments"].values():
        for by_t in by_r.values():
            for a_ in by_t.values():
                a(f"- {a_['statement']}")
    a("")
    a(f"**S^scale (viabilité) = {e['s_scale_viability']:.2f}** "
      "(1 − écart maximal de P(couverture < τ) entre maillages).")
    if e["exploratory_dependent"]:
        a(f"{len(e['exploratory_dependent'])} statut(s) changent entre les bornes des coefficients exploratoires "
          "(non causaux) : ils ne sont pas des conclusions.")
    if any(v for by_t in e["regime_dependent"].values() for v in by_t.values()):
        a("La viabilité d'au moins un territoire **dépend du régime constitutionnel** : toute analyse de "
          "souveraineté doit annoncer le régime (spec 14 §6, 05 §19).")
    a("")


def _causal_section(a: Any, manifest: RunManifest, causal: dict[str, Any]) -> None:
    lib = manifest.causal_library
    assert lib is not None
    val = causal["validation"]
    a(f"Bibliothèque `{lib.library_id}` v{lib.version}, **gelée** avant toute évaluation qui la consomme "
      f"(`{causal['freeze_hash'][:19]}…`). Le solveur ne peut ajuster aucun effet. Contexte cible : "
      f"`{manifest.request.region}`.\n")
    a("| effet | traitement | résultat | design | grade | transport (recouvrement) | statut | effet (IC 90 %) |")
    a("|---|---|---|---|---|---|---|---|")
    for k, e in causal["effects"].items():
        eff = e["effect"]
        shown = "—" if eff is None else (
            f"[{eff['lower']:.3g}, {eff['upper']:.3g}]" if eff["mean"] is None
            else f"{eff['mean']:.3g} [{eff['lower']:.3g}, {eff['upper']:.3g}]")
        a(f"| `{k}` | {e['treatment']} | {e['outcome']} | {e['design']} | {e['grade']} | "
          f"{e['transport']} ({e['overlap']:.2f}) | **{e['status']}** | {shown} |")
    a("")
    for k, e in causal["effects"].items():
        failed = [d for d, v in e["diagnostics"].items() if v == "FAILED"]
        failed += [r for r, v in e["robustness"].items() if v == "FAILED"]
        if failed:
            a(f"- `{k}` : **rejeté** — échecs : {', '.join(sorted(failed))}. Réponse : `CAUSAL_EFFECT_UNKNOWN`.")
        elif e["status"] == "EXPLORATORY_ONLY":
            a(f"- `{k}` : hypothèse d'expert (I7) — bornes exploratoires, jamais un fait causal.")
    a("")
    for k, v in val["estimations"].items():
        t = v.get("synthetic_truth")
        if t is not None:
            verdict = "couverte" if t["covered"] else "**non couverte** (estimation biaisée)"
            note = " ; l'effet a été rejeté par ses diagnostics" if v["admissibility"] == "UNSUPPORTED" else ""
            a(f"- `{k}` : vérité synthétique {t['att']:.4f} — {verdict} par l'intervalle estimé "
              f"(avant élargissement de transport){note}.")
    a("")
    a(f"**Gate C : {val['gate_c']}** — tout effet admis passe chaque test exécuté (région exclue, placebo, "
      "contrôle négatif, vérité synthétique). Aucune affirmation causale sans grade (A5).\n")


def _candidate_section(a: Any, manifest: RunManifest, cand: dict[str, Any]) -> None:
    cm = manifest.candidate_model
    assert cm is not None
    e = cand["ensemble"]
    a(f"Générateur `{cm.generator_id}` v{cm.version}. Les candidats sont des **unités analytiques**, non "
      "évaluées, jamais des propositions. Ils sont fondés sur la population gelée et la géographie seulement "
      "(aucune part de groupe), et ne sont pas publiés.\n")
    a("| famille | paramètres | États par maillage | S^scale | stable | contigu partout |")
    a("|---|---|---|---|---|---|")
    for v in e["variants"].values():
        params = ", ".join(f"{k}={x}" for k, x in v["params"].items()) or "—"
        states = ", ".join(str(x) for x in v["n_states_by_mesh"].values())
        s = "—" if v["s_scale"] is None else f"{v['s_scale']:.2f}"
        stable = "—" if v["stable"] is None else ("oui" if v["stable"] else "**non**")
        contiguous = "oui" if v["contiguous_everywhere"] else "non"
        a(f"| {v['family']} | {params} | {states} | {s} | {stable} | {contiguous} |")
    a("")
    for fam, why in e["unavailable_families"].items():
        a(f"- {fam} : **NOT_AVAILABLE** — {why}.")
    a("")
    a("Baselines : STATUS_QUO (rien ne change), NO_TERRITORIAL_CHANGE (seule l'application des droits peut "
      "varier), INSTITUTIONAL_ONLY_REFORM (compétences recomposées à géométrie fixe, M9). Le nombre d'États est "
      "balayé, jamais pénalisé ; une union (1 État) fait partie du balayage.\n")


def _fmt_rri(r: list[float] | None) -> str:
    return "UNKNOWN" if r is None else f"[{r[0]:.2g}, {r[1]:.2g}]"


def _composer_section(a: Any, manifest: RunManifest, comp: dict[str, Any]) -> None:
    cm = manifest.composer_model
    assert cm is not None
    e = comp["ensemble"]
    a(f"Composeur `{cm.composer_id}` v{cm.version} : leviers testés sur la géométrie du statu quo, dans l'ordre "
      "de recherche du §39, seuls puis cumulés, aux deux bornes de leur efficacité (bibliothèque gelée). "
      "Recherche institutionnelle **avant** toute frontière.\n")
    a(f"**Conclusion : {e['conclusion']}** ({e['stability']})"
      + (f" — levier minimal : `{e['chosen']}`" if e["chosen"] else "") + ".\n")
    mid = next(iter(comp["per_mesh"]))
    first = comp["per_mesh"][mid]
    for oid, res in first["ontologies"].items():
        b = res["baseline"]
        a(f"`{mid}`, ontologie `{oid}` — statu quo : {b['violations']} violation(s), max P(D > τ) "
          f"{b['max_p_exceed']:.2f}, coût {b['cost']:.1f}.\n")
        a("| option | statut | violations (borne basse) | F réseau | J_conn | RRI | coût | complexité | grades |")
        a("|---|---|---|---|---|---|---|---|---|")
        for o in res["options"]:
            lo = o["lo"]
            if lo is None:
                a(f"| {o['option']} | **{o['status']}** | — | — | — | — | — | — | {', '.join(o['grades']) or '—'} |")
                continue
            jc = "—" if lo["j_conn"] is None else f"{lo['j_conn']:.2e}"
            a(f"| {o['option']} | {o['status']} | {lo['violations']} | {lo['f_network']:.2e} | {jc} | "
              f"{_fmt_rri(o['hi']['rri'])} | {lo['cost']:.1f} | {lo['complexity']} | {', '.join(o['grades'])} |")
        a("")
        a(f"Non dominés (vue robuste) : {', '.join(f'`{x}`' for x in res['non_dominated'])}. Renvoyés à la "
          f"recherche territoriale (M10) : {', '.join(res['deferred_to_territorial_search']) or '—'}.\n")
        break
    a("Les efficacités sont des hypothèses d'expert (I7) : toute conclusion du composeur est **exploratoire**. "
      "NO_CHANGE ou NO_TERRITORIAL_CHANGE_SUFFICIENT sont des résultats valides et attendus (01 §31) ; "
      "INSTITUTIONAL_INSUFFICIENT_AT_FIXED_GEOMETRY ne serait pas une recommandation de frontière.\n")


def _fmt_obj(x: float | None) -> str:
    return "UNKNOWN" if x is None else f"{x:.3g}"


def _pareto_section(a: Any, manifest: RunManifest, p: dict[str, Any]) -> None:
    rw = p["robustness"]
    a(f"Archive de Pareto **robuste** : ρ(J) = E_ω[J] + {rw['lambda_tail']}·CVaR_{rw['cvar_alpha']}(J) + "
      f"{rw['lambda_var']}·Var_ω(J) sur ω = (maillage × ontologie) ; ε-dominance ; contrainte de droits dure. "
      "Aucune pondération entre objectifs, aucune « meilleure solution ». Institutions : gabarit du statu quo, "
      "recomposé par le composeur (J_pkg) quand la géométrie viole la contrainte de droits.\n")
    a(f"**Conclusion : {p['conclusion']}**.")
    if p["improving_on_status_quo"]:
        a("Variantes qui font au moins aussi bien que le statu quo partout (hors coût de transition) : "
          + ", ".join(f"`{k}`" for k in p["improving_on_status_quo"]) + ". C'est une propriété de l'archive "
          "sous les objectifs modélisés, jamais une recommandation : voir les biais connus ci-dessous.")
    elif p.get("unresolved_dominance"):
        a("Des variantes dominent le statu quo sur les objectifs **connus** (hors transition), mais un objectif "
          "UNKNOWN peut renverser cette dominance : elle n'est pas résolue.\n")
        a("| variante | " + " | ".join(p["unknown_objectives"]) + " |")
        a("|---|" + "---|" * len(p["unknown_objectives"]))
        for name, bounds in p["unresolved_dominance"].items():
            a(f"| `{name}` | " + " | ".join(bounds.get(u, "—") for u in p["unknown_objectives"]) + " |")
        a("\nNOT_BETTER : l'axiome de monotonie par fusion dit que l'objectif ne peut qu'y être pire que pour le "
          "statu quo (fusion d'États) ; UNDETERMINED : aucun axiome ne tranche.")
    else:
        a("Aucune variante ne fait au moins aussi bien que le statu quo sur tous les objectifs (hors coût de "
          "transition) : le statu quo reste sur le front, et rien ne justifie un redécoupage.")
    a("")
    objs = [o for o in p["objectives"]]
    a("| rang | famille | paramètres | faisable | " + " | ".join(f"ρ({o})" for o in objs) + " | S^ont | S^scale |")
    a("|---|---|---|---|" + "---|" * len(objs) + "---|---|")
    for s in p["solutions"]:
        params = ", ".join(f"{k}={v}" for k, v in s["params"].items()) or "—"
        ss = "—" if s["s_scale"] is None else f"{s['s_scale']:.2f}"
        a(f"| {s['rank'] or '—'} | {s['family']} | {params} | {'oui' if s['feasible'] else '**non**'} | "
          + " | ".join(_fmt_obj(s["objectives"][o]) for o in objs) + f" | {s['s_ontology']:.2f} | {ss} |")
    a("")
    if p["infeasibility"]:
        c = p["infeasibility"]
        a(f"**INFEASIBLE** — contraintes liantes : {c['binding_constraints']} ; conflits minimaux : "
          f"{c['minimal_conflict_sets']}. Aucune relaxation appliquée.\n")
    a("Biais connus : " + " ; ".join(p["known_biases"]) + ".\n")
    a(f"Objectifs **UNKNOWN** (jamais comptés à 0) : {', '.join(p['unknown_objectives'])}. ε : "
      + ", ".join(f"{k} {v:g}" for k, v in p["epsilon"].items()) + ".\n")
    b = p["benchmark"]
    a(f"**Gate O : {p['gate_o']}** — benchmark exact sur {b['partitions_enumerated']} bipartitions contiguës "
      f"d'une grille 4×4 fictive, {len(b['seeds'])} départs : k-means, écart à l'optimum {b['kmeans']['best_gap']:.1%} "
      f"(pire départ {max(b['kmeans']['relative_gaps']):.1%}) ; coupe spectrale {b['spectral']['best_gap']:.1%}. "
      f"La coupe seule a pour front exact des micro-territoires ({b['cut_only_front']['smallest_state_cells']} "
      "cellule(s)) : elle n'est jamais un objectif isolé.\n")
    a(f"Publication : {p['publication']}. Statut : **{p['recommendation_status']}**.\n")


def _validation_section(a: Any, v: dict[str, Any]) -> None:
    g = v["gates"]
    a("Gates de publication (05 §20) : " + " ; ".join(f"**{k}** {s}" for k, s in g.items())
      + f". Catégorie : **{v['publication_category']}** — {v['release_note']}.\n")
    a(f"S^publish = min(S^ontology, S^scale, S^time, S^parameter) = "
      f"{'UNKNOWN' if v['s_publish'] is None else format(v['s_publish'], '.2f')} (τ = {v['s_publish_tau']}). "
      f"S^time : {v['s_time']}.\n")
    a("| variante | S^ont | S^scale | S^param | S^publish |")
    a("|---|---|---|---|---|")
    for k, s in v["stability"].items():
        cells = ["—" if s[c] is None else f"{s[c]:.2f}" for c in ("s_ontology", "s_scale", "s_parameter", "s_publish")]
        a(f"| `{v['names'].get(k, k)}` | " + " | ".join(cells) + " |")
    a("")
    sens = v["sensitivity"]
    a("**Sensibilité normative** (05 §18, un paramètre à la fois) :\n")
    a("| paramètre | valeur | conclusion | entrent au front | sortent du front |")
    a("|---|---|---|---|---|")
    for r in sens["settings"]:
        a(f"| {r['parameter']} | {r['value']} | {'**' if r['conclusion_changed'] else ''}{r['conclusion']}"
          f"{'**' if r['conclusion_changed'] else ''} | {len(r['entered_front'])} | {len(r['left_front'])} |")
    a("")
    pc = sens["political_choices"]
    a(("Paramètres qui changent la conclusion — **choix politiques**, pas conclusions scientifiques : "
       + ", ".join(pc) + ".") if pc else "Aucun paramètre testé ne change la conclusion.")
    rg = v["regimes"]
    a(f"\n**Régimes** (05 §19 ; {rg['scope']}) : nominal {rg['nominal']} ; "
      + ", ".join(f"{r} → {x['conclusion']}" for r, x in rg["alternatives"].items())
      + (". La conclusion **dépend du régime**." if rg["regime_dependent"] else ". Conclusion inchangée.") + "\n")
    ms = v["multiscale"]
    a("**Multi-échelle** (05 §5) : " + ", ".join(f"`{m}` → {x['conclusion']} (front {len(x['front'])})"
                                                for m, x in ms["per_mesh"].items())
      + ". Dépendantes d'un seul maillage : "
      + (", ".join(f"`{v['names'].get(k, k)}`" for k in ms["single_mesh_dependent"]) or "aucune")
      + f" ; front variable selon le maillage : {len(ms['mesh_dependent'])} variante(s).\n")
    a("**Ablations** (05 §13) :\n")
    a("| module retiré | statut | conclusion | entrent | sortent |")
    a("|---|---|---|---|---|")
    for x in v["ablations"]:
        if x["status"] != "RUN":
            a(f"| {x['ablation']} | {x['status']} ({x['what']}) | — | — | — |")
            continue
        a(f"| {x['ablation']} | {x['what']} | {x['conclusion']} | {len(x['entered_front'])} | "
          f"{len(x['left_front'])} |")
    a("")
    gh = v["goodhart"]
    a(f"**Goodhart** (05 §14) : {gh['status']}.")
    for r in gh["attacks"]:
        a(f"- `{r['attack']}` : {'faisable' if r['feasible'] else 'infaisable'}, rang {r['rank'] or '—'}, "
          f"signalements {', '.join(r['flags']) or 'aucun'}{' — **faille**' if r['loophole'] else ''}.")
    if gh.get("flagged_variants"):
        a("- variantes signalées pour revue : " + ", ".join(f"`{v['names'].get(k, k)}` ({', '.join(f)})"
                                                        for k, f in gh["flagged_variants"].items()) + ".")
    a("")
    a("**Falsification** (05 §11) : " + " ; ".join(f"{c['control']} {c['status']}" for c in v["falsification"])
      + ".\n")
    p = v["privacy"]
    a(f"**Confidentialité** (05 §15-16) : Gate S {p['gate_s']} — {sum(x['blocked'] for x in p['attacks'])}/"
      f"{len(p['attacks'])} attaques bloquées, contrôles bénins publiés : "
      f"{sum(c['released'] for c in p['benign_controls'])}/{len(p['benign_controls'])}. "
      f"Couches publiables telles quelles : {', '.join(p['public_layers']) or 'aucune'}.\n")


def _map_r_section(a: Any, m: dict[str, Any]) -> None:
    w = m["weights"]
    a("Map-R demande quelle amélioration est réaliste **depuis les institutions présentes** : chaque trajectoire "
      "part du statu quo, monte la hiérarchie contrefactuelle (§79) sans jamais redescendre, et chaque étape est "
      "réévaluée. Pénalité de trajectoire (02 §26) : J_path = Σ_t [" f"{w['lambda_irreversibility']}·ι + "
      f"{w['lambda_uncertainty']}·U − {w['lambda_voi']}·VOI], à côté du vecteur J de l'état final, transition "
      "comprise. VOI est un indicateur (étape réversible sur un effet non établi), pas une valeur espérée.\n")
    a(f"**Conclusion : {m['conclusion']}** — premier niveau de la hiérarchie au front : "
      f"`{m['first_level_on_front']}`. Catégorie de publication : **{m['publication_category']}**.\n")
    if m["conclusion"] == "STATUS_QUO_NOT_DOMINATED":
        a("Aucune trajectoire ne fait au moins aussi bien que le statu quo sur tous les objectifs, coût de "
          "transition compris : rester est sur le front. Les autres trajectoires du front sont des **compromis** "
          "(elles améliorent certains objectifs et en dégradent d'autres), jamais des recommandations.\n")
    a("| rang | trajectoire | étapes | faisable | J_path | ρ(J_T) | ρ(J_pkg) | ρ(J_D) | améliore | dégrade |")
    a("|---|---|---|---|---|---|---|---|---|---|")
    for p in m["paths"]:
        o, e = p["objectives"], p["explanation"]
        steps = " → ".join(s["action"] for s in p["steps"])
        a(f"| {p['rank'] or '—'} | `{p['name']}` | {steps} | {'oui' if p['feasible'] else '**non**'} | "
          f"{p['penalty']:.2f} | {_fmt_obj(o.get('J_T'))} | {_fmt_obj(o.get('J_pkg'))} | {_fmt_obj(o.get('J_D'))} | "
          f"{', '.join(e['improved']) or '—'} | {', '.join(e['worsened']) or '—'} |")
    a("")
    a("**Hiérarchie contrefactuelle** (§79) :\n")
    a("| niveau | action | trajectoires | au front |")
    a("|---|---|---|---|")
    for h in m["hierarchy"]:
        a(f"| {h['level']} | {h['action']} | {len(h['paths'])} | {len(h['on_front'])}"
          + (f" — {h['note']}" if h["note"] else "") + " |")
    a("")
    u = m["urgency"]
    urgent = sum(u["status_quo_urgent_estimates"].values())
    a(f"Urgence droits (02 §27) : {urgent} estimation(s) de domination grave urgente au statu quo"
      + (f" ; trajectoires rendues infaisables : {len(u['paths_made_infeasible'])}." if urgent else
         " — l'exception ne s'applique pas.")
      + (f" Options non évaluables (effet inconnu) : {', '.join(m['not_evaluable_options'])}."
         if m["not_evaluable_options"] else "") + "\n")
    front = [p for p in m["paths"] if p["rank"] == 1]
    a("Lecture admise (06 §15), pour chaque trajectoire du front :\n")
    for p in front:
        a(f"- `{p['name']}` — {p['statement']}")
    a("")
    v = m["valid_as_of"]
    a(f"Valide à la date du run ({v['run_created_at']}) et des données ({', '.join(v['data_vintages'])}) ; aucune "
      "conclusion n'est permanente (06 §16). Couche cartographique : "
      + ("publiée." if m["public_layer"]["published"] else f"**vide** — {m['public_layer']['reason']}.") + "\n")
