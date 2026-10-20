# Raccourcis. Tout s'execute dans les conteneurs via appctl : rien sur l'hote.
APPCTL := sudo appctl
CLI    := $(APPCTL) run cli

.PHONY: validate build rebuild status logs smoke test test-fast lint typecheck db-upgrade pilot docs

validate:
	$(APPCTL) validate

build:
	$(APPCTL) build

rebuild:
	$(APPCTL) rebuild

status:
	$(APPCTL) status

logs:
	$(APPCTL) logs

smoke:
	$(CLI) tests/test_smoke.sh

test:
	$(CLI) pytest

test-fast:
	$(CLI) pytest -m "not db" -x -q

lint:
	$(CLI) ruff check src tests

typecheck:
	$(CLI) mypy

db-upgrade:
	$(CLI) amtgo db upgrade

# Soumet le pilote synthetique a la file du worker (suivre avec `make logs`).
pilot:
	$(CLI) amtgo run submit configs/runs/synthetic_pilot.yaml

# Construction locale du site : la CI (pages.yml) fait la meme chose et publie.
docs:
	$(CLI) sh scripts/build_docs.sh /tmp/site
