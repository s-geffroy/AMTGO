# Contexte de build : la racine du projet (voir compose.yaml et ADR-0001).
# Debian slim et non Alpine : shapely, pyproj et h3 publient des wheels
# manylinux, pas musl (ADR-0002).
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /usr/local/bin/uv

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    OPENBLAS_NUM_THREADS=1 \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1
# Threads BLAS = quota CPU du conteneur (cpus: "1.0" dans compose.yaml). Le conteneur
# voit tous les coeurs de l'hote : sans ce reglage, OpenBLAS lance un thread par coeur
# qui s'attendent activement sur un seul CPU (x200 sur une resolution 300x300).

# libexpat1 : requise par le GDAL embarque dans les wheels de rasterio (absente de l'image slim).
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependances d'abord, depuis le lockfile : la couche reste en cache tant que
# pyproject.toml et uv.lock ne bougent pas.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --all-groups --no-install-project

COPY src ./src
COPY configs ./configs
COPY tests ./tests
COPY mkdocs.yml ./
# Les fichiers arrivent avec le mode de l'hote : les rendre lisibles par 'app'.
RUN chmod -R a+rX /app
# Installation editable : le service 'cli' monte ./src en lecture seule par
# dessus, et les tests voient le code courant sans rebuild.
RUN uv sync --frozen --all-groups

# Version du code, reportee dans chaque RunManifest (code_commit).
ARG GIT_COMMIT=unknown
ENV AMTGO_CODE_COMMIT=$GIT_COMMIT

# Utilisateur non-root : rien n'oblige ce conteneur a tourner en root.
# /state est cree ICI, et possede par 'app' : Docker initialise un volume nomme
# vide avec le proprietaire et les droits du repertoire de l'image. Sans ca, le
# volume arriverait en root:root et le worker ne pourrait pas y ecrire.
RUN useradd --uid 10001 --create-home app && mkdir -p /state && chown -R app:app /state
USER app

# Aucun EXPOSE : ce conteneur n'ouvre rien.
# -u : sortie non bufferisee, sinon les logs n'apparaissent que par blocs.
CMD ["python3", "-u", "/app/src/worker.py"]
