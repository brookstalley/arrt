"""A request from inside an async test, without blocking the event loop.

The MCP client a surface test drives runs on that loop, so a blocking `httpx.get`
beside it stalls the client for as long as the server takes to answer.
"""

import httpx


async def request(method: str, url: str, **kwargs) -> httpx.Response:
    async with httpx.AsyncClient() as client:
        return await client.request(method, url, **kwargs)
