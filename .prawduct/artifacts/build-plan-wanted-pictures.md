---
artifact: build-plan
version: 1
scope: wanted-pictures
branch: feature/wanted-pictures
partition: serial — one builder; the private Met page plugin is a separate repository's work
depends_on:
  - artifact: information-architecture
  - artifact: api-contract
governed_by:
  - artifact: api-contract
    dispositions:
      - "§ Inputs & Outputs: a below-floor instance is shown, labelled and selectable, never hidden → conforms: the Wanted row shows the same instance the review card shows, with its fit badge"
      - "Every HTTP answer has an MCP twin with the same field names → conforms: `GET /api/wanted` and `art_review(action='list_wanted')` both gain `shown` (`test_surface_parity.py`)"
  - artifact: information-architecture
    dispositions:
      - "§ Screens: Wanted → amended: each row carries the work's picture, and its *Why* says when the only scans found are too small"
  - artifact: accessibility-spec
    dispositions:
      - "Glyph and word carry the state → conforms: the fit badge travels with the picture as on the card; a row with no picture says so in words"
lifecycle: active
---

# Build Plan — Wanted shows each work's picture

## What this plan is

The owner, 2026-10-06, while the private Met page plugin was being built (it
reports the Met's thumbnails and web-size images of in-copyright works, which are
far below the floor): "these thumbnails will augment search results and serve as
placeholders on the wanted page, so users will know visually about the work they
want but cannot yet have on a wall." Shown that Wanted rows carry no picture
today, the owner chose: thumbnails stay ordinary below-floor scans, and Wanted
rows show the best surviving scan's picture.

## Requirements Confidence

**High.** The picture is one the card already computes.

- [DECISION: the picture is `CandidateView.shown`'s — the selected instance, else the best surviving one by `selection.surviving` — so Wanted and the card can never picture a work differently; a work whose every scan was turned down shows none | the card's own rule, with its reasons in `ReviewService._view`; a turned-down scan may be the wrong painting, so it never stands for the work | agent's, from the owner's "best surviving scan"]
- [DECISION: built in `ReviewService.list_wanted`, beside `list_works`, wrapping `DiscoveryService.list_wanted` | the instance view and its fit are the review service's; discovery cannot build one without importing upward | agent's]
- [DECISION: HTTP reads no bytes (`pictures=False`: a stat says whether one exists, as the review grid does); the browser asks the existing preview route per row, lazily | the listing is uncapped, so its cost must stay a stat per row | agent's]
- [DECISION: MCP's `list_wanted` sends no image blocks; each row carries the card summary's fit fields and `preview_note`, and the response's notice names `get_work` for the picture whenever a row has one | an uncapped listing with an image per row has no bound on its size; `list_works` is capped and so may carry them | agent's]
- [DECISION: *Why* is derived, not stored: the turned-down count, then what the shown scan is — "found only too small" when below the floor, "one still on offer" when it is the selection (wanted without turning it down), else "one found, not on offer" — and "No scan found" only when nothing stands | with a picture beside it, "No scan found" on a work holding a too-small scan is false; it was already false before this plan for a work wanted from a below-floor card. "On offer" means selected, as `is_on_offer` does on the card | agent's; the fourth reading added at review]
- [ASSUMPTION: the picture enlarges on press, as on the card | same `instanceImage` button]

**Not in this plan:** a placeholder kind of image that can never be accepted (the
owner chose ordinary scans); pictures on any other listing.

## Status

- [x] Chunk 01: Wanted rows carry the work's picture, on both surfaces

### Chunk 01: Wanted rows carry the work's picture, on both surfaces

**Exposed API:** `GET /api/wanted` and `art_review(action='list_wanted')`: each
work gains `shown` (HTTP: an `InstanceOut` or null; MCP: the card summary's
shown fields or null). Additive.

Done when:

- `ReviewService.list_wanted(*, pictures)` returns each wanted work with its shown
  instance; unit tests: selected, below-floor-only, all turned down, none found.
- The route and the tool carry `shown`; the parity test holds the names; an
  integration test reads a below-floor scan's row over real HTTP and MCP.
- Wanted renders the picture (enlargeable) or words for its absence, and *Why*
  reads each case; browser tests for each.
- `api-contract.md` (`GET /api/wanted`, `list_wanted`), `information-architecture.md`
  § Screens (Wanted), and `WantedListingOut`'s docstring updated.

- **Critic mode:** chunk (the one boundary review)
