---
schema: 1
type: fix
scope: pillow-13
date: 2026-11-08
title: Pillow 13 and certifi, for their security fixes
---

Dependabot listed 44 open alerts on `main`, nearly all Pillow 12.3.0 in
`arrt/uv.lock`: 5 critical and 23 high, among them JPEG and TIFF decoder buffer
overflows and decompression-bomb bypasses. Arrt decodes images fetched from museums
and image sources with Pillow, unattended, so these sit on its untrusted input. Pillow
goes to 13.0.0, with `pillow>=13.0.0` declared so a lock cannot return below it;
certifi to 2026.10.23 (one critical alert); black to 26.10.1 in the root and `arrt`
lockfiles (an alert on its GitHub Action, which Arrt does not use, taken to match the
contract package). Pillow 13's incompatible changes were read against every call site
(`fromarray` modes, `get_child_images`, `_show`, ImageCms product fields, `IFD.Makernote`,
I-mode PNG saving, `ImageColor.getcolor`): Arrt uses none. All suites pass under 13.0.0,
and the three Pillow tools in `arrt/tools/` start. Arrt Player locks Pillow 12.3.0 too,
in its own repository.

## Consumer note

No visible change. The image libraries Arrt uses to read downloaded pictures are
patched against the vulnerabilities GitHub reported.
