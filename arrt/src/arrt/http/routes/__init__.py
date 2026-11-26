"""The browser client's JSON routes, one module per resource.

Each module holds its resource's handlers and the shaping only they use; what two
resources shape alike is in `shapes`, and what every module needs is in `common`.
A module's `router` is not mounted anywhere: `arrt.http.api` assembles them into the
one router the application includes, in the order FastAPI matches them in.
"""
