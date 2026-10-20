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
    unknown = ["tout effet causal (`CAUSAL_EFFECT_UNKNOWN`)", "toute ontologie identitaire (M4)",
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
