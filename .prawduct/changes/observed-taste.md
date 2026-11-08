---
schema: 1
type: feature
scope: observed-taste
date: 2026-11-08
title: Review's verdicts become taste
---

Item 2 of `agents-and-memory.md`'s order of work, by the owner's rule of
2026-11-08. Every accept and reject re-derives the artist's observed judgment
(`taste.observe_artist`, by `artist_key`): at least 5 rejected and at least 90% of
the artist's verdicts is an observed `declines`, not open to more; the mirror is an
observed `likes`, open to more; anything else withdraws it. A `stated` judgment is
never overwritten (an observed row beside one is withdrawn), and an `inferred` one
is left alone, since nothing can write one again. Startup re-derives every
artist, so existing verdicts become taste on the first start. The Taste screen's
help names review.

## Consumer note

After the first start on this version, Taste may show judgments marked "Read from
what you accepted and rejected", with the counts behind each. They reach Ask and
Gets like any other taste. To overrule one, correct it on Taste: your correction
is a stated judgment, which review never overwrites. Forgetting one lasts only
until your next decision on that artist's works, or Arrt's next start, and the
Forget dialog says so.
