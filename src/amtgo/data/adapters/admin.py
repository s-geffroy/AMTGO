"""Unités administratives réelles : polygones (COD-AB, geoBoundaries) et tableaux de totaux.

Deux adapters, une même lecture des polygones :

- ``admin_boundaries`` : un polygone par unité, support ADMIN. La licence d'une
  frontière geoBoundaries est lue **dans ses métadonnées** et comparée à celle
  déclarée par le manifeste (licences mixtes dans gbOpen) ;
- ``admin_table`` : un total par unité (recensement ou projection), joint aux
  polygones par code ou par nom. La jointure est exhaustive dans les deux sens :
  une unité sans polygone ou un polygone sans total est une erreur, jamais un
  zéro ni une omission silencieuse (03 §26). Les fusions (district scindé
  après le tracé des polygones) sont déclarées dans le manifeste.

Le statut de preuve vient du manifeste : D pour un recensement, M pour une
projection. Il n'est jamais promu ici.
"""

from __future__ import annotations

import csv
import io
import json
import unicodedata
import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime, time
from pathlib import Path
from typing import Any

from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from shapely.validation import make_valid

from amtgo.core.enums import SupportType
from amtgo.core.uncertainty import DistributionType, UncertainValue
from amtgo.data.adapters.files import PinnedFileMixin
from amtgo.data.observations import Observation
from amtgo.data.sources import SourceManifest
from amtgo.errors import ConfigurationError, DataLicenseError


def _read_bytes(files: dict[str, Path], resource: str, member: str | None) -> bytes:
    if resource not in files:
        raise ConfigurationError(f"ressource {resource!r} absente du manifeste")
    path = files[resource]
    if member is None:
        return path.read_bytes()
    with zipfile.ZipFile(path) as z:
        if member not in z.namelist():
            raise ConfigurationError(f"{resource} : membre {member!r} absent de l'archive")
        return z.read(member)


def read_units(files: dict[str, Path], spec: dict[str, Any]) -> dict[str, tuple[str, BaseGeometry]]:
    """{code: (nom, géométrie valide)} d'une couche de polygones GeoJSON (éventuellement zippée)."""
    fc = json.loads(_read_bytes(files, spec["resource"], spec.get("member")))
    code_f, name_f = spec["code_field"], spec["name_field"]
    out: dict[str, tuple[str, BaseGeometry]] = {}
    for feat in fc["features"]:
        props = feat.get("properties") or {}
        code, name = props.get(code_f), props.get(name_f)
        if not code or not name:
            raise ConfigurationError(f"{spec['resource']} : unité sans {code_f!r} ou {name_f!r}")
        if str(code) in out:
            raise ConfigurationError(f"{spec['resource']} : code {code!r} dupliqué")
        geom = shape(feat["geometry"])
        out[str(code)] = (str(name), geom if geom.is_valid else make_valid(geom))
    if not out:
        raise ConfigurationError(f"{spec['resource']} : aucune unité")
    return out


def normalize_name(name: str) -> str:
    """Nom comparable : sans accents ni casse, tirets et espaces multiples ramenés à un espace."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return " ".join(s.replace("-", " ").replace("_", " ").casefold().split())


def _validity(manifest: SourceManifest) -> tuple[datetime, datetime | None]:
    if manifest.temporal_start is None:
        raise ConfigurationError(f"{manifest.source_id} : temporal_start requis (temps de validité)")
    start = datetime.combine(manifest.temporal_start, time.min, tzinfo=UTC)
    end = datetime.combine(manifest.temporal_end, time.max, tzinfo=UTC) if manifest.temporal_end else None
    return start, end


def _common(manifest: SourceManifest, recorded_at: datetime) -> dict[str, Any]:
    start, end = _validity(manifest)
    return dict(version=manifest.release, source_id=str(manifest.source_uuid), valid_from=start,
                valid_until=end, recorded_at=recorded_at, quality=manifest.quality,
                evidence_status=manifest.default_evidence_status, sensitivity=manifest.privacy_class)


def check_declared_license(manifest: SourceManifest, files: dict[str, Path]) -> None:
    """Licence lue dans les métadonnées de la frontière, comparée à celle déclarée (ADR-0028)."""
    chk = manifest.retrieval.parameters.get("license_check")
    if chk is None:
        return
    meta = json.loads(_read_bytes(files, chk["resource"], chk.get("member")))
    found = str(meta.get(chk["field"], "")).strip()
    if found != str(chk["expected"]).strip():
        raise DataLicenseError(f"{manifest.source_id} : licence {found!r} dans les métadonnées, "
                               f"{chk['expected']!r} déclarée dans le manifeste")


class AdminBoundariesAdapter(PinnedFileMixin):
    def normalize(
        self, manifest: SourceManifest, files: dict[str, Path], recorded_at: datetime
    ) -> Iterator[Observation]:
        check_declared_license(manifest, files)
        layers: list[dict[str, Any]] = manifest.retrieval.parameters.get("layers", [])
        if not layers:
            raise ConfigurationError(f"{manifest.source_id} : paramètre 'layers' requis")
        common = _common(manifest, recorded_at)
        for spec in layers:
            variable = spec["variable"]
            for code, (name, geom) in sorted(read_units(files, spec).items()):
                yield Observation(
                    id=Observation.make_id(common["source_id"], variable, code, common["valid_from"]),
                    variable_id=variable, support_type=SupportType.ADMIN, geometry_wkt=geom.wkt,
                    admin_code=code, attributes={"name": name, "level": spec.get("level")}, **common,
                )


def join_table(units: dict[str, tuple[str, BaseGeometry]], rows: list[dict[str, str]],
               params: dict[str, Any]) -> dict[str, tuple[float, list[str]]]:
    """{code de polygone: (total, lignes du tableau)} ; jointure exhaustive dans les deux sens."""
    table = params["table"]
    total_f = table["total_field"]
    by_unit: dict[str, tuple[float, list[str]]] = {}
    if params.get("join", "code") == "code":
        key_f = table["code_field"]
        keys = {str(r[key_f]): r for r in rows}
        lookup = {code: [code] for code in units}
    else:
        key_f = table["name_field"]
        aliases = {normalize_name(k): normalize_name(v) for k, v in (params.get("aliases") or {}).items()}
        # Suffixes de nommage du tableau (« X District ») retirés avant comparaison aux polygones.
        suffixes = [normalize_name(s) for s in params.get("strip_suffixes") or []]
        keys = {}
        for r in rows:
            k = normalize_name(str(r[key_f]))
            for s in suffixes:
                if k.endswith(" " + s):
                    k = k[: -len(s) - 1]
            keys[aliases.get(k, k)] = r
        merges = {normalize_name(k): [normalize_name(x) for x in v] for k, v in (params.get("merge") or {}).items()}
        lookup = {}
        for code, (name, _) in units.items():
            n = normalize_name(name)
            # Les fusions nomment des lignes du tableau (alias appliqués) ; sinon, le nom du polygone.
            lookup[code] = [aliases.get(x, x) for x in merges[n]] if n in merges else [n]
    if len(keys) != len(rows):
        raise ConfigurationError(f"tableau : clé {key_f!r} dupliquée")
    used: set[str] = set()
    missing: list[str] = []
    for code, wanted in sorted(lookup.items()):
        if not all(w in keys for w in wanted):
            missing.append(f"{code} ({units[code][0]})")
            continue
        used.update(wanted)
        by_unit[code] = (sum(float(keys[w][total_f]) for w in wanted), sorted(wanted))
    orphans = sorted(set(keys) - used)
    if missing or orphans:
        raise ConfigurationError(f"jointure tableau-polygones incomplète : polygones sans total {missing}, "
                                 f"lignes sans polygone {orphans} (déclarer 'aliases' ou 'merge')")
    return by_unit


def group_units(units: dict[str, tuple[str, BaseGeometry]],
                groups: dict[str, list[str]] | None) -> dict[str, tuple[str, BaseGeometry]]:
    """Regroupe des polygones en une seule marge déclarée (unités plus petites qu'une cellule).

    Perte de résolution assumée et nommée dans le manifeste : sans elle, le recalage
    exact sur des unités qui tiennent dans une cellule n'a pas de solution.
    """
    if not groups:
        return units
    by_name = {normalize_name(name): code for code, (name, _) in units.items()}
    out = dict(units)
    for group, members in groups.items():
        wanted = [normalize_name(m) for m in members]
        missing = [m for m in wanted if m not in by_name or by_name[m] not in out]
        if missing:
            raise ConfigurationError(f"regroupement {group!r} : polygones introuvables ou déjà regroupés {missing}")
        codes = [by_name[m] for m in wanted]
        geom = unary_union([out.pop(c)[1] for c in codes])
        out["group:" + "+".join(sorted(codes))] = (group, geom)
    return out


class AdminTableAdapter(PinnedFileMixin):
    def normalize(
        self, manifest: SourceManifest, files: dict[str, Path], recorded_at: datetime
    ) -> Iterator[Observation]:
        p = manifest.retrieval.parameters
        for key in ("table", "boundaries", "variable", "relative_error"):
            if key not in p:
                raise ConfigurationError(f"{manifest.source_id} : paramètre {key!r} requis")
        rel = float(p["relative_error"])
        if not 0 < rel < 1:
            raise ConfigurationError(f"{manifest.source_id} : relative_error hors ]0, 1[")
        check_declared_license(manifest, files)
        units = group_units(read_units(files, p["boundaries"]), p.get("group_boundaries"))
        raw = _read_bytes(files, p["table"]["resource"], p["table"].get("member")).decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(raw)))
        joined = join_table(units, rows, p)
        common = _common(manifest, recorded_at)
        variable = p["variable"]
        for code, (total, parts) in sorted(joined.items()):
            if total <= 0:
                raise ConfigurationError(f"{manifest.source_id} : total non positif pour {code}")
            name, geom = units[code]
            yield Observation(
                id=Observation.make_id(common["source_id"], variable, code, common["valid_from"]),
                variable_id=variable, support_type=SupportType.ADMIN, geometry_wkt=geom.wkt, admin_code=code,
                value=UncertainValue(mean=total, std=rel * total, distribution_type=DistributionType.NORMAL),
                attributes={"name": name, "table_rows": parts}, **common,
            )
