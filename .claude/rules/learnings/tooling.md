---
paths:
  - "pyproject.toml"
  - "arrt/pyproject.toml"
  - "arrt-player/pyproject.toml"
  - "tests/preferences/**"
---
# Learnings — tooling

- Run an autofixer only under the project's real rule set, never `--select` with RUF100 in it — because a narrowed selection makes every other rule's `noqa` look unused, and the fix deletes them all.
- Stage new files before recording suite evidence — because guards that walk `git ls-files` (the waiver check among them) skip untracked files, so a green local run can miss what CI then refuses.
