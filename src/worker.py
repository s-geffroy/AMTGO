#!/usr/bin/env python3
"""
Worker AMTGO : une boucle, un battement de coeur, un arret propre.

Le travail est dans cycle() : avancer d'UNE etape le plus ancien run de la file
(amtgo.runs.queue). Le reste est la charpente et merite d'etre gardee : c'est
elle qui rend le conteneur observable et arretable.
"""
import os
import signal
import time
from pathlib import Path

from amtgo.config.settings import get_settings
from amtgo.utils.logging import log_event

INTERVAL = int(os.environ.get("WORKER_INTERVAL", "30"))
HEARTBEAT = Path(os.environ.get("WORKER_HEARTBEAT", "/tmp/heartbeat"))
STATE = Path(os.environ.get("WORKER_STATE", os.environ.get("AMTGO_STATE_DIR", "/state")))
os.environ.setdefault("AMTGO_STATE_DIR", str(STATE))

stopping = False
_repo = None


def log(msg, **fields):
    # Une ligne JSON horodatee par evenement, flush immediat (amtgo.utils.logging).
    log_event(msg, **fields)


def on_stop(signum, _frame):
    global stopping
    stopping = True
    log("worker.signal", detail=f"signal {signum} recu : arret a la fin de l'etape en cours")


def repository():
    """Base preparee une seule fois (migrations a jour) ; un echec sera retente au cycle suivant."""
    global _repo
    if _repo is None:
        from amtgo.db.engine import current_revision, make_repository, upgrade

        settings = get_settings()
        if settings.db_enabled:
            upgrade(settings)
            log("worker.db", status="ready", detail=current_revision(settings))
        else:
            log("worker.db", status="disabled", detail="AMTGO_DB_HOST absent : artefacts fichiers seuls")
        _repo = make_repository(settings)
    return _repo


def cycle():
    """Le travail : une etape d'un run. Rien a faire n'est pas une erreur."""
    from amtgo.runs.queue import advance_one

    adv = advance_one(get_settings(), repository(), should_stop=lambda: stopping)
    if adv is None:
        return
    if adv.outcome == "failed":
        log("worker.cycle", run_id=adv.run_id, stage=adv.step, status="run_failed")


def main():
    signal.signal(signal.SIGTERM, on_stop)
    signal.signal(signal.SIGINT, on_stop)
    STATE.mkdir(parents=True, exist_ok=True)
    log("worker.start", detail=f"intervalle {INTERVAL} s, etat dans {STATE}")

    while not stopping:
        try:
            cycle()
        except Exception as exc:
            # Un cycle qui echoue ne tue pas le worker : il rate son tour et
            # reessaie au suivant. Ce qui ne doit jamais etre avale, c'est le
            # message d'erreur.
            from amtgo.runs.queue import safe_error

            log("worker.cycle", status="error", error=safe_error(exc))
        HEARTBEAT.touch()

        # Sommeil fractionne : un SIGTERM ne doit pas attendre l'intervalle
        # entier pour etre pris en compte.
        for _ in range(INTERVAL):
            if stopping:
                break
            time.sleep(1)

    log("worker.stop", detail="arrete")


if __name__ == "__main__":
    main()
