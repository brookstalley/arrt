---
paths:
  - "pyproject.toml"
  - "arrt/pyproject.toml"
  - "postarr/pyproject.toml"
---
# Learnings — tooling

- Run an autofixer only under the project's real rule set, never `--select` with RUF100 in it — because a narrowed selection makes every other rule's `noqa` look unused, and the fix deletes them all.
