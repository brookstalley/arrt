# Arrt, the curation server, as a container.
#
# Built for the NAS (`build-plan-nas.md`), from a commit, with everything it
# fetches pinned: the uv image and the Debian base by digest, Python by version
# through uv, the Python packages by `uv.lock`, and dezoomify-rs by release and
# checksum. A house's own half — addresses, ports, the env file, the volumes —
# is not here: this repository is public, and that half lives in the owner's
# homelab repository. `deploy/nas/compose.example.yaml` shows its shape.
#
#   docker buildx build --platform linux/amd64 -t arrt:<commit> arrt/
#   docker buildx build --platform linux/amd64 --target test --build-context repo=. arrt/
#
# The test target needs the repository root as a second context (`repo`): the
# contract tests read `contract/`, and the seed and mat-corpus tests read the
# 2024 index `all.json`, both of which sit beside `arrt/`, not in it. The app
# image needs neither.
#
# The art root is a volume at /art: the catalogue, the masters and every derived
# file live there, so the image holds code only and a rollback is a different tag.

FROM ghcr.io/astral-sh/uv:0.11.32@sha256:df4cae8f3a96d175e2e5f992e597550000edbe78fdc2594d5cd8de1a217f504c AS uv

FROM debian:bookworm-slim@sha256:3783cc01769c7b2b1b83a5c5ad96c815348e28ed7da68e2e3687004faa906251 AS base

# libssl3 for dezoomify-rs, which links OpenSSL 3 dynamically; ca-certificates
# for every HTTPS fetch the server makes (Wikidata, Commons, museums, OpenRouter).
RUN apt-get update \
 && apt-get install -y --no-install-recommends libssl3 ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*

COPY --from=uv /uv /uvx /usr/local/bin/

# Python comes from uv, as on the Pi, into a directory every user can read: the
# container runs as an unprivileged user the compose file chooses.
ENV UV_PYTHON_INSTALL_DIR=/opt/python \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv
RUN uv python install 3.14

# dezoomify-rs, the version the tile-fetch findings were measured with, checked
# against the checksum of its release archive so a replaced download fails the
# build rather than shipping.
ARG DEZOOMIFY_VERSION=2.18.1
ARG DEZOOMIFY_SHA256=ef8964c57b19f583d21abc89baa1cf56e03d7756e844ba7062c4d089dadbc9d1
RUN curl -fsSL -o /tmp/dz.tgz \
      "https://github.com/lovasoa/dezoomify-rs/releases/download/v${DEZOOMIFY_VERSION}/dezoomify-rs-linux.tgz" \
 && echo "${DEZOOMIFY_SHA256}  /tmp/dz.tgz" | sha256sum -c - \
 && tar -xzf /tmp/dz.tgz -C /usr/local/bin dezoomify-rs \
 && rm /tmp/dz.tgz \
 && dezoomify-rs --version

WORKDIR /app

# Dependencies first, from the lock alone, so a code change rebuilds only the
# layer below.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev

# The suite, in the image it tests: `--target test`. The browser group is not
# installed (it needs a downloaded Chromium), so the browser suite stays where
# it runs today.
FROM base AS test
RUN uv sync --frozen
COPY tests ./tests
# Where the tests look for them: three levels above a test file, which in the
# image is the filesystem root.
COPY --from=repo all.json /all.json
COPY --from=repo contract /contract
RUN uv run --frozen pytest -q -p no:cacheprovider

FROM base AS app

ENV ART_ROOT=/art \
    CURATION_HOST=0.0.0.0 \
    CURATION_PORT=8770 \
    PATH=/opt/venv/bin:$PATH
VOLUME ["/art"]
EXPOSE 8770

# The compose file may choose another user; this one owns nothing in the image,
# which is the point: the art root is the only place it writes.
USER 568:568

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(f\"http://127.0.0.1:{os.environ.get('CURATION_PORT', '8770')}/healthz\", timeout=4)"]

# SIGTERM, not SIGKILL: the server stops its background workers and closes the
# catalogue on a clean shutdown. The compose file gives it a grace period.
STOPSIGNAL SIGTERM
CMD ["python", "-m", "arrt"]
