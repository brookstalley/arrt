# Change Log — Samsung Frame Art Loader

<!-- Append new entries at the top. Each entry is a ## section.
     This file is separate from project-state.yaml to reduce merge conflicts
     when multiple branches add entries simultaneously.

     # Tagged entries

     Add a tag-line directly under each ## header recording its rollup scope
     and, once released, which release it belongs to.

     **Nothing is REGENERATED from these tags any more — but they are still
     READ, and the difference matters when you write one.** `prawduct-hook
     regen-views` once rebuilt the build-plan `## Status` block, a release-notes
     view and a `scope_rollups:` block from them; prawduct v3.2.8 retired that
     command and the `views_enabled` switch that governed it, so this header
     spent three releases telling readers to run something that no longer
     exists.

     What survives is consumption, not generation. `scope=` and the *absence* of
     `release=` are how release-readiness enumerates work that has not shipped —
     which is why any value at all in `release=`, a placeholder included, drops
     that entry's whole scope out of the pending set. The PR flow refuses a
     branch whose entry carries no `scope=`. Only `status=` is inert now, and
     the Status checkboxes are ticked by hand and believed by every reader.

     Format:

         ## YYYY-MM-DD: title (vN.M.P)

         <!-- prawduct: release=v1.3.18 | scope=v1.4 -->

         **Why:** ...

     Recognized keys:
       chunks   - retired: nothing reads it. Archived entries carry it as
                  history; `scope=` ties an entry to its plan.
       release  - version string (used by the release-notes view)
       status   - shipped | merged (legacy). Write a new entry with NO
                  status= on the feature branch: a statusless tagged entry
                  is the release-pending state, and it becomes "merged" by
                  construction when its PR lands — no stamp, no post-merge
                  bookkeeping commit (protected branches take commits only
                  by PR). Flip to `shipped` as part of release-prep when
                  the integration branch is released (gitflow), or write
                  `status=shipped` directly in the closing PR when the
                  PR's base IS the release surface (trunk; include
                  `release=vN.M.P` when the product tracks versions —
                  release-notes groups by it) — either way the tag merges
                  atomically with the work it describes.
                  `merged` is a legacy stamp some logs carry; it is treated
                  as statusless. Don't invent states — the three above are
                  the whole vocabulary.
       scope    - rollup identifier (e.g., v1.4) -->

> **Names, 2026-10-01.** Entries are history and keep the names of their day. Until
> 2026-10-01 **Curatarr** named the server and **Arrt** named the player. Since then
> the server is **Arrt** and the player is **Postarr**
> (`build-plan-rename-arrt-postarr.md`). Paths and package names here are the
> old ones.


<!-- Older entries live in .prawduct/change-log-archive/YYYY-MM.md, moved there verbatim by `prawduct-hook archive-change-log`. -->

## 2026-10-05: An Ask's search hands the pages it read to the source plugins

<!-- prawduct: scope=ask-pages -->

**Why:** the owner chose Artlogic, the gallery platform, as the next source, found
through Ask's web search rather than a list of galleries. Gallery works have no
Wikidata item, so no plugin could be told where to look. Measured: a search for an
artist's paintings cites the gallery's artist page (`procurement-corpus.md` § The
probe: Artlogic, and what Ask's search cites). Plan: `build-plan-ask-pages.md`.

**What:**
- Phase 1 keeps its search's citations (`WorkList.citations`): in the search's
  order, each once, http(s) only. Never an address from the model's answer.
- New table `run_citations`, written when phase 1 closes (`data-model.md`
  § RunCitation, Q46–Q47).
- Phase 2 hands every work the run proposed its run's citations as
  `ImageQuery.pages`, on approval, on a re-search and after a restart. Each passes
  `check_fetchable` first, once per run per pass; a refused one is dropped and
  logged (`phase_two.page_refused`). A Get has none. The container hands the
  check the same resolver acquisition uses, so a suite's stated DNS answers
  reach it too.
- The plugin interface is 1.1. A plugin written for 1.0 loads unchanged.
- `check_fetchable` refuses a URL it cannot parse (`http://[x/`) and a name the
  resolver cannot encode (`a..b`, a label over 63 characters) instead of raising
  a parser's error. A stored citation of either shape would otherwise have failed
  its run's phase 2 on every re-search; acquisition's three callers gain the same.
- `security-model.md`: bound 2 re-derived for plugin reads of cited pages
  (§ Plugins read pages a search cited), with the owner's approval.

## 2026-10-04: Library screens — Artworks' theme filter and Select mode, a work's mark, Artists by surname

<!-- prawduct: scope=library-screens | release=v0.2.0 -->

**Why:** the owner's review of the Library screens (#169, #172-#175): the theme
dropdown on Artworks read as a filter and was an editor; search's *Image found*
badge read as if it might mean held; the Artists index sorted by first name in
one narrow table; the Wikidata identity controls all showed at once; Library ›
Topics was one long column. Plan: `build-plan-library-screens.md`.

**What:**
- `GET /api/works?theme=<id>` and `art_catalogue(action='list', theme=...)`
  narrow to one theme, composing with facets and text. Each binding composes
  Programming's `theme_work_ids` with the Library's listing restricted to those
  ids (seam rule 1). Each page carries the themes with counts against the other
  filters. An unknown theme is refused by name.
- Artworks: *Theme* is the Filter rail's first group. **Select** mode shows the
  ticks and an action bar that adds the ticked works to a theme or removes them
  from the theme being filtered. An address naming a deleted theme shows the
  works the other filters select and says the theme is gone.
- A work's mark: held, wanted and not held each have their own image style
  wherever registry works are listed (typeahead, Search results, a Topic, an
  Artist's *Their work*, a work's *More by*), each keeping its glyph and word.
  Registry works report `wanted`.
- Artworks, behaviour that changed: a filtered theme now follows the Sort menu
  rather than its own curated order, and the Sort menu is offered with it. The
  rail's *Themes* list with its *Open* buttons and *Manage themes*, and the
  toolbar's always-shown theme picker, are gone: themes are reached from
  Library › Themes, and the picker lives in Select mode's action bar.
- Library › Artists sorts by surname (the stored family name, else the last
  word once a generational suffix such as *the Younger* or *Jr.* is set aside),
  shown as posters by default with a table view in the address.
- Artist and Work pages show the Wikidata identity with one quiet *Edit*.
  Library › Topics lays each kind out in columns.

**Tests changed, and why:** each retired test asserted a design the owner's
review replaced; its successor asserts the new design.
- `test_a_theme_chip_filters_the_grid_to_its_members`,
  `test_the_rails_filter_and_its_opener_are_separate_controls_with_separate_names`
  and `test_the_rails_opener_goes_to_the_theme_rather_than_filtering_the_grid`:
  the rail's Themes list and its *Open* buttons are gone. Replaced by
  `test_a_theme_in_the_filter_rail_narrows_the_grid` and
  `test_filtering_by_a_theme_and_changing_its_members_are_different_controls`.
- `test_a_theme_is_shown_in_its_own_order_so_sort_is_not_offered`: a filtered
  theme now follows the Sort menu. Replaced by
  `test_a_theme_filtered_here_is_in_the_sort_menus_order`.
- `test_the_table_carries_the_tick_only_when_there_is_a_theme_to_add_to`: ticks
  now show only in Select mode. Replaced by
  `test_the_table_carries_the_tick_in_select_mode_only_when_there_is_a_theme_to_add_to`.
- `test_the_item_field_stays_hidden_until_change_is_pressed`: the identity's
  *Change* became one *Edit* that hides every control. Replaced by
  `test_at_rest_the_control_is_the_identity_and_one_edit`.
- `test_held_artists_are_listed_with_counts_and_open_their_page` and
  `test_held_artists_by_name_with_works_in_circulation_counted`: the index went
  from name order to surname order. Replaced by
  `test_held_artists_are_posters_in_surname_order_and_open_their_page` and
  `test_held_artists_by_surname_with_works_in_circulation_counted`.
- `test_removing_from_a_theme_takes_the_tiles_out_and_says_what_is_left` waits
  for the rail's count instead of reading it at once: the rail is recounted by a
  fetch after the tile goes, and under parallel load the immediate read saw the
  old count. Same assertion, same strength; a rail that never recounts still
  fails it, checked by removing the recount.

**Owner verification:** 2026-10-04, "Screens are good".

## 2026-10-04: A title worded differently by its holder

<!-- prawduct: scope=title-identity | release=v0.2.0 -->

**Why:** run 3 found seven of the nine open MoMA works; phase two's title gate
refused the other two on wording ("Tree" against MoMA's "The Tree"; Taeuber-Arp's
long title against MoMA's "Composition"). The owner ruled: a leading article
passes; a holder's shorter title does not pass on its own; a page the work's
Wikidata item records does. Plan: `build-plan-title-identity.md`.

**What:**
- `title_key` drops one leading English article (`the`, `a`, `an`) followed by
  whitespace in the title as written, so "A. Lincoln" keeps its initial; quotes
  or emphasis before it are passed over, and a title that would be left empty
  keeps its article. It is
  half of `work_dedup_key`, so the identity key changes with it. The generic-title
  guard compares the title without its article, so "The Portrait (Hands)" keeps
  its parenthetical.
- `phase_two.not_the_work` names `found_url`, `qid` and `link`, how the title
  gate was or was not settled.
- Phase two passes a result whose title differs when the work has a QID and the
  result's `url` is exactly one of `Registry.pages_about(qid)`. The artist check
  still runs. The registry is asked at most once per work, only on a differing
  title; one that cannot be asked means no link (`phase_two.link_unavailable`).
  The review card says the title differs and what identified it.
- The container hands phase two the deployment's registry.
- The startup repair re-derives every stored key, not only those whose title it
  re-cleaned, and reports re-keyed rows apart (`works.rekeyed`, at INFO). Before
  this, a change to the derivation alone left stored keys under the old rule.
  **A rollback does not undo it:** the previous build re-keys only re-cleaned
  titles, so article-titled rows stay split from new proposals until this build
  is redeployed or the pre-deploy catalogue copy is restored.

**Tests changed, and why:**
- `test_a_stored_title_the_rules_do_not_reach_is_left_exactly_as_it_is`: it
  seeded keys no writer produces (`title.lower()`) and asserted them unchanged.
  The repair now rewrites any stale key, so the rows are seeded with the keys the
  rules derive. It still asserts title and key unchanged, and now also that no
  repair is logged.
- `test_a_work_the_curator_already_rejected_is_not_proposed_again` and
  `test_the_stored_estimate_counts_the_works_actually_proposed`: they wrote the
  old derivation's key out by hand (`salvador dali::the elephants`). They now
  seed the key the rules derive, with the artist the row would carry.
- The shared `propose` fixture defaults a key to its title's derivation rather
  than `title.lower()`, so a test that restarts the plane does not see its rows
  re-keyed.
