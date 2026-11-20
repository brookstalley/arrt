# Arrt, the curation server, as a container.
#
# Built for the NAS (`build-plan-nas.md`), from a commit, with everything it
# fetches pinned: the uv, node and Debian images by digest, Python by version
# through uv, the Python packages by `uv.lock`, and dezoomify-rs by release and
# checksum. A house's own half — addresses, ports, the env file, the volumes —
# is not here: this repository is public, and that half lives in the owner's
# homelab repository. `deploy/nas/compose.example.yaml` shows its shape.
#
#   docker buildx build --platform linux/amd64 -t arrt:<commit> arrt/
#   docker buildx build --platform linux/amd64 --target test --build-context repo=. arrt/
#
# The test target needs the repository root as a second context (`repo`): the
# contract tests read `contract/`, the seed and mat-corpus tests read the 2024
# index `all.json`, the UX walk's tests read `.env.example`, and the plugin
# tests read `docs/source-plugins.md`, all of which sit beside `arrt/`, not in
# it. The app image needs none of them.
#
# CI builds the test target only on a pull request into `main` and by hand
# (`.github/workflows/image.yml`); the pool builds it as the `image` suite of
# `.testament.toml`, run from a machine doing the work and never by CI
# (`tests/the_image_test_stage.py`, `docs/testing.md` § The image's test stage on
# the pool). Before that, on every pull request,
# `tests/test_the_image_carries_what_tests_read.py` reads the test stage's COPY
# lines, and the stages it is built on, against every path the server's tests
# and tools build from their own location: a test that reads a file this stage
# does not carry fails there, naming the file and the COPY it needs. Keep the
# layout a mirror of the repository's (`/app` is `arrt/`, `/` its root), one
# COPY a line, as that test reads them.
#
# The art root is a volume at /art: the catalogue, the masters and every derived
# file live there, so the image holds code only and a rollback is a different tag.

FROM ghcr.io/astral-sh/uv:0.11.32@sha256:df4cae8f3a96d175e2e5f992e597550000edbe78fdc2594d5cd8de1a217f504c AS uv

# Node for the test stage alone, its binary only, pinned as the testament image
# pins it (`.devcontainer/Dockerfile`): Debian's own nodejs (18) is older than
# the syntax the client is written in.
FROM node:22-bookworm-slim@sha256:5ec23b7c622b00547753bc6ffd78085dd868a68aeb41c8e0a1418f033e13d96d AS node

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
# The version is `.python-version`'s, the one every suite and CI run reads.
WORKDIR /app
COPY .python-version ./
RUN uv python install

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

# Dependencies first, from the lock alone, so a code change rebuilds only the
# layer below.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev

# The suite, in the image it tests: `--target test`. The browser group is not
# installed (it needs a downloaded Chromium), so the browser suite stays where
# it runs today and `tests/browser` is not collected.
FROM base AS test
# Node, for the tests that run the client's own modules (they skip without it).
# The test stage only: the app never runs JavaScript.
COPY --from=node /usr/local/bin/node /usr/local/bin/node
RUN node --version
# The contract package is a dev dependency at `../contract`, which from `/app`
# is `/contract`, so it is in place before the sync that installs it. Its
# `player-contract.md` is a symlink to the artifact, which the build of the
# package carries, so the artifact goes where the link points.
COPY --from=repo contract /contract
COPY --from=repo .prawduct/artifacts/player-contract.md /.prawduct/artifacts/player-contract.md
RUN uv sync --frozen
COPY tests ./tests
# The UX walk's tests import `tools/ux_walk.py` by path, from beside `tests/`.
COPY tools ./tools
# The names the walk's synthetic server starts blank are the ones the repository
# root's `.env.example` declares, and the harness refuses to boot without it
# (`ux_walk.names_to_blank`). One level above `/app`. Not `.env`: nothing loads this.
COPY --from=repo .env.example /.env.example
# Where the tests look for it: three levels above a test file, which in the
# image is the filesystem root.
COPY --from=repo all.json /all.json
# The plugin author's guide, whose tables `test_source_plugins.py` holds to the
# code; read the same way, three levels above the test file.
COPY --from=repo docs/source-plugins.md /docs/source-plugins.md
# As the app stage's user, not root: root reads a file whatever its mode, so the
# tests that make a file unreadable to prove it is reported would fail here, and
# a suite run as root would vouch for permissions the app never has. It owns
# nothing in the image, as the app owns nothing outside the art root, so a test
# that writes beside itself fails here as it would in the app; HOME points at
# the one place it may write. `--no-sync` because the environment was synced
# above, and a sync as this user could not write to it.
#
# **`player_e2e` is deselected here, by `pyproject.toml`'s addopts, and is not run.**
# `tests/system/test_a_real_player.py` installs Arrt Player from GitHub with git, and
# this stage has no git and should reach no network. The built app stage meets a real
# Player in `image.yml`'s own job on a pull request into `main` instead. Under the
# addopts' `-n auto` pytest prints no "deselected" count, so this line is where it is said.
USER 568:568
ENV HOME=/tmp
RUN uv run --no-sync pytest -q -p no:cacheprovider --ignore=tests/browser --junitxml=/tmp/results.xml

# The test stage's JUnit report, alone, for CI to read with
# `.github/scripts/assert_tests_ran.py`: `--target test-report` with a local
# output. A red suite fails the stage above, so there is no report to export.
FROM scratch AS test-report
COPY --from=test /tmp/results.xml /results.xml

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
