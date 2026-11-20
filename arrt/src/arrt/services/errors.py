"""The exception type the surfaces above the service layer have to know, and its one refinement.

Both the MCP bindings and the HTTP handlers translate `ServiceError` into their
own error shape. Keeping it a single type means neither surface grows a
per-error translation table — the thing that turns a thin binding into a thick
one. `NotFound` is the one distinction a surface draws, and it is a subclass so
that a surface which draws none (MCP) answers as it always has.
"""


class ServiceError(Exception):
    """An operation the service refused, carrying a message fit to return.

    The message is written for whoever asked: it names the value that was
    wrong and, where there is one, the thing to do instead. It never carries a
    stack trace or an internal identifier — those go to the log.
    """


class NotFound(ServiceError):
    """A refusal because the caller named a thing, by its id or by the name that is its identity, that does not exist.

    A subclass rather than a second type, so every place that catches
    `ServiceError` (MCP's failure shape, the Ask agent, the scheduler's jobs, a
    service catching a collaborator's refusal) answers exactly as before. Only
    `/api` tells the two apart: a `NotFound` answers 404 there and every other
    refusal 400 (`app.py`, `http/api.service_error_response`). The Player's
    routes are the contract's, and keep 400 for both.

    A thing that exists in a state that refuses the act (nothing hanging on a
    wall, a work not archived, a run already ended, no work in the queue failed
    for a cause now) is not this: it is a plain `ServiceError`, and 400. So is a
    value chosen from a fixed list (a mat preset, a facet, a status), and a
    Wikidata item that Wikidata does not have: neither is a thing this server
    holds.
    """
