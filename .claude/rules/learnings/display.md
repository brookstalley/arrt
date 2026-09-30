---
paths:
  - "arrt/**"
---
# Learnings — display

- When you widen or retype a seam like `Measure`, convert every implementation together, test doubles first — because a double a green run exercises without asserting goes silently wrong.
- When a test proves a style, flag or slice took effect, also compare against the version applied to everything — because 'applied somewhere' and 'applied to the right span' differ from unstyled alike.
- When a preview tool, sample or fixture feeds a human's judgement, assert it takes the shipped branch, not a legal fallback — because a fallback renders cleanly and shows the wrong thing.
- When a requirement is about perception, record the physical quantity (viewing distance, angular size, luminance) beside any px/pt — because legibility is a fact about a person at a distance.
- When a double stands in for a stateful client, fail where the real one fails and let it model accepted-but-ignored — because a double failing early, or holding only your beliefs, makes every later assertion vacuous.
- When a test advances an injected clock, step by amounts that are not multiples of the interval under test — because an equal step can't tell wrongly consumed from correctly withheld.
