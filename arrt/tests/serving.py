"""Serving a real application on a loopback port, the way this suite reaches a surface.

Real uvicorn rather than an in-process transport: Starlette does not run a mounted
sub-app's lifespan, and the lifespan is what makes the MCP mount work.
"""

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Final

import httpx
import pytest
import uvicorn

#: How long one of the suite's own requests may take before it fails. httpx's
#: default is 5 s, and contention alone comes close to it: with three full
#: curation suites running at once (2026-11-09, 12,510 requests timed), p99.9
#: was 2.1 s and the slowest 4.4 s, on ordinary routes holding no lock; and with
#: the browser suite running beside a curation suite, `/openapi.json` took longer
#: than the 10 s its test then gave it. A 5 s bound, or any one call's own
#: shorter one, fails a test for the machine's load (#372), which says nothing
#: about the server. Thirty seconds is the browser suite's Playwright default,
#: so both of the suite's transports give a server the same time before
#: calling it hung.
SUITE_REQUEST_SECONDS: Final = 30.0

#: httpx's one-shot request functions, every one of which a test calls bare.
#: The patch is process-wide: it reaches any caller in the test process. The
#: product builds clients with timeouts of its own and calls none of these
#: (`test_the_product_calls_none_of_httpxs_one_shot_functions`); a dependency
#: that does (`langchain_openai`, `langsmith`) gets 30 s too, and no offline
#: test reaches those calls. `httpx.stream` is left out because it is a context
#: manager whose wrapper has no keyword default to set: a test streaming a
#: response passes its own `timeout`.
_ONE_SHOT: Final = ("request", "get", "options", "head", "post", "put", "patch", "delete")


def bound_the_suites_requests() -> None:
    """Give every one-shot httpx call the suite makes `SUITE_REQUEST_SECONDS`, not httpx's 5 s.

    Set as the functions' keyword default rather than at each call site,
    which is where the next test would forget it. A client a test builds
    itself is outside this default and sets its own timeout; nothing here
    checks that it does. Refuses, rather than
    quietly doing nothing, if httpx has stopped declaring the default here.
    """
    for name in _ONE_SHOT:
        defaults = getattr(httpx, name).__kwdefaults__
        if not defaults or "timeout" not in defaults:
            raise RuntimeError(f"httpx.{name} no longer takes a keyword `timeout` default; the suite's bound would not apply")
        defaults["timeout"] = httpx.Timeout(SUITE_REQUEST_SECONDS)


@contextmanager
def serve(app: Any) -> Iterator[str]:
    """Serve `app` on an ephemeral loopback port until the block ends; yields its URL.

    **uvicorn is asked for port 0 and the port is read back from the socket it
    bound**, so no other process can take the port between choosing and binding
    (conftest's `server_url` says why that matters under the parallel suite).
    """
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 20
    while not server.started:
        if time.monotonic() > deadline:
            server.should_exit = True
            pytest.fail("the curation server did not start within 20 seconds")
        time.sleep(0.02)

    # Only valid once `started` is set — that is what puts the bound sockets on
    # the server — which is why this reads after the wait rather than beside the
    # config above.
    port = server.servers[0].sockets[0].getsockname()[1]

    try:
        yield f"http://{config.host}:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=20)
