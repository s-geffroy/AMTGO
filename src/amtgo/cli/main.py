"""CLI ``amtgo`` (Typer). Cible §54 ; seules les commandes M0–M2 existent."""

from __future__ import annotations

from pathlib import Path

import typer

from amtgo.config.settings import get_settings

app = typer.Typer(no_args_is_help=True, add_completion=False,
                  help="AMTGO — laboratoire de géométries constitutionnelles (V1.0-RC1).")
run_app = typer.Typer(no_args_is_help=True, help="Runs : soumission, exécution, état.")
db_app = typer.Typer(no_args_is_help=True, help="Base dédiée : migrations.")
source_app = typer.Typer(no_args_is_help=True, help="Registre de sources.")
ingest_app = typer.Typer(no_args_is_help=True, help="Ingestion.")
export_app = typer.Typer(no_args_is_help=True, help="Exports (passent tous par le privacy guard).")
validate_app = typer.Typer(no_args_is_help=True, help="Validation : mondes synthétiques, red-team.")
app.add_typer(run_app, name="run")
app.add_typer(db_app, name="db")
app.add_typer(source_app, name="source")
app.add_typer(ingest_app, name="ingest")
app.add_typer(export_app, name="export")
app.add_typer(validate_app, name="validate")


def _resolve(path: Path) -> Path:
    if path.exists():
        return path
    candidate = get_settings().configs_dir / path
    if candidate.exists():
        return candidate
    raise typer.BadParameter(f"introuvable : {path}")


@run_app.command("submit")
def run_submit(request: Path) -> None:
    """Gèle une requête de run et la place dans la file du worker."""
    from amtgo.runs.queue import submit

    manifest, created = submit(_resolve(request), get_settings())
    typer.echo(f"{manifest.run_id} {'soumis' if created else 'déjà présent'}")


@run_app.command("execute")
def run_execute(request: Path) -> None:
    """Soumet puis exécute un run jusqu'au bout, de façon synchrone (CI, Pages)."""
    from amtgo.db.engine import make_repository
    from amtgo.runs.queue import run_to_completion, submit

    settings = get_settings()
    manifest, _ = submit(_resolve(request), settings)
    state = run_to_completion(settings, make_repository(settings), str(manifest.run_id))
    typer.echo(f"{manifest.run_id} {state.status.value}")
    if state.status.value != "SUCCEEDED":
        typer.echo(state.error or "", err=True)
        raise typer.Exit(1)


@run_app.command("status")
def run_status() -> None:
    """État de tous les runs de la file."""
    from amtgo.runs.queue import list_runs

    for s in list_runs(get_settings()):
        done = sum(st.done for st in s.steps)
        typer.echo(f"{s.run_id} {s.status.value:9} {done}/{len(s.steps)} {s.error or ''}")


@db_app.command("upgrade")
def db_upgrade(revision: str = "head") -> None:
    """Applique les migrations versionnées."""
    from amtgo.db.engine import current_revision, upgrade

    settings = get_settings()
    upgrade(settings, revision)
    typer.echo(f"révision courante : {current_revision(settings)}")


@source_app.command("validate")
def source_validate(paths: list[Path] = typer.Argument(None)) -> None:  # noqa: B008
    """Valide des manifestes de source (par défaut : tout configs/sources/)."""
    from amtgo.data.sources import load_source_manifest
    from amtgo.errors import AMTGOError

    targets = paths or sorted((get_settings().configs_dir / "sources").glob("*.yaml"))
    failed = 0
    for p in targets:
        try:
            m = load_source_manifest(_resolve(p))
            typer.echo(f"OK   {m.source_id} {m.release} {m.license.license_id} {m.data_zone.value}")
        except AMTGOError as exc:
            failed += 1
            typer.echo(f"ECHEC {p}: {exc}", err=True)
    if failed:
        raise typer.Exit(1)


@ingest_app.command("run")
def ingest_run(manifest: Path, role: list[str], out: Path = Path("/tmp/amtgo-ingest")) -> None:
    """Ingère une source hors run (exploration) ; un run reste la voie reproductible."""
    from amtgo.data.ingestion import IngestRequest, ingest_source
    from amtgo.data.sources import load_source_manifest

    settings = get_settings()
    m = load_source_manifest(_resolve(manifest))
    r = ingest_source(m, IngestRequest(roles=tuple(role)), settings.state_dir / "cache", out)
    typer.echo(f"{m.source_id} : {r.observation_count} observations → {r.observations_path}")


@export_app.command("pages-map")
def export_pages_map_cmd(run_id: str, out: Path) -> None:
    """Exporte les couches de la carte publique d'un run terminé."""
    from amtgo.export.pages_map import export_pages_map
    from amtgo.runs.queue import runs_dir

    meta = export_pages_map(runs_dir(get_settings()) / run_id, out)
    typer.echo(f"{len(meta['layers'])} couches → {out}")


@export_app.command("report")
def export_report(run_id: str, out: Path) -> None:
    """Copie le rapport Markdown d'un run terminé."""
    from amtgo.runs.queue import runs_dir

    src = runs_dir(get_settings()) / run_id / "report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    typer.echo(f"rapport → {out}")


@validate_app.command("worlds")
def validate_worlds(out: Path | None = None) -> None:
    """Évalue les mondes A–F et vérifie leurs propriétés D/F/I (code de sortie ≠ 0 si l'une échoue)."""
    from amtgo.config.loader import load_model
    from amtgo.manifests.normative import NormativeManifest
    from amtgo.validation.worlds_report import checks, evaluate_all, render

    nm = load_model(NormativeManifest, get_settings().configs_dir / "normative" / "default.yaml")
    text = render(nm.rights, nm.connection_weights.as_channels())
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    typer.echo(text)
    if not all(ok for _, ok, _ in checks(evaluate_all(nm.rights, nm.connection_weights.as_channels()))):
        raise typer.Exit(1)
