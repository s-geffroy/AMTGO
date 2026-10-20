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
    a(f"**{computability.value}** — aucun modèle de mesure n'existe encore (M3) : aucune "
      "recommandation territoriale n'est possible.\n")

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
    a(_NA.format(m="M3") + "\n")
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

    a("## Known limitations\n")
    a("- Les points géomasqués sont répartis par un noyau uniforme déterministe, pas par un "
      "modèle de mesure (M3).")
    a("- Les cellules H3 ne s'emboîtent qu'approximativement d'un niveau à l'autre.")
    a("- Les seuils normatifs du manifeste par défaut sont provisoires (gouvernance, 06 §6).")
    return "\n".join(L) + "\n"
