"""Deployment values: what stops the process, and what quietly defaults.

The distinction is the whole point of this module. A value nobody typed gets a
default when there is a right answer and a refusal when there is not; a value
somebody typed *and got wrong* always refuses, because substituting a default
there hides the typo behind behaviour that looks deliberate.

**A Player is a client** (`clients.md`): it is told its server, its token and its
cache, and learns its walls from the server. The Frame is an output it may or
may not have, so the Frame's own required values are required only on a client
configured with one.
"""

from pathlib import Path

import pytest

from arrt_player.config import RETIRED_SETTINGS, ConfigError, WallIdUnusable, load

FRAME = {
    "TV_ADDRESS": "10.0.0.1",
    "LATITUDE": "45.68",
    "LONGITUDE": "-111.04",
    "LOCATION_NAME": "Bozeman",
}


def an_environment(cache_dir: Path, *, frame: bool = True, **overrides: str) -> dict[str, str]:
    environment = {
        "SERVER_URL": "http://127.0.0.1:8770/",
        "CLIENT_TOKEN": "the-clients-token",
        "CACHE_DIR": str(cache_dir),
        **(FRAME if frame else {}),
    }
    environment.update(overrides)
    return environment


class TestWhatMustBeSet:
    @pytest.mark.parametrize("missing", ["SERVER_URL", "CLIENT_TOKEN", "CACHE_DIR"])
    def test_a_client_without_its_server_its_token_or_its_cache_does_not_start(self, cache_dir: Path, missing: str):
        environment = an_environment(cache_dir, frame=False)
        del environment[missing]

        with pytest.raises(ConfigError, match=missing):
            load(environment)

    @pytest.mark.parametrize("retired", sorted(RETIRED_SETTINGS))
    def test_a_setting_a_one_wall_player_read_is_refused_by_name(self, cache_dir: Path, retired: str):
        """A stale `.env` fails loudly rather than being half-read.

        Each of these was read once at start and never again, so a Player that
        ignored one would start, pull nothing for the wall its operator believes
        it serves, and say nothing about why.
        """
        with pytest.raises(ConfigError, match=f"{retired} is retired") as refused:
            load(an_environment(cache_dir, **{retired: "anything"}))

        assert RETIRED_SETTINGS[retired] in str(refused.value)

    @pytest.mark.parametrize(
        ("retired", "replaced_by"),
        [("WALL_ID", "Settings › Clients"), ("WALL_TOKEN", "CLIENT_TOKEN"), ("MANIFEST_SOURCE", "SERVER_URL")],
    )
    def test_the_refusal_says_what_replaced_it(self, cache_dir: Path, retired: str, replaced_by: str):
        with pytest.raises(ConfigError, match=replaced_by):
            load(an_environment(cache_dir, **{retired: "anything"}))

    def test_a_retired_setting_left_empty_is_not_set(self, cache_dir: Path):
        """`WALL_ID=` is a key nobody filled in, which is the same as no key."""
        assert load(an_environment(cache_dir, WALL_ID="", WALL_TOKEN="", MANIFEST_SOURCE="")).server_url

    @pytest.mark.parametrize("missing", ["LATITUDE", "LONGITUDE", "LOCATION_NAME"])
    def test_a_frame_without_the_sun_it_follows_does_not_start(self, cache_dir: Path, missing: str):
        environment = an_environment(cache_dir)
        del environment[missing]

        with pytest.raises(ConfigError, match=missing):
            load(environment)

    def test_a_number_that_is_not_one_is_refused_rather_than_defaulted(self, cache_dir: Path):
        with pytest.raises(ConfigError, match="TV_PORT"):
            load(an_environment(cache_dir, TV_PORT="eight-thousand"))

    def test_a_label_panel_with_no_frame_is_a_client_with_a_label_output(self, cache_dir: Path):
        """**Reversed on purpose** (`labels-and-surfaces.md` ruling 3): a label output
        may live on a client with no display at all, and the server maps it to a
        wall on any client. So `EPD_DEVICE` without `TV_ADDRESS` starts, with no
        Frame and a panel."""
        settings = load(an_environment(cache_dir, frame=False, EPD_DEVICE="waveshare_epd.it8951"))

        assert settings.frame is None
        assert settings.panel.epd_device == "waveshare_epd.it8951"


class TestTheFrameIsAnOutputAClientMayHave:
    def test_tv_address_present_is_a_frame(self, cache_dir: Path):
        settings = load(an_environment(cache_dir))

        assert settings.frame is not None
        assert settings.frame.tv_address == "10.0.0.1"

    def test_tv_address_absent_is_no_frame_and_needs_none_of_its_values(self, cache_dir: Path):
        settings = load(an_environment(cache_dir, frame=False))

        assert settings.frame is None
        with pytest.raises(ValueError, match="no Frame"):
            settings.frame_wall("living-room")


class TestWhatDefaults:
    def test_a_client_with_a_frame_needs_seven_values(self, cache_dir: Path):
        settings = load(an_environment(cache_dir))

        assert settings.server_url == "http://127.0.0.1:8770", "a trailing slash doubled every route's first one"
        assert settings.client_token == "the-clients-token"
        assert settings.cache_dir == cache_dir
        assert settings.poll_interval_seconds == 1.0
        assert settings.client_poll_seconds == 30.0
        assert settings.frame.tv_port == 8002
        assert settings.panel.epd_panel_width_px == 1448
        assert settings.panel.epd_panel_height_px == 1072
        assert settings.frame.tv_client_name == "tvpi"
        assert settings.frame.tv_token_file == cache_dir / "token_file"

    def test_the_panel_is_configurable_because_nothing_may_hardcode_one(self, cache_dir: Path):
        """This deployment is a 1448×1072 IT8951; the product must run on any."""
        settings = load(an_environment(cache_dir, EPD_PANEL_WIDTH_PX="800", EPD_PANEL_HEIGHT_PX="600"))

        assert (settings.panel.epd_panel_width_px, settings.panel.epd_panel_height_px) == (800, 600)

    def test_the_three_values_that_decide_whether_this_device_has_a_panel(self, cache_dir: Path):
        """**The names a misspelling makes invisible.**

        These three are the whole of what `.env` says about the label surface, and
        every other test in this plane builds its settings directly — so a misspelt
        key or a wrong default here would leave `epd_device` empty on a Pi that has
        a panel, `label_surface` would return None, and the heartbeat would report
        a device with no panel. That is the exact distinction this plane was built
        to draw, collapsed by a typo nothing else would catch.
        """
        panel = load(
            an_environment(cache_dir, EPD_DEVICE="waveshare_epd.it8951", EPD_MARGIN_PX="64", EPD_ROTATE_DEGREES="0")
        ).panel

        assert panel.epd_device == "waveshare_epd.it8951"
        assert panel.epd_margin_px == 64
        assert panel.epd_rotate_degrees == 0

    def test_a_deployment_that_says_nothing_about_a_panel_has_none(self, cache_dir: Path):
        """The supported deployment rather than the degraded one.

        The rotation still takes the reference deployment's default, because it
        describes how a panel is used rather than whether there is one. The margin
        does not: it derives from the type, so this value is an override nobody
        has exercised rather than a default everybody inherits.
        """
        panel = load(an_environment(cache_dir)).panel

        assert panel.epd_device == ""
        assert panel.epd_margin_px is None
        assert panel.epd_rotate_degrees == 180

    def test_the_viewing_conditions_have_no_defaults_and_must_not_acquire_any(self, cache_dir: Path):
        """**The one pair in this module that may never be guessed.**

        A wrong *viewing distance* is not visible at all — it produces type nobody
        can read from where they stand, while the daemon starts, the panel draws
        and every test passes. That is not hypothetical; it is what shipped. A
        default here would restore it.
        """
        stated = load(an_environment(cache_dir, EPD_PANEL_DIAGONAL_INCHES="6", EPD_VIEWING_DISTANCE_INCHES="84")).panel
        assert (stated.epd_panel_diagonal_inches, stated.epd_viewing_distance_inches) == (6.0, 84.0)

        unstated = load(an_environment(cache_dir)).panel
        assert unstated.epd_panel_diagonal_inches is None
        assert unstated.epd_viewing_distance_inches is None

    def test_a_viewing_measurement_that_is_not_a_number_is_refused_rather_than_dropped(self, cache_dir: Path):
        with pytest.raises(ConfigError, match="EPD_VIEWING_DISTANCE_INCHES"):
            load(an_environment(cache_dir, EPD_VIEWING_DISTANCE_INCHES="seven feet"))

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("false", False), ("FALSE", False), ("0", False), ("no", False), ("off", False), ("true", True), ("yes", True)],
    )
    def test_the_shuffle_fallback_reads_the_spellings_people_write(self, cache_dir: Path, raw: str, expected: bool):
        assert load(an_environment(cache_dir, ROTATION_SHUFFLE=raw)).rotation_shuffle_fallback is expected


class TestEachWallHasItsOwnDirectory:
    """**The paths are derived, never configured**, and that is the whole mechanism
    keeping two walls on one client apart: a wall's worker opens exactly the files
    its id names, so another room's are files it never opens."""

    def test_a_walls_files_are_under_its_own_directory_in_the_cache(self, cache_dir: Path):
        wall = load(an_environment(cache_dir)).wall("study")

        assert wall.wall_dir == cache_dir / "study"
        assert wall.manifest_path == cache_dir / "study" / "manifest.json"
        assert wall.render_root == wall.heartbeat_root == cache_dir / "study"
        assert wall.state_path == cache_dir / "study" / "display-state.sqlite"

    def test_two_walls_on_one_client_share_no_file(self, cache_dir: Path):
        settings = load(an_environment(cache_dir))
        study, hall = settings.wall("study"), settings.wall("hall")

        assert {study.manifest_path, study.state_path, study.wall_dir}.isdisjoint(
            {hall.manifest_path, hall.state_path, hall.wall_dir}
        )

    def test_a_wall_on_the_frame_carries_the_frame_and_the_wall(self, cache_dir: Path):
        settings = load(an_environment(cache_dir, TV_PORT="8003"))
        on_the_frame = settings.frame_wall("study")

        assert on_the_frame.wall_dir == cache_dir / "study"
        assert on_the_frame.tv_port == 8003
        assert on_the_frame.client_token == "the-clients-token"

    @pytest.mark.parametrize("unusable", ["..", ".", "a/b", "../elsewhere", ".client", "", "wall id", "x\x00y"])
    def test_a_wall_id_that_is_not_a_plain_directory_name_is_refused(self, cache_dir: Path, unusable: str):
        """The server mints UUIDs; an id that would put a wall's files outside its own directory is refused by name."""
        with pytest.raises(WallIdUnusable):
            load(an_environment(cache_dir)).wall(unusable)

    @pytest.mark.parametrize("usable", ["3f2a9c1e-8b7d-4e6f-a1b2-c3d4e5f60718", "living-room", "w_1", "wall.v2"])
    def test_ids_the_server_mints_are_accepted(self, cache_dir: Path, usable: str):
        assert load(an_environment(cache_dir)).wall(usable).wall_dir == cache_dir / usable


class TestTheStartupLine:
    def test_the_clients_line_names_its_server_and_cache_and_says_whether_it_has_a_frame(self, cache_dir: Path):
        with_frame = load(an_environment(cache_dir)).startup_lines()
        without = load(an_environment(cache_dir, frame=False)).startup_lines()

        assert with_frame["server_url"] == "http://127.0.0.1:8770"
        assert with_frame["cache_dir"] == str(cache_dir)
        assert with_frame["frame"]["tv_address"] == "10.0.0.1:8002"
        assert "TV_ADDRESS is not set" in str(without["frame"])

    def test_a_walls_line_names_the_wall_and_both_files_that_follow_from_it(self, cache_dir: Path):
        """**The value whose being wrong has no other symptom.** The heartbeat's
        path is where an operator looks when the health panel says a wall is
        silent, and the manifest's is the file being waited on."""
        lines = load(an_environment(cache_dir)).frame_wall("study").startup_lines()

        assert lines["wall_id"] == "study"
        assert lines["manifest_path"] == str(cache_dir / "study" / "manifest.json")
        assert lines["heartbeat_path"] == str(cache_dir / "study" / "display-heartbeat-study.json")

    def test_the_clients_line_names_its_panel_with_or_without_a_frame(self, cache_dir: Path):
        """The panel is the client's now, so its geometry is on the client's line, Frame or no Frame."""
        for frame in (True, False):
            lines = load(an_environment(cache_dir, frame=frame, EPD_DEVICE="waveshare_epd.it8951")).startup_lines()
            assert lines["panel"]["epd_panel_px"] == "1448x1072"
            assert lines["panel"]["epd_device"] == "waveshare_epd.it8951"

    def test_it_names_the_viewing_conditions_the_type_was_sized_from(self, cache_dir: Path):
        lines = load(an_environment(cache_dir, EPD_PANEL_DIAGONAL_INCHES="6", EPD_VIEWING_DISTANCE_INCHES="84")).startup_lines()

        assert "6.0" in str(lines["panel"]["epd_viewing"])
        assert "84.0" in str(lines["panel"]["epd_viewing"])

    def test_unstated_viewing_conditions_are_reported_as_what_they_cost(self, cache_dir: Path):
        line = str(load(an_environment(cache_dir)).startup_lines()["panel"]["epd_viewing"])

        assert "not stated" in line
        assert "draws none" in line, f"the line does not say what the absence costs: {line}"

    def test_it_holds_no_fact_about_the_television_s_physical_size(self, cache_dir: Path):
        """Curation composes the mat into the render, so this plane never needs the TV's size."""
        settings = load(an_environment(cache_dir, TV_PANEL_DIAGONAL_INCHES="50", TV_PANEL_WIDTH_PX="3840"))

        assert not hasattr(settings.frame, "tv_panel_diagonal_inches")
        assert "3840" not in repr(settings.startup_lines())

    def test_the_pairing_token_is_reported_as_a_path_and_never_as_its_contents(self, cache_dir: Path, tmp_path: Path):
        token = tmp_path / "token_file"
        token.write_text("a-real-pairing-token")

        lines = load(an_environment(cache_dir, TV_TOKEN_FILE=str(token))).startup_lines()

        assert lines["frame"]["tv_token_file"] == str(token)
        assert "a-real-pairing-token" not in repr(lines)

    def test_the_client_token_is_in_no_repr_and_no_startup_line(self, cache_dir: Path):
        settings = load(an_environment(cache_dir))
        wall = settings.wall("study")
        on_the_frame = settings.frame_wall("study")

        for said in (repr(settings), repr(wall), repr(on_the_frame), repr(settings.startup_lines())):
            assert "the-clients-token" not in said
        assert "the-clients-token" not in repr(on_the_frame.startup_lines())
        assert "the-clients-token" not in repr(wall.wall_lines())
