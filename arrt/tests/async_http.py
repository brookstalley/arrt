"""A request from inside an async test, without blocking the event loop.

The MCP client a surface test drives runs on that loop, so a blocking `httpx.get`
beside it stalls the client for as long as the server takes to answer.
"""

import httpx
from serving import SUITE_REQUEST_SECONDS


async def request(method: str, url: str, **kwargs) -> httpx.Response:
    # The suite's bound, as every one-shot call has it (`serving.py`).
    async with httpx.AsyncClient(timeout=SUITE_REQUEST_SECONDS) as client:
        return await client.request(method, url, **kwargs)
