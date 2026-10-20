#!/usr/bin/env python3
"""
Squelette de worker : une boucle, un battement de coeur, un arret propre.

Remplacer le contenu de cycle(). Le reste est la charpente et merite d'etre
gardee : c'est elle qui rend le conteneur observable et arretable.
"""
import os
import signal
import time
from pathlib import Path

INTERVAL = int(os.environ.get("WORKER_INTERVAL", "30"))
HEARTBEAT = Path(os.environ.get("WORKER_HEARTBEAT", "/tmp/heartbeat"))
STATE = Path(os.environ.get("WORKER_STATE", "/state"))

stopping = False


def log(msg):
    # flush : sans lui, la sortie est bufferisee des qu'elle n'est pas un
    # terminal, et `appctl logs` ne montre rien pendant des minutes.
    print(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {msg}", flush=True)


def on_stop(signum, _frame):
    global stopping
    stopping = True
    log(f"signal {signum} recu : arret a la fin du cycle en cours")


def cycle():
    """Le travail. C'est ici que ca se passe."""
    counter = STATE / "cycles"
    n = int(counter.read_text()) + 1 if counter.exists() else 1
    counter.write_text(str(n))
    log(f"cycle {n}")


def main():
    signal.signal(signal.SIGTERM, on_stop)
    signal.signal(signal.SIGINT, on_stop)
    STATE.mkdir(parents=True, exist_ok=True)
    log(f"demarrage (intervalle {INTERVAL} s, etat dans {STATE})")

    while not stopping:
        try:
            cycle()
        except Exception as exc:
            # Un cycle qui echoue ne tue pas le worker : il rate son tour et
            # reessaie au suivant. Ce qui ne doit jamais etre avale, c'est le
            # message d'erreur.
            log(f"echec du cycle : {exc!r}")
        HEARTBEAT.touch()

        # Sommeil fractionne : un SIGTERM ne doit pas attendre l'intervalle
        # entier pour etre pris en compte.
        for _ in range(INTERVAL):
            if stopping:
                break
            time.sleep(1)

    log("arrete")


main()
