"""Serving a real application on a loopback port, the way this suite reaches a surface.

Real uvicorn rather than an in-process transport: Starlette does not run a mounted
sub-app's lifespan, and the lifespan is what makes the MCP mount work.
"""

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
import uvicorn


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
