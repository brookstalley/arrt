# The image Arrt's suites run in on testament's runners (`.testament.toml`).
#
# Not the deploy image. `arrt/Dockerfile` builds with `arrt/` as its context and
# its test stage runs as root, and testament builds every image from the repo
# root and refuses one that ends as root (#386). The deploy image stays as it is;
# this one holds what the three suites and the browser suite need, and nothing
# that ships.
#
# Built on each runner for its own architecture, so nothing here may be
# architecture-specific: the pool has arm64 and x86_64 machines.

FROM ghcr.io/astral-sh/uv:0.11.32@sha256:df4cae8f3a96d175e2e5f992e597550000edbe78fdc2594d5cd8de1a217f504c AS uv

# Node only for its binary: the curation suite parses the browser client's
# modules with it (`test_client_vocabulary.py`, `test_ages.py`,
# `test_one_date_formatter.py`), and without it those checks skip as
# "opportunistic" and read as covered when they never ran. Debian's own nodejs
# (18) is older than the syntax the client is written in.
FROM node:22-bookworm-slim@sha256:5ec23b7c622b00547753bc6ffd78085dd868a68aeb41c8e0a1418f033e13d96d AS node

FROM debian:bookworm-slim@sha256:3783cc01769c7b2b1b83a5c5ad96c815348e28ed7da68e2e3687004faa906251

# git: the root suite's guards walk `git ls-files`. tar: testament unpacks its
# plugin with it.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl git tar libssl3 \
 && rm -rf /var/lib/apt/lists/*

COPY --from=uv /uv /uvx /usr/local/bin/
COPY --from=node /usr/local/bin/node /usr/local/bin/node
RUN node --version

# Python and the browser live outside any home, readable by the user below.
ENV UV_PYTHON_INSTALL_DIR=/opt/python \
    UV_LINK_MODE=copy \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright

# Every project pins the same Python (`tests/test_one_python.py`), so the root's
# `.python-version` names it for all three.
COPY .python-version /opt/python-version
RUN uv python install "$(cat /opt/python-version)"

# The browser suite's Chromium and its system libraries, at the Playwright the
# curation plane's lockfile pins (`tests/preferences/test_test_image.py` holds
# the two together). Installed here rather than in a setup step, which would
# download it again for every new tree.
ARG PLAYWRIGHT_VERSION=1.62.0
RUN uvx --python "$(cat /opt/python-version)" --from "playwright==${PLAYWRIGHT_VERSION}" playwright install --with-deps chromium \
 && chmod -R a+rX /opt/ms-playwright /opt/python \
 && rm -rf /root/.cache

RUN useradd --create-home --uid 1000 tester
USER tester
