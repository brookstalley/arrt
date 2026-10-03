"""The container's liveness probe: cheap, unauthenticated, and touching nothing.

A supervisor calls it every few seconds and restarts what does not answer, so it
must answer without reading the catalogue — unlike `/api/health`, the person's
page, which reads the whole health panel.
"""

import httpx


def test_the_probe_answers_ok(server_url):
    response = httpx.get(f"{server_url}/healthz", timeout=10.0)

    assert (response.status_code, response.text) == (200, "ok")


def test_the_probe_is_not_in_the_published_api(server_url):
    """It is for the container, not for clients, so the schema does not offer it."""
    schema = httpx.get(f"{server_url}/openapi.json", timeout=10.0).json()

    assert "/healthz" not in schema["paths"]
