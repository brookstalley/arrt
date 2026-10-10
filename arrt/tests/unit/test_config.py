"""Deployment configuration resolution.

The values here differ between the dev Mac and the Pi, so the failure this
module exists to prevent is a plausible-looking default that quietly writes the
catalogue somewhere unintended. These tests assert the refusals, not just the
happy path.
"""

import os
from decimal import Decimal
from pathlib import Path

import pytest

from arrt.config import (
    CATALOGUE_FILENAME,
    DEFAULT_ASK_MODEL,
    DEFAULT_ASK_STEP_LIMIT,
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_ROTATION_INTERVAL_SECONDS,
    DEFAULT_ROTATION_SHUFFLE,
    ConfigError,
    Settings,
    retired_settings_in,
)
from arrt.library.dimensions import Units


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Resolve from this process's environment and nothing else.

    `from_env` calls `load_dotenv()` with no path, and dotenv searches from
    `config.py`'s own directory upward — never the cwd — so chdir'ing to a
    scratch directory isolates nothing.

    The stub is still needed after the 2026-08-05 precedence fix, for the half
    that fix did not change: a name this fixture *deletes* is absent from the
    environment, so a real `.env` is free to supply it, and the documented
    setup step (`cp .env.example .env`) creates exactly that file. Every
    missing-value assertion below would otherwise be green only on a machine
    where nobody has followed the README. Names this fixture *sets* no longer
    need it — that is what `test_an_exported_value_beats_the_dotenv_file`
    pins.
    """
    monkeypatch.setattr("arrt.config.load_dotenv", lambda **_: False)
    for name in (
        "ART_ROOT",
        "CURATION_HOST",
        "CURATION_PORT",
        "ROTATION_INTERVAL_SECONDS",
        "ROTATION_SHUFFLE",
        "LABEL_UNITS",
        "BACKUP_DIR",
        "BACKUP_INTERVAL_SECONDS",
        "BACKUP_KEEP",
        "MONTHLY_BUDGET_USD",
    ):
        monkeypatch.delenv(name, raising=False)


def _dotenv_supplying(monkeypatch, **values):
    """Stand in for `python-dotenv`, honouring its real precedence flag.

    Measured against the installed python-dotenv on 2026-08-05: with no
    `override` an entry already in `os.environ` is left alone, and the file's
    value is used only for names that are absent; `override=True` replaces
    both. The fake reproduces exactly that, so it is the *library* being stood
    in for — `Settings.from_env` itself is driven for real, and if it ever
    passes `override=True` again the fake honours it and the caller below goes
    red. A stub that simply ignored the flag would make that mutation
    invisible, which is the whole failure this pair of tests exists to catch.
    """

    def loader(*_args, override=False, **_kwargs):
        for name, value in values.items():
            if override or name not in os.environ:
                monkeypatch.setenv(name, value)
        return True

    return loader


def test_an_exported_value_beats_the_dotenv_file(monkeypatch):
    """`.env` supplies defaults; whatever is already exported wins.

    The inverse shipped until 2026-08-05 and made
    `ART_ROOT=/tmp/scratch uv run python -m arrt` boot against the real
    catalogue — the export was discarded rather than refused, so the wrong
    tree looked exactly like the right one.
    """
    monkeypatch.setenv("ART_ROOT", "/from-the-environment")
    monkeypatch.setattr(
        "arrt.config.load_dotenv",
        _dotenv_supplying(monkeypatch, ART_ROOT="/from-the-dotenv-file"),
    )

    assert Settings.from_env().art_root == Path("/from-the-environment")


def test_the_dotenv_file_still_supplies_what_the_environment_does_not(monkeypatch):
    """The other half, and it is not redundant with the test above.

    Deleting the `load_dotenv()` call outright would satisfy that one and
    break every machine set up by the documented `cp .env.example .env` step.
    This is the case that test cannot rescue.
    """
    monkeypatch.delenv("ART_ROOT", raising=False)
    monkeypatch.setattr(
        "arrt.config.load_dotenv",
        _dotenv_supplying(monkeypatch, ART_ROOT="/from-the-dotenv-file"),
    )

    assert Settings.from_env().art_root == Path("/from-the-dotenv-file")


def test_a_missing_art_root_fails_fast_and_names_the_file_to_fix():
    with pytest.raises(ConfigError) as caught:
        Settings.from_env()

    assert "ART_ROOT" in str(caught.value)
    assert ".env" in str(caught.value)


def test_an_empty_art_root_is_refused_rather_than_treated_as_the_cwd(monkeypatch):
    monkeypatch.setenv("ART_ROOT", "")

    with pytest.raises(ConfigError, match="ART_ROOT"):
        Settings.from_env()


def test_the_catalogue_is_anchored_under_art_root(monkeypatch, tmp_path):
    monkeypatch.setenv("ART_ROOT", str(tmp_path))

    settings = Settings.from_env()

    assert settings.catalogue_path == tmp_path / CATALOGUE_FILENAME
    assert settings.catalogue_path.parent == settings.art_root


def test_the_defaults_bind_loopback_on_the_protocol_port(monkeypatch, tmp_path):
    # Asserted against literals, not against the constants themselves — that
    # form agrees with whatever value they are changed to. Widening the bind
    # to a non-loopback address is a deliberate exposure decision, and this
    # should fail when someone makes it quietly.
    monkeypatch.setenv("ART_ROOT", str(tmp_path))

    settings = Settings.from_env()

    assert (settings.host, settings.port) == ("127.0.0.1", 8770)
    assert (DEFAULT_HOST, DEFAULT_PORT) == ("127.0.0.1", 8770)


def test_a_non_numeric_port_is_rejected_with_the_offending_value(monkeypatch, tmp_path):
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("CURATION_PORT", "eight-thousand")

    with pytest.raises(ConfigError) as caught:
        Settings.from_env()

    assert "eight-thousand" in str(caught.value)


@pytest.mark.parametrize("port", ["0", "65536", "-1"])
def test_a_port_outside_the_valid_range_is_refused(monkeypatch, tmp_path, port):
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("CURATION_PORT", port)

    with pytest.raises(ConfigError, match="between 1 and 65535"):
        Settings.from_env()


def test_an_explicit_host_and_port_override_the_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("CURATION_HOST", "0.0.0.0")  # noqa: S104 -- the point of the test
    monkeypatch.setenv("CURATION_PORT", "9001")

    settings = Settings.from_env()

    assert (settings.host, settings.port) == ("0.0.0.0", 9001)  # noqa: S104 -- the configured value is what is asserted


# -- the wall's own settings ---------------------------------------------------
#
# Every value below reaches the manifest or the mat. A silently wrong one is not
# a crash: it is a wall running at the wrong pace, or a mat composed for a
# television that is not on the wall.


def test_the_manifest_and_heartbeat_are_anchored_under_art_root_and_named_per_wall(monkeypatch, tmp_path):
    """Both planes have to agree where these are, so neither is configurable.

    And both are **per wall**: the file set is indexed by wall id, which is what
    keeps one room's rewrite out of another room's file and lets health name which
    wall is silent. A settings object holding one path apiece is what let a second
    wall's theme overwrite the first's until 2026-08-12.
    """
    monkeypatch.setenv("ART_ROOT", str(tmp_path))

    settings = Settings.from_env()

    assert settings.manifest_v2_path("living-room") == tmp_path / "theme-manifest-living-room.v2.json"
    assert settings.heartbeat_path("living-room") == tmp_path / "display-heartbeat-living-room.json"
    # Two walls, two files. The assertion the singular fields could not make.
    assert settings.manifest_v2_path("study") != settings.manifest_v2_path("living-room")


def test_the_shipped_rotation_defaults_are_what_the_wall_runs_today(monkeypatch, tmp_path):
    """Carried forward from the 2024 plane; the cutover must not change the pace."""
    monkeypatch.setenv("ART_ROOT", str(tmp_path))

    settings = Settings.from_env()

    assert settings.rotation_interval_seconds == DEFAULT_ROTATION_INTERVAL_SECONDS
    assert settings.rotation_shuffle == DEFAULT_ROTATION_SHUFFLE


def test_a_deployment_can_override_every_wall_setting(monkeypatch, tmp_path):
    """Values no default could produce, so a setting read from the wrong name would show."""
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("ROTATION_INTERVAL_SECONDS", "931")
    monkeypatch.setenv("ROTATION_SHUFFLE", "false")

    settings = Settings.from_env()

    assert settings.rotation_interval_seconds == 931
    assert settings.rotation_shuffle is False


@pytest.mark.parametrize("spelling", ["false", "False", "FALSE", "0", "no", "off", " off "])
def test_every_spelling_of_off_turns_shuffle_off(monkeypatch, tmp_path, spelling):
    """The hazard this reader exists for: `bool("false")` is True in Python.

    A lenient reader turns a deliberate "off" into "on" and reports nothing, on
    the setting that reaches the manifest and drives the wall.
    """
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("ROTATION_SHUFFLE", spelling)

    assert Settings.from_env().rotation_shuffle is False


@pytest.mark.parametrize("spelling", ["true", "True", "1", "yes", "on"])
def test_every_spelling_of_on_turns_shuffle_on(monkeypatch, tmp_path, spelling):
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("ROTATION_SHUFFLE", spelling)

    assert Settings.from_env().rotation_shuffle is True


def test_a_flag_that_is_neither_is_refused_rather_than_guessed(monkeypatch, tmp_path):
    """Guessing here is how "shuffle=maybe" becomes "shuffle=on" with nothing said."""
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("ROTATION_SHUFFLE", "sometimes")

    with pytest.raises(ConfigError, match="must be true or false, got 'sometimes'"):
        Settings.from_env()


@pytest.mark.parametrize(
    "name",
    [
        "ROTATION_INTERVAL_SECONDS",
        "BACKUP_INTERVAL_SECONDS",
        "BACKUP_KEEP",
        "QUALITY_MINIMUM_PX",
    ],
)
def test_a_non_numeric_whole_number_setting_is_refused_with_the_offending_value(monkeypatch, tmp_path, name):
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv(name, "wide")

    with pytest.raises(ConfigError, match="must be a whole number, got 'wide'"):
        Settings.from_env()


@pytest.mark.parametrize(
    "name",
    [
        "ROTATION_INTERVAL_SECONDS",
        "BACKUP_INTERVAL_SECONDS",
        "BACKUP_KEEP",
        "QUALITY_MINIMUM_PX",
    ],
)
@pytest.mark.parametrize("value", ["0", "-1"])
def test_a_setting_that_must_be_positive_refuses_zero_and_below(monkeypatch, tmp_path, name, value):
    """Zero is the dangerous one: a zero interval spins, a zero panel divides by
    nothing, and a zero minimum would let any scan at all be chosen unasked."""
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv(name, value)

    with pytest.raises(ConfigError, match="must be greater than zero"):
        Settings.from_env()


@pytest.mark.parametrize(
    "name", ["TV_PANEL_WIDTH_PX", "TV_PANEL_HEIGHT_PX", "TV_PANEL_DIAGONAL_INCHES", "MAT_WIDTH_INCHES", "MAT_BOTTOM_WEIGHT"]
)
def test_the_players_screen_settings_are_neither_read_nor_retired(monkeypatch, tmp_path, name):
    """The screen and the mat's width are the Player's (`feeds-and-players.md` ruling 7).

    One `.env` serves both planes on a development checkout, so the server
    must neither refuse them nor tell an operator to remove a key the Player
    still reads. A value the server would refuse, if it read it, is what shows
    that it does not.
    """
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv(name, "not a number")

    Settings.from_env()

    assert retired_settings_in({name: "not a number"}) == []


def test_the_quality_minimum_reaches_the_profile_that_judges_against_it(monkeypatch, tmp_path):
    """A configured minimum nothing carried would be a setting with no effect."""
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("QUALITY_MINIMUM_PX", "1500")

    assert Settings.from_env().quality_profile.minimum_long_edge_px == 1500


def test_the_default_quality_minimum_is_a_thousand_pixels(monkeypatch, tmp_path):
    """The owner's number, 2026-10-06: about right for a 1080p display with a mat."""
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.delenv("QUALITY_MINIMUM_PX", raising=False)

    assert Settings.from_env().quality_profile.minimum_long_edge_px == 1000


def test_a_retired_setting_still_set_is_named_with_what_replaced_it():
    """A key nothing reads looks exactly like one in force, so it is said out loud."""
    [sentence] = retired_settings_in({"RESOLUTION_FLOOR_INCHES": "11.34", "ART_ROOT": "/art"})

    assert sentence.startswith("RESOLUTION_FLOOR_INCHES is no longer read")
    assert "QUALITY_MINIMUM_PX" in sentence


def test_nothing_is_said_when_no_retired_setting_is_set():
    """The absence is asserted too: a notice that fires on every start is one a reader learns to skip."""
    assert retired_settings_in({"ART_ROOT": "/art", "QUALITY_MINIMUM_PX": "1000"}) == []
    assert retired_settings_in({"RESOLUTION_FLOOR_INCHES": ""}) == []


@pytest.mark.parametrize(
    "key",
    [
        "CONVERSATION_MODEL",
        "CONVERSATION_MAX_OUTPUT_TOKENS",
        "CONVERSATION_INPUT_COST_USD_PER_MTOK",
        "CONVERSATION_OUTPUT_COST_USD_PER_MTOK",
        "CONVERSATION_INPUT_TOKENS",
    ],
)
def test_a_retired_conversation_setting_is_named_with_asks_model(key):
    """A `.env` still choosing a conversation model would otherwise run Ask on its default, unsaid."""
    [sentence] = retired_settings_in({key: "some-value", "ART_ROOT": "/art"})

    assert sentence.startswith(f"{key} is no longer read")
    assert "ASK_MODEL" in sentence


def test_asks_model_step_limit_and_web_search_are_read_from_the_environment(monkeypatch, tmp_path):
    """Each at a value no default produces, so a dropped read shows."""
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("ASK_MODEL", "example/another-model")
    monkeypatch.setenv("ASK_STEP_LIMIT", "3")
    monkeypatch.setenv("SEARXNG_URL", "http://searxng.invalid:8080")

    settings = Settings.from_env()

    assert settings.ask_model == "example/another-model"
    assert settings.ask_step_limit == 3
    assert settings.searxng_url == "http://searxng.invalid:8080"


def test_asks_defaults_hold_when_nothing_is_set(monkeypatch, tmp_path):
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    for key in ("ASK_MODEL", "ASK_STEP_LIMIT", "SEARXNG_URL"):
        monkeypatch.delenv(key, raising=False)

    settings = Settings.from_env()

    assert settings.ask_model == DEFAULT_ASK_MODEL
    assert settings.ask_step_limit == DEFAULT_ASK_STEP_LIMIT
    assert settings.searxng_url is None


@pytest.mark.parametrize("limit", ["0", "-2"])
def test_an_ask_step_limit_below_one_is_refused(monkeypatch, tmp_path, limit):
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("ASK_STEP_LIMIT", limit)

    with pytest.raises(ConfigError, match="ASK_STEP_LIMIT"):
        Settings.from_env()


def test_the_thumbnail_cache_sits_inside_the_art_root(monkeypatch, tmp_path):
    """Every stored path is relative to ART_ROOT, so a cache outside it is unstorable."""
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    settings = Settings.from_env()

    assert settings.thumbnails_path.is_relative_to(settings.art_root)
    # Not `tv-thumbs/`, which holds images downloaded from the television keyed
    # by its own content ids — per-device state this catalogue excludes.
    assert settings.thumbnails_path.name != "tv-thumbs"


# -- discovery: what it may do, and what it is priced at ------------------------


def test_the_shipped_discovery_defaults_reproduce_the_recorded_cost_analysis(monkeypatch, tmp_path):
    """The defaults are a derivation, not a preference, and this is where it is checked.

    The figures come from a cost analysis arrived at independently of this code.
    If the shipped settings cannot reproduce them, one of the two is wrong and a
    curator is authorising against a number that describes nothing.

    **Twice now the analysis has moved under a decision, and neither time was
    this assertion relaxed to fit.** The engine choice (2026-08-02) took a search
    request from $0.005 to $0.001, and the model-only component was untouched at
    eight cents — which is what made the fall attributable to search. Then phase 2
    was built and measured (2026-08-02), and both halves of the run changed at
    once:

    - **Phase 1's token basis was re-based against a measured run** — 3,453 in and
      1,608 out, against a shipped 490,000 / 30,000. The old input figure was a
      whole-run basis being spent on phase 1 alone, and it made the number shown
      to a curator about twenty times the actual. The bounds now shipped are
      8,000 each: roughly twice the measured input, and for output the
      provider-priced reservation itself.
    - **Phase 2 costs nothing**, because it asks open museum APIs and establishes
      identity by local comparison rather than by a model call. That is what made
      the re-basing safe to do: correcting phase 1 while phase 2's consumption was
      unknown would have traded a visible overstatement for an invisible
      understatement of the run as a whole.

    Computed here rather than compared against a copied total, so the assertion
    fails when the composition changes rather than tracking it.
    """
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    discovery = Settings.from_env().discovery_settings

    # A typical run finds about twenty works. Bounded, so this is the ceiling
    # rather than the expectation.
    typical_works = 20
    run_total = discovery.phase1_estimate_usd + discovery.phase2_estimate_usd(typical_works)
    # Only phase 1 searches for money. The per-work allowance still bounds phase
    # 2's fan-out and is still reported beside a run's usage — it simply bills
    # nothing, which is why it is absent from this sum rather than multiplied by
    # a price.
    paid_searches = discovery.phase1_search_allowance
    search_spend = paid_searches * discovery.search_cost_usd
    model_spend = run_total - search_spend

    assert paid_searches == 10
    assert (
        discovery.phase1_search_allowance + typical_works * discovery.phase2_searches_per_work == 50
    ), "the fan-out cap is unchanged at 10 + 2/work; only its price went to zero"
    assert search_spend == Decimal("0.010"), "ten requests at the pinned engine's $0.001"
    assert discovery.phase2_estimate_usd(typical_works) == Decimal(0), "museum APIs are free and phase 2 makes no model call"
    assert run_total == Decimal("0.01336"), "a bounded run, an order of magnitude under the pre-measurement estimate"
    # The model call alone: 8,000 in at $0.14/M and 8,000 out at $0.28/M.
    assert model_spend == Decimal("0.00336")
    # The correction's whole point, stated as a relation rather than a number so
    # it cannot be satisfied by a stale constant: a real run measured $0.0016, and
    # a bound that far exceeds what it bounds is not informative. Ten-fold is
    # generous headroom for an allowance a run uses one of.
    assert run_total < 10 * Decimal("0.0016"), "the estimate is a usable bound rather than a twenty-fold overstatement"


def test_the_search_price_matches_the_engine_that_is_pinned(monkeypatch, tmp_path):
    """The two *shipped defaults* are one decision and must not drift apart.

    Parallel bills $0.001 and the other back-ends $0.005, so shipping an engine
    and a price that disagree would put a five-fold error into the only figure a
    curator sees before authorising a run.

    **This cannot see a deployment, and saying so is the point.** The module's
    autouse `_clean_env` stubs `load_dotenv` and clears no `DISCOVERY_*` name, so
    what runs here compares two constants in `config.py` to each other. That stub
    is correct — a config test that read the developer's own `.env` would pass or
    fail by machine — but it means the case in the sentence above, *a deployment*
    that changed one and left the other, is invisible here and was live on this
    repo's own `.env` while this test was green: `DISCOVERY_SEARCH_COST_USD=0.005`
    with no engine pinned, so estimates priced Exa while the engine was the
    `parallel` default.

    The mechanism for the deployment case is therefore **not a test**: startup
    logs the engine and the price on one line, so a mismatch is one journal read
    rather than a silent five-fold error. Adding a boot-time refusal was
    considered and not done — a household product that will not start because two
    optional settings disagree fails harder than the error it is preventing.
    """
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    settings = Settings.from_env()

    prices = {"parallel": Decimal("0.001"), "exa": Decimal("0.005"), "perplexity": Decimal("0.005")}
    expected = prices.get(settings.discovery_search_engine)

    assert expected is not None, (
        f"{settings.discovery_search_engine!r} has no recorded per-request price; add it here with the "
        "measurement behind it, or the run estimate is guessing"
    )
    assert settings.search_cost_usd == expected, (
        f"the engine is {settings.discovery_search_engine!r} at {expected}/request, but the configured "
        f"search price is {settings.search_cost_usd}"
    )


def test_the_retired_approval_threshold_is_not_read(monkeypatch, tmp_path):
    """No run stops for approval (the owner's ruling 3 of 2026-10-07, #290), so a
    deployment's leftover `DISCOVERY_APPROVAL_THRESHOLD` is not read, even when
    it would not parse."""
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("DISCOVERY_APPROVAL_THRESHOLD", "several")

    assert not hasattr(Settings.from_env().discovery_settings, "approval_threshold")


def test_a_deployment_can_override_every_discovery_setting(monkeypatch, tmp_path):
    """None of these may be a literal in source: prices move and policy is local."""
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    for name, value in {
        "DISCOVERY_PHASE1_SEARCH_ALLOWANCE": "6",
        "DISCOVERY_PHASE2_SEARCHES_PER_WORK": "3",
        "DISCOVERY_SEARCH_COST_USD": "0.001",
        "DISCOVERY_INPUT_COST_USD_PER_MTOK": "0.30",
        "DISCOVERY_OUTPUT_COST_USD_PER_MTOK": "2.50",
        "DISCOVERY_PHASE1_INPUT_TOKENS": "100000",
        "DISCOVERY_PHASE1_OUTPUT_TOKENS": "5000",
    }.items():
        monkeypatch.setenv(name, value)

    discovery = Settings.from_env().discovery_settings

    assert discovery.phase1_search_allowance == 6
    assert discovery.phase2_searches_per_work == 3
    assert discovery.search_cost_usd == Decimal("0.001")
    # 100,000 in at $0.30/M is $0.03; 5,000 out at $2.50/M is $0.0125; six
    # searches at $0.001 add $0.006.
    assert discovery.phase1_estimate_usd == Decimal("0.0485")
    # Zero whatever the per-work allowance is set to, because phase 2 asks museum
    # APIs and identifies works locally — it makes no paid call for the allowance
    # to price. The allowance is still read and still bounds fan-out, which is
    # what the assertion three lines up checks; what it no longer does is cost
    # anything.
    assert discovery.phase2_estimate_usd(10) == Decimal(0)


def test_a_price_is_read_as_a_decimal_rather_than_through_a_float(monkeypatch, tmp_path):
    """A tenth of a cent that cannot be represented exactly is a rounding error
    in every figure derived from it, including a running total nobody will
    reconcile against the provider's own."""
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("DISCOVERY_SEARCH_COST_USD", "0.005")
    monkeypatch.setenv("DISCOVERY_PHASE1_SEARCH_ALLOWANCE", "3")

    priced = Settings.from_env().discovery_settings.search_cost_usd * 3

    assert priced == Decimal("0.015")
    assert str(priced) == "0.015", "a price that went through float would not render exactly"


@pytest.mark.parametrize(
    "name",
    ["DISCOVERY_PHASE1_SEARCH_ALLOWANCE", "DISCOVERY_PHASE1_INPUT_TOKENS"],
)
def test_a_count_that_is_not_a_number_is_refused_with_the_offending_value(monkeypatch, tmp_path, name):
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv(name, "several")

    with pytest.raises(ConfigError, match="must be a whole number, got 'several'"):
        Settings.from_env()


@pytest.mark.parametrize(
    "name",
    ["DISCOVERY_PHASE1_SEARCH_ALLOWANCE", "DISCOVERY_PHASE2_SEARCHES_PER_WORK"],
)
def test_a_count_of_zero_is_allowed_rather_than_refused(monkeypatch, tmp_path, name):
    """Zero forbids searching, a coherent setting for a cautious deployment, and
    refusing it would be config inventing a policy nobody wrote — which is the
    distinction from a zero rotation interval."""
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv(name, "0")

    assert Settings.from_env()


@pytest.mark.parametrize(
    "name",
    ["DISCOVERY_PHASE1_SEARCH_ALLOWANCE", "DISCOVERY_PHASE2_SEARCHES_PER_WORK"],
)
def test_a_negative_count_is_refused(monkeypatch, tmp_path, name):
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv(name, "-1")

    with pytest.raises(ConfigError, match="cannot be negative"):
        Settings.from_env()


def test_a_price_that_is_not_a_number_is_refused_with_the_offending_value(monkeypatch, tmp_path):
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("DISCOVERY_SEARCH_COST_USD", "five cents")

    with pytest.raises(ConfigError, match="must be a decimal number of US dollars, got 'five cents'"):
        Settings.from_env()


def test_a_negative_price_is_refused(monkeypatch, tmp_path):
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("DISCOVERY_INPUT_COST_USD_PER_MTOK", "-0.14")

    with pytest.raises(ConfigError, match="is a price and cannot be negative"):
        Settings.from_env()


def test_a_deployment_can_override_every_engine_setting(monkeypatch, tmp_path):
    """The engine's own values are deployment values too, and none may be a
    literal in source: the model and its price move independently of this code,
    and the output reservation is what a provider refuses a request against."""
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("DISCOVERY_MODEL", "probe/model-under-test")
    monkeypatch.setenv("DISCOVERY_MAX_OUTPUT_TOKENS", "1234")
    monkeypatch.setenv("DISCOVERY_SEARCH_RESULTS", "6")
    monkeypatch.setenv("DISCOVERY_SEARCH_ENGINE", "exa")

    settings = Settings.from_env()

    assert settings.discovery_model == "probe/model-under-test"
    assert settings.discovery_max_output_tokens == 1234
    assert settings.discovery_search_results == 6
    assert settings.discovery_search_engine == "exa"


def test_a_search_engine_is_always_resolved_to_a_name(monkeypatch, tmp_path):
    """Blank and absent both mean the chosen engine, and neither may mean "none".

    Leaving the engine unset does not select a neutral default — it hands the
    choice to whichever model is configured, because the provider resolves an
    absent engine to that model provider's own native search where it has one and
    to Exa where it does not. A deployment changing `DISCOVERY_MODEL` would then
    silently change how the product searches, which is the thing pinning exists
    to stop.
    """
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.delenv("DISCOVERY_SEARCH_ENGINE", raising=False)

    assert Settings.from_env().discovery_search_engine == "parallel"

    monkeypatch.setenv("DISCOVERY_SEARCH_ENGINE", "")

    assert Settings.from_env().discovery_search_engine == "parallel", "blank is unset, not a request for no engine"


def test_the_chosen_engine_is_the_one_the_comparison_selected(monkeypatch, tmp_path):
    """Parallel, on measured cost at indistinguishable quality.

    Across sixteen "resolve a named work to its holding museum" cases and a
    recency-bound intent, Exa, Parallel and Perplexity each found the institution
    every time. Parallel bills a fifth of what the other two do per request, which
    made the measured comparison run four times cheaper for the same results.
    """
    monkeypatch.setenv("ART_ROOT", str(tmp_path))

    assert Settings.from_env().discovery_search_engine == "parallel"


def test_the_engine_settings_ship_at_the_values_the_analysis_chose(monkeypatch, tmp_path):
    """A floating model alias, and a search breadth of ten because breadth is free.

    The fee is charged per search request and was measured identical at one,
    three, five and ten results, so a lower default would save nothing and see
    less. The alias is floating rather than a dated snapshot so a snapshot
    retirement cannot break the product's only paid path.
    """
    monkeypatch.setenv("ART_ROOT", str(tmp_path))

    settings = Settings.from_env()

    assert settings.discovery_model == "deepseek/deepseek-v4-flash"
    assert ":" not in settings.discovery_model, "a dated snapshot pin, not the floating alias"
    assert settings.discovery_search_results == 10


def test_the_output_reservation_must_be_positive(monkeypatch, tmp_path):
    """There is no coherent request that reserves no output, and the provider
    refuses one rather than running it cheaply."""
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("DISCOVERY_MAX_OUTPUT_TOKENS", "0")

    with pytest.raises(ConfigError, match="DISCOVERY_MAX_OUTPUT_TOKENS"):
        Settings.from_env()


def test_the_api_key_is_absent_rather_than_empty_when_unset(monkeypatch, tmp_path):
    """`None` is what the entry point tests to decide whether discovery can run,
    and an empty string would be truthy-adjacent enough to invite a bug."""
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("OPENROUTER_API_KEY", "")

    assert Settings.from_env().openrouter_api_key is None


def test_the_api_key_never_appears_in_the_redacted_configuration(monkeypatch, tmp_path):
    """Driven off the declaration rather than a remembered list, so declaring a
    new secret is what gets it redacted — and checked."""
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-should-never-be-logged")

    redacted = Settings.from_env().redacted()

    assert "sk-or-v1-should-never-be-logged" not in str(redacted)
    assert redacted["openrouter_api_key"] == "<set>"
    assert set(redacted) == set(Settings.__dataclass_fields__), "every field is accounted for, secret or not"


def test_no_backup_directory_means_no_backups(monkeypatch, tmp_path):
    """Unset is a deployment that takes none; the health panel then says none was recorded."""
    monkeypatch.setenv("ART_ROOT", str(tmp_path))

    settings = Settings.from_env()

    assert settings.backup_dir is None
    assert (settings.backup_interval_seconds, settings.backup_keep) == (24 * 60 * 60, 14)


def test_the_backup_settings_are_read_by_their_names(monkeypatch, tmp_path):
    """A misspelt name would switch backups off without a word, so each is read back."""
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setenv("BACKUP_INTERVAL_SECONDS", "3600")
    monkeypatch.setenv("BACKUP_KEEP", "3")

    settings = Settings.from_env()

    assert settings.backup_dir == tmp_path / "backups"
    assert (settings.backup_interval_seconds, settings.backup_keep) == (3600, 3)


def test_source_order_names_plugins_most_preferred_first(monkeypatch, tmp_path):
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("SOURCE_ORDER", " artic, commons ,, gallery ")

    assert Settings.from_env().source_order == ("artic", "commons", "gallery")


@pytest.mark.parametrize("raw", [None, "", " , "])
def test_source_order_defaults_to_commons_then_the_art_institute(monkeypatch, tmp_path, raw):
    """The owner's ruling of 2026-10-01, when the deployment names no order."""
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    if raw is None:
        monkeypatch.delenv("SOURCE_ORDER", raising=False)
    else:
        monkeypatch.setenv("SOURCE_ORDER", raw)

    assert Settings.from_env().source_order == ("commons", "artic")


def test_a_monthly_budget_is_read_as_exact_money_and_unset_is_none(monkeypatch, tmp_path):
    """None, not zero, when unset: a budget of zero would read as a month already spent."""
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    assert Settings.from_env().monthly_budget_usd is None

    monkeypatch.setenv("MONTHLY_BUDGET_USD", "12.40")
    assert Settings.from_env().monthly_budget_usd == Decimal("12.40")


def test_a_monthly_budget_that_is_not_money_is_refused_by_name(monkeypatch, tmp_path):
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("MONTHLY_BUDGET_USD", "ten dollars")

    with pytest.raises(ConfigError, match="MONTHLY_BUDGET_USD"):
        Settings.from_env()


def test_labels_are_imperial_unless_told_otherwise(monkeypatch, tmp_path):
    monkeypatch.setenv("ART_ROOT", str(tmp_path))

    assert Settings.from_env().label_units is Units.IMPERIAL


@pytest.mark.parametrize("spelling", ["metric", "METRIC", " Metric "])
def test_labels_are_metric_however_metric_is_spelled(monkeypatch, tmp_path, spelling):
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("LABEL_UNITS", spelling)

    assert Settings.from_env().label_units is Units.METRIC


def test_a_system_of_units_that_is_neither_is_refused_rather_than_guessed(monkeypatch, tmp_path):
    """A typo falling back to imperial would leave a metric household's labels
    unchanged with nothing said."""
    monkeypatch.setenv("ART_ROOT", str(tmp_path))
    monkeypatch.setenv("LABEL_UNITS", "metirc")

    with pytest.raises(ConfigError, match="LABEL_UNITS must be imperial or metric, got 'metirc'"):
        Settings.from_env()
