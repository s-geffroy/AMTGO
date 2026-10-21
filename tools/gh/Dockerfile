# Outil GitHub CLI (gh) dans un conteneur jetable : rien n'est installe sur l'hote.
# Version epinglee et empreinte verifiee (sha256 publie avec la release).
FROM debian:bookworm-slim

ARG GH_VERSION=2.103.0
ARG GH_SHA256=fdd768eb70f6409f80fcfa9f3a1c0adf0fc98d827ab3ce0bed2ac22762c5d786

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl git \
 && curl -fsSLo /tmp/gh.tar.gz \
      "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_amd64.tar.gz" \
 && echo "${GH_SHA256}  /tmp/gh.tar.gz" | sha256sum -c - \
 && tar -xzf /tmp/gh.tar.gz -C /tmp \
 && install -m 0755 "/tmp/gh_${GH_VERSION}_linux_amd64/bin/gh" /usr/local/bin/gh \
 && rm -rf /tmp/gh* /var/lib/apt/lists/* \
 && apt-get purge -y curl && apt-get autoremove -y

COPY gh-run /usr/local/bin/gh-run
RUN chmod 0755 /usr/local/bin/gh-run && useradd --uid 10002 --create-home gh
USER gh

ENTRYPOINT ["/usr/local/bin/gh-run"]
CMD ["--version"]
