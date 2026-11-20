-- The catalogue Arrt's code at 6e4faae5 made over the synthetic seed in tools/old_catalogue.py.
BEGIN TRANSACTION;
CREATE TABLE acquisition_queue (
    artwork_id   TEXT PRIMARY KEY REFERENCES artworks(id),
    failures     INTEGER NOT NULL DEFAULT 0 CHECK (failures >= 0),
    next_try_at  TEXT,
    detail       TEXT,
    source_id    TEXT REFERENCES sources(id)
);
INSERT INTO "acquisition_queue" VALUES('work-sunday',1,NULL,'the museum did not answer',NULL);
CREATE TABLE affinities (
    id             TEXT PRIMARY KEY,
    kind           TEXT NOT NULL,
    -- The thing itself as it was named, and a string rather than a foreign key.
    -- The artists the curator reacts to are often ones they could not
    -- have named, so the common case at the moment a judgment is written is a
    -- name with no row in this catalogue at all.
    value          TEXT NOT NULL,
    sentiment      TEXT NOT NULL,
    -- Independent of `sentiment`, because one scalar is a bug: "meh on Magritte,
    -- but open to learning more" is two facts, and collapsing them silently
    -- blacklists an artist the curator asked to keep hearing about.
    open_to_more   INTEGER NOT NULL,
    derivation     TEXT NOT NULL,
    -- Required by the write path for `inferred` and `observed`, and NOT NULL
    -- here would say the same thing wrongly: it is a rule about which
    -- derivations need evidence, not about the column.
    rationale      TEXT,
    artist_id      TEXT REFERENCES artists(id),
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);
INSERT INTO "affinities" VALUES('affinity-hopper','artist','Edward Hopper','loves',1,'stated',NULL,'artist-hopper','2026-09-01T12:00:00+00:00','2026-09-01T12:00:00+00:00');
CREATE TABLE artists (
    id             TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    nationality    TEXT,
    born           INTEGER,
    died           INTEGER,
    lifespan_text  TEXT,
    biography      TEXT,
    family_name    TEXT,
    given_name     TEXT,
    display_nationality TEXT,
    wikidata_qid   TEXT,
    wikidata_qid_set_by TEXT
);
INSERT INTO "artists" VALUES('artist-hopper','Edward Hopper','American',1882,1967,NULL,NULL,NULL,NULL,NULL,NULL,NULL);
CREATE TABLE artworks (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    artist_id     TEXT REFERENCES artists(id),
    date_created  TEXT,
    medium        TEXT,
    dimensions    TEXT,
    description   TEXT,
    rights        TEXT,
    status        TEXT NOT NULL,
    accepted_at   TEXT,
    created_at    TEXT NOT NULL,
    commentary    TEXT,
    wikidata_qid  TEXT,
    wikidata_qid_set_by TEXT
);
INSERT INTO "artworks" VALUES('work-nighthawks','Nighthawks','artist-hopper','1942','Oil on canvas',NULL,NULL,NULL,'accepted','2026-09-01T12:00:00+00:00','2026-09-01T12:00:00+00:00',NULL,NULL,NULL);
INSERT INTO "artworks" VALUES('work-automat','Automat','artist-hopper','1942','Oil on canvas',NULL,NULL,NULL,'accepted','2026-09-01T12:00:00+00:00','2026-09-01T12:00:00+00:00',NULL,NULL,NULL);
INSERT INTO "artworks" VALUES('work-sunday','Early Sunday Morning','artist-hopper','1942','Oil on canvas',NULL,NULL,NULL,'accepted','2026-09-01T12:00:00+00:00','2026-09-01T12:00:00+00:00',NULL,NULL,NULL);
INSERT INTO "artworks" VALUES('work-rooms','Rooms by the Sea','artist-hopper','1942','Oil on canvas',NULL,NULL,NULL,'archived','2026-09-01T12:00:00+00:00','2026-09-01T12:00:00+00:00',NULL,NULL,NULL);
CREATE TABLE candidate_images (
    id                   TEXT PRIMARY KEY,
    candidate_work_id    TEXT NOT NULL REFERENCES candidate_works(id),
    url                  TEXT NOT NULL,
    preview_url          TEXT,
    preview_path         TEXT,
    provider             TEXT NOT NULL,
    source_class         TEXT NOT NULL,
    acquisition_method   TEXT NOT NULL,
    estimated_width      INTEGER,
    estimated_height     INTEGER,
    rights_status        TEXT,
    confidence           REAL NOT NULL,
    quality_score        REAL,
    selection_rationale  TEXT,
    is_selected          INTEGER NOT NULL,
    rejected_at          TEXT
);
INSERT INTO "candidate_images" VALUES('image-hotel','candidate-hotel','https://museum.example/hotel-room.jpg',NULL,NULL,'artic','institutional','direct_http',NULL,NULL,NULL,0.7,NULL,NULL,1,NULL);
CREATE TABLE candidate_works (
    id                 TEXT PRIMARY KEY,
    discovery_run_id   TEXT NOT NULL REFERENCES discovery_runs(id),
    artwork_id         TEXT REFERENCES artworks(id),
    proposed_title     TEXT NOT NULL,
    proposed_artist    TEXT,
    rationale          TEXT NOT NULL,
    work_dedup_key     TEXT NOT NULL,
    -- Nullable so the widening step can add it to files written before
    -- collections could be browsed. A null is `proposed`: nothing but phase 1
    -- could mint a candidate work then, so the absent value has one meaning.
    provenance         TEXT,
    -- Which browse query produced an offered work, and how many works that query
    -- matched in the collection. Both null for a proposed work, which no query
    -- produced. They are stored as facts rather than composed into `rationale`
    -- because the sentence they belong to is per-QUERY: `product-brief.md` asks
    -- that a curator be able to tell one-of-four-hundred from one-of-one, and the
    -- surface says that once for the group. `matched` is the collection's total
    -- and is deliberately not capped by `offered_works_per_run` — the cap is what
    -- the reader reconciles it against, so capping it here would destroy the
    -- comparison the requirement exists for.
    offered_for_artist     TEXT,
    offered_artist_matched INTEGER,
    -- The source (provider id) that offered the work, kept on the work because
    -- the scan it arrived with can be turned down and replaced by another
    -- museum's. Null on proposed and chosen works, and on offers recorded before
    -- it was kept; nullable so widening reaches older files.
    offered_by             TEXT,
    -- The Wikidata item a chosen work was asked for by. Null on proposed and
    -- offered works, which no item named; nullable so widening reaches older files.
    wikidata_qid           TEXT,
    -- Phase 1's word on whether a source it was given confirms a work it
    -- proposed: 1, 0, or null for no word. Nullable so widening reaches older
    -- files, whose proposals read as unconfirmed-or-not unknown, never confirmed.
    source_confirmed       INTEGER,
    resolution_status  TEXT NOT NULL,
    unresolved_reason  TEXT,
    verdict            TEXT NOT NULL,
    rejected_reason    TEXT,
    decided_at         TEXT
);
INSERT INTO "candidate_works" VALUES('candidate-automat','run-1','work-automat','Automat','Edward Hopper','A realist of the American city.','hopper|automat','proposed',NULL,NULL,NULL,NULL,NULL,'resolved',NULL,'accepted',NULL,'2026-09-01T12:00:00+00:00');
INSERT INTO "candidate_works" VALUES('candidate-hotel','run-1',NULL,'Hotel Room','Edward Hopper','A realist of the American city.','hopper|hotel room','proposed',NULL,NULL,NULL,NULL,NULL,'resolved',NULL,'wanted',NULL,'2026-09-01T12:00:00+00:00');
CREATE TABLE catalogue_opened (
    id                    INTEGER PRIMARY KEY CHECK (id = 1),
    release               TEXT NOT NULL,
    opened_at             TEXT NOT NULL,
    migrations_completed  INTEGER NOT NULL
);
INSERT INTO "catalogue_opened" VALUES(1,'0.11.0','2026-09-01T12:00:00+00:00',1);
CREATE TABLE clients (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL UNIQUE,
    created_at       TEXT NOT NULL,
    token_verifier   TEXT,
    token_issued_at  TEXT
);
INSERT INTO "clients" VALUES('client-hall','The Pi in the hall','2026-09-01T12:00:00+00:00','verifier-of-the-hall-token','2026-09-01T12:00:00+00:00');
CREATE TABLE default_theme_offers (
    artwork_id  TEXT PRIMARY KEY,
    offered_at  TEXT NOT NULL
);
INSERT INTO "default_theme_offers" VALUES('work-nighthawks','2026-09-01T12:00:00+00:00');
INSERT INTO "default_theme_offers" VALUES('work-automat','2026-09-01T12:00:00+00:00');
INSERT INTO "default_theme_offers" VALUES('work-sunday','2026-09-01T12:00:00+00:00');
INSERT INTO "default_theme_offers" VALUES('work-rooms','2026-09-01T12:00:00+00:00');
CREATE TABLE discovery_runs (
    id                     TEXT PRIMARY KEY,
    kind                   TEXT NOT NULL,
    -- A resolve run's parent is the run that originally proposed these works.
    -- Cost rolls up through this chain, which is what keeps "what did asking for
    -- Dali cost" answerable once spend is spread across several runs.
    parent_run_id          TEXT REFERENCES discovery_runs(id),
    intent_text            TEXT,
    strategy               TEXT,
    initiated_by           TEXT NOT NULL,
    status                 TEXT NOT NULL,
    estimated_cost_usd     TEXT,
    actual_cost_usd        TEXT,
    approval_required      INTEGER NOT NULL,
    unresolved_work_count  INTEGER,
    started_at             TEXT NOT NULL,
    completed_at           TEXT,
    -- The theme a Get's accepted works join instead of the default. Programming's
    -- id, so deliberately no REFERENCES clause: it is an opaque reference across
    -- the Library/Programming seam that may fail to resolve once the theme is
    -- deleted. Null means the default, and is what every run before Gets could
    -- name a theme reads as; nullable so widening reaches older files.
    destination_theme_id   TEXT,
    -- Why the run's worker ended it, written only by `failed` and
    -- `halted_by_budget`. Nullable so widening reaches older files, whose runs
    -- ended before a reason was kept and read back as giving none.
    end_reason             TEXT,
    -- The Watch whose pass started the run. No REFERENCES clause: a run outlives
    -- its Watch. Nullable so widening reaches older files, whose runs were all
    -- started by a person or an agent.
    watch_id               TEXT
);
INSERT INTO "discovery_runs" VALUES('run-1','discovery',NULL,'American realism',NULL,'web_ui','completed','0.05','0.04',0,NULL,'2026-09-01T12:00:00+00:00','2026-09-01T12:00:00+00:00',NULL,NULL,'watch-hopper');
CREATE TABLE displays (
    id               TEXT PRIMARY KEY,
    identity         TEXT NOT NULL UNIQUE,
    client_id        TEXT REFERENCES clients(id),
    output           TEXT NOT NULL,
    kind             TEXT,
    first_seen       TEXT NOT NULL
);
INSERT INTO "displays" VALUES('display-hall','client-hall/hdmi-a-1','client-hall','hdmi-a-1',NULL,'2026-09-01T12:00:00+00:00');
CREATE TABLE history_events (
    id           TEXT PRIMARY KEY,
    kind         TEXT NOT NULL,
    occurred_at  TEXT NOT NULL,
    work_id      TEXT,
    run_id       TEXT,
    wall_id      TEXT,
    theme_id     TEXT,
    detail       TEXT
);
INSERT INTO "history_events" VALUES('event-1','wall.hung','2026-09-01T12:00:00+00:00',NULL,NULL,'wall-main','theme-late',NULL);
CREATE TABLE label_outputs (
    id               TEXT PRIMARY KEY,
    client_id        TEXT NOT NULL REFERENCES clients(id),
    output           TEXT NOT NULL,
    wall_id          TEXT REFERENCES walls(id)
);
INSERT INTO "label_outputs" VALUES('label-hall','client-hall','epd-0','wall-main');
CREATE TABLE mat_colors (
    id          TEXT PRIMARY KEY,
    artwork_id  TEXT NOT NULL REFERENCES artworks(id),
    hex_rgb     TEXT NOT NULL,
    method      TEXT NOT NULL,
    is_current  INTEGER NOT NULL,
    lab_l       REAL,
    lab_a       REAL,
    lab_b       REAL,
    reason      TEXT,
    model_id    TEXT,
    chosen_at   TEXT NOT NULL
);
INSERT INTO "mat_colors" VALUES('mat-nighthawks','work-nighthawks','#27285b','vision_model',1,NULL,NULL,NULL,NULL,NULL,'2026-09-01T12:00:00+00:00');
CREATE TABLE originals (
    id             TEXT PRIMARY KEY,
    artwork_id     TEXT NOT NULL UNIQUE REFERENCES artworks(id),
    source_id      TEXT NOT NULL REFERENCES sources(id),
    relative_path  TEXT NOT NULL,
    width          INTEGER NOT NULL,
    height         INTEGER NOT NULL,
    -- A zero-byte file is the 2024 pipeline's known download failure. The
    -- catalogue must not be able to record one as a held original.
    byte_size      INTEGER NOT NULL CHECK (byte_size > 0),
    content_hash   TEXT NOT NULL,
    -- How the fetch that produced these bytes ended. Nullable, because the column
    -- was added to a table that already had rows on disk and the widening step
    -- can only add columns that allow NULL — a null here means "written before
    -- this was recorded", which readers treat as complete rather than as partial.
    fetch_status   TEXT
);
INSERT INTO "originals" VALUES('original-nighthawks','work-nighthawks','source-work-nighthawks','raw/work-nighthawks.tif',6000,4000,90000000,'hash-nighthawks','ok');
CREATE TABLE renditions (
    id                   TEXT PRIMARY KEY,
    artwork_id           TEXT NOT NULL REFERENCES artworks(id),
    kind                 TEXT NOT NULL,
    target_width         INTEGER NOT NULL,
    target_height        INTEGER NOT NULL,
    relative_path        TEXT NOT NULL,
    source_content_hash  TEXT NOT NULL,
    generated_at         TEXT NOT NULL,
    content_sha256       TEXT,
    byte_size            INTEGER,
    -- The rule a presentation master was made by. Nullable because the
    -- widening step can only add a column that allows NULL.
    layout               TEXT
);
INSERT INTO "renditions" VALUES('rendition-thumbnail','work-nighthawks','thumbnail',400,300,'thumbs/work-nighthawks.jpg','hash-nighthawks','2026-09-01T12:00:00+00:00',NULL,NULL,NULL);
INSERT INTO "renditions" VALUES('rendition-master','work-nighthawks','presentation_master',400,300,'masters/work-nighthawks.jpg','hash-nighthawks','2026-09-01T12:00:00+00:00',NULL,NULL,NULL);
CREATE TABLE reported_screens (
    display_id        TEXT NOT NULL REFERENCES displays(id) ON DELETE CASCADE,
    width_px          INTEGER NOT NULL,
    height_px         INTEGER NOT NULL,
    last_reported_at  TEXT NOT NULL,
    PRIMARY KEY (display_id, width_px, height_px)
);
INSERT INTO "reported_screens" VALUES('display-hall',3840,2160,'2026-09-01T12:00:00+00:00');
CREATE TABLE resolve_run_works (
    resolve_run_id     TEXT NOT NULL REFERENCES discovery_runs(id),
    candidate_work_id  TEXT NOT NULL REFERENCES candidate_works(id),
    PRIMARY KEY (resolve_run_id, candidate_work_id)
);
CREATE TABLE run_citations (
    discovery_run_id  TEXT NOT NULL REFERENCES discovery_runs(id),
    url               TEXT NOT NULL,
    position          INTEGER NOT NULL,
    PRIMARY KEY (discovery_run_id, url)
);
INSERT INTO "run_citations" VALUES('run-1','https://encyclopedia.example/hopper',0);
CREATE TABLE scene_pins (
    scene_id  TEXT NOT NULL REFERENCES scenes(id),
    wall_id   TEXT NOT NULL,
    work_id   TEXT NOT NULL,
    PRIMARY KEY (scene_id, wall_id)
);
INSERT INTO "scene_pins" VALUES('scene-1','wall-main','work-nighthawks');
CREATE TABLE scenes (
    id          TEXT PRIMARY KEY,
    status      TEXT NOT NULL CHECK (status IN ('draft', 'live', 'ended')),
    lifetime    TEXT CHECK (lifetime IN ('preview', 'hold')),
    starts_at   TEXT,
    until       TEXT,
    created_at  TEXT NOT NULL,
    ended_at    TEXT
);
INSERT INTO "scenes" VALUES('scene-1','ended','hold',NULL,NULL,'2026-09-01T12:00:00+00:00','2026-09-01T12:00:00+00:00');
CREATE TABLE settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    updated_by  TEXT NOT NULL
);
INSERT INTO "settings" VALUES('label_units','metric','2026-09-01T12:00:00+00:00','web_ui');
CREATE TABLE showings (
    wall_id       TEXT NOT NULL,
    started_at    TEXT NOT NULL,
    work_id       TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL,
    ended_at      TEXT,
    PRIMARY KEY (wall_id, started_at)
);
INSERT INTO "showings" VALUES('wall-main','2026-09-01T12:00:00+00:00','work-nighthawks','2026-09-01T12:00:00+00:00',NULL);
CREATE TABLE sightings (
    wikidata_qid  TEXT NOT NULL,
    url           TEXT NOT NULL,
    PRIMARY KEY (wikidata_qid, url)
);
INSERT INTO "sightings" VALUES('Q900001','https://museum.example/hotel-room');
CREATE TABLE sources (
    id                   TEXT PRIMARY KEY,
    artwork_id           TEXT NOT NULL REFERENCES artworks(id),
    url                  TEXT NOT NULL,
    provider             TEXT NOT NULL,
    source_class         TEXT NOT NULL,
    acquisition_method   TEXT NOT NULL,
    rights_status        TEXT NOT NULL,
    is_primary           INTEGER NOT NULL,
    confidence           REAL,
    selection_rationale  TEXT,
    last_fetch_status    TEXT,
    last_fetched_at      TEXT
);
INSERT INTO "sources" VALUES('source-work-nighthawks','work-nighthawks','https://museum.example/work-nighthawks','artic','institutional','dezoomify','public_domain',1,NULL,NULL,'ok','2026-09-01T12:00:00+00:00');
INSERT INTO "sources" VALUES('source-work-automat','work-automat','https://museum.example/work-automat','artic','institutional','dezoomify','public_domain',1,NULL,NULL,'ok','2026-09-01T12:00:00+00:00');
INSERT INTO "sources" VALUES('source-work-sunday','work-sunday','https://museum.example/work-sunday','artic','institutional','dezoomify','public_domain',1,NULL,NULL,'ok','2026-09-01T12:00:00+00:00');
INSERT INTO "sources" VALUES('source-work-rooms','work-rooms','https://museum.example/work-rooms','artic','institutional','dezoomify','public_domain',1,NULL,NULL,'ok','2026-09-01T12:00:00+00:00');
CREATE TABLE spend_records (
    id                TEXT PRIMARY KEY,
    discovery_run_id  TEXT REFERENCES discovery_runs(id),
    artwork_id        TEXT REFERENCES artworks(id),
    category          TEXT NOT NULL,
    model_id          TEXT,
    input_tokens      INTEGER,
    output_tokens     INTEGER,
    units             INTEGER,
    -- Decimal text rather than a REAL. This column is money, and SQLite's only
    -- numeric types are integers and IEEE doubles.
    cost_usd          TEXT NOT NULL,
    occurred_at       TEXT NOT NULL
);
INSERT INTO "spend_records" VALUES('spend-discovery','run-1',NULL,'discovery_tokens',NULL,NULL,NULL,NULL,'0.04','2026-09-01T12:00:00+00:00');
INSERT INTO "spend_records" VALUES('spend-conversation',NULL,NULL,'conversation_tokens',NULL,NULL,NULL,NULL,'0.01','2026-09-01T12:00:00+00:00');
CREATE TABLE theme_assignments (
    wall_id      TEXT PRIMARY KEY REFERENCES walls(id),
    theme_id     TEXT NOT NULL REFERENCES themes(id),
    assigned_at  TEXT NOT NULL
);
INSERT INTO "theme_assignments" VALUES('wall-main','theme-late','2026-09-01T12:00:00+00:00');
INSERT INTO "theme_assignments" VALUES('wall-study','theme-all','2026-09-01T12:00:00+00:00');
CREATE TABLE theme_memberships (
    theme_id    TEXT NOT NULL REFERENCES themes(id),
    artwork_id  TEXT NOT NULL REFERENCES artworks(id),
    position    INTEGER,
    added_at    TEXT NOT NULL,
    PRIMARY KEY (theme_id, artwork_id)
);
INSERT INTO "theme_memberships" VALUES('theme-all','work-nighthawks',1,'2026-09-01T12:00:00+00:00');
INSERT INTO "theme_memberships" VALUES('theme-all','work-automat',2,'2026-09-01T12:00:00+00:00');
INSERT INTO "theme_memberships" VALUES('theme-all','work-sunday',3,'2026-09-01T12:00:00+00:00');
INSERT INTO "theme_memberships" VALUES('theme-all','work-rooms',4,'2026-09-01T12:00:00+00:00');
INSERT INTO "theme_memberships" VALUES('theme-late','work-nighthawks',1,'2026-09-01T12:00:00+00:00');
INSERT INTO "theme_memberships" VALUES('theme-late','work-automat',2,'2026-09-01T12:00:00+00:00');
INSERT INTO "theme_memberships" VALUES('theme-mornings','work-sunday',1,'2026-09-01T12:00:00+00:00');
CREATE TABLE themes (
    id                        TEXT PRIMARY KEY,
    name                      TEXT NOT NULL UNIQUE,
    description               TEXT,
    created_at                TEXT NOT NULL,
    is_default                INTEGER NOT NULL DEFAULT 0,
    is_hidden                 INTEGER NOT NULL DEFAULT 0
);
INSERT INTO "themes" VALUES('theme-all','All works',NULL,'2026-09-01T12:00:00+00:00',1,0);
INSERT INTO "themes" VALUES('theme-late','Late night',NULL,'2026-09-01T12:00:00+00:00',0,0);
INSERT INTO "themes" VALUES('theme-mornings','Mornings',NULL,'2026-09-01T12:00:00+00:00',0,0);
CREATE TABLE walls (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL UNIQUE,
    created_at       TEXT NOT NULL,
    display_id       TEXT REFERENCES displays(id),
    -- How the wall's Player draws the mat, or NULL for its own default. The
    -- values are checked by the service: a CHECK here would bind new files
    -- only, since an added column cannot carry one onto an older file.
    mat_mode         TEXT,
    -- How the wall plays its theme: how long each work stays up, and whether in
    -- shuffled order. NULL on either is the deployment default rather than
    -- "unset", so a wall that has chosen nothing is an ordinary wall.
    rotation_interval_seconds INTEGER,
    shuffle          INTEGER,
    -- The shapes the wall shows, as width over height: the tallest and the
    -- widest. NULL on either is no limit on that side, which is every wall
    -- that has chosen nothing.
    min_aspect_ratio REAL,
    max_aspect_ratio REAL
);
INSERT INTO "walls" VALUES('wall-main','The wall','2026-09-01T12:00:00+00:00','display-hall',NULL,600,1,NULL,NULL);
INSERT INTO "walls" VALUES('wall-study','Study','2026-09-01T12:00:00+00:00',NULL,NULL,NULL,NULL,NULL,NULL);
CREATE TABLE watches (
    id               TEXT PRIMARY KEY,
    intent_text      TEXT NOT NULL,
    enabled          INTEGER NOT NULL,
    cadence          TEXT,
    monthly_cap_usd  TEXT,
    created_at       TEXT NOT NULL,
    created_by       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    updated_by       TEXT NOT NULL,
    last_attempt_at  TEXT,
    last_run_id      TEXT,
    last_refusal     TEXT
);
INSERT INTO "watches" VALUES('watch-hopper','More Hopper',1,NULL,NULL,'2026-09-01T12:00:00+00:00','web_ui','2026-09-01T12:00:00+00:00','web_ui',NULL,NULL,NULL);
CREATE TABLE work_exclusions (
    artwork_id   TEXT PRIMARY KEY,
    excluded_at  TEXT NOT NULL
);
INSERT INTO "work_exclusions" VALUES('work-sunday','2026-09-01T12:00:00+00:00');
CREATE TABLE work_facets (
    id           TEXT PRIMARY KEY,
    artwork_id   TEXT NOT NULL REFERENCES artworks(id),
    kind         TEXT NOT NULL,
    value        TEXT NOT NULL COLLATE NOCASE,
    derivation   TEXT NOT NULL,
    source_note  TEXT,
    created_at   TEXT NOT NULL,
    value_qid    TEXT
);
INSERT INTO "work_facets" VALUES('facet-diner','work-nighthawks','subject','diner','sourced',NULL,'2026-09-01T12:00:00+00:00',NULL);
CREATE INDEX artworks_by_status ON artworks(status);
CREATE UNIQUE INDEX work_facets_once_per_work ON work_facets(artwork_id, kind, value);
CREATE INDEX work_facets_by_value ON work_facets(kind, value);
CREATE INDEX work_facets_by_artwork ON work_facets(artwork_id);
CREATE INDEX work_facets_by_item ON work_facets(value_qid);
CREATE UNIQUE INDEX themes_one_default ON themes(is_default) WHERE is_default = 1;
CREATE UNIQUE INDEX displays_one_per_output ON displays(client_id, output) WHERE client_id IS NOT NULL;
CREATE UNIQUE INDEX label_outputs_one_per_output ON label_outputs(client_id, output);
CREATE INDEX label_outputs_by_wall ON label_outputs(wall_id);
CREATE UNIQUE INDEX walls_one_per_display ON walls(display_id) WHERE display_id IS NOT NULL;
CREATE INDEX theme_assignments_by_theme ON theme_assignments(theme_id);
CREATE INDEX sources_by_artwork ON sources(artwork_id);
CREATE UNIQUE INDEX sources_one_primary ON sources(artwork_id) WHERE is_primary = 1;
CREATE INDEX renditions_by_content
    ON renditions(content_sha256);
CREATE UNIQUE INDEX renditions_by_geometry
    ON renditions(artwork_id, kind, target_width, target_height);
CREATE INDEX mat_colors_by_artwork ON mat_colors(artwork_id);
CREATE UNIQUE INDEX mat_colors_one_current ON mat_colors(artwork_id) WHERE is_current = 1;
CREATE INDEX theme_memberships_by_artwork ON theme_memberships(artwork_id);
CREATE INDEX showings_by_work ON showings(work_id, last_seen_at);
CREATE INDEX scenes_by_status ON scenes(status);
CREATE INDEX history_events_by_time ON history_events(occurred_at);
CREATE INDEX history_events_by_wall ON history_events(wall_id, occurred_at) WHERE wall_id IS NOT NULL;
CREATE INDEX discovery_runs_by_status ON discovery_runs(status);
CREATE INDEX discovery_runs_by_parent ON discovery_runs(parent_run_id);
CREATE INDEX candidate_works_by_dedup_key ON candidate_works(work_dedup_key);
CREATE INDEX candidate_works_by_run ON candidate_works(discovery_run_id);
CREATE INDEX candidate_images_by_work ON candidate_images(candidate_work_id);
CREATE UNIQUE INDEX candidate_images_one_selected
    ON candidate_images(candidate_work_id) WHERE is_selected = 1;
CREATE UNIQUE INDEX affinities_one_per_thing ON affinities(kind, value);
CREATE INDEX spend_records_by_time ON spend_records(occurred_at);
CREATE INDEX spend_records_by_run ON spend_records(discovery_run_id);
CREATE INDEX discovery_runs_by_watch ON discovery_runs(watch_id);
CREATE INDEX resolve_run_works_by_work ON resolve_run_works(candidate_work_id);
COMMIT;
