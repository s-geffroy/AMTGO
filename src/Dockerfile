FROM python:3.13-alpine

WORKDIR /app
COPY worker.py /app/worker.py

# Utilisateur non-root : rien n'oblige ce conteneur a tourner en root.
# /state est cree ICI, et possede par 'app' : Docker initialise un volume nomme
# vide avec le proprietaire et les droits du repertoire de l'image. Sans ca, le
# volume arriverait en root:root et le worker ne pourrait pas y ecrire.
RUN adduser -D -u 10001 app && mkdir -p /state && chown -R app:app /app /state
USER app

# Aucun EXPOSE : ce conteneur n'ouvre rien.
# -u : sortie non bufferisee, sinon les logs n'apparaissent que par blocs.
CMD ["python3", "-u", "/app/worker.py"]
