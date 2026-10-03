"""The log shape, and the run id that rides every line emitted inside a run.

Correlation is the whole reason this exists: one curator action fans out across
minutes and many external calls, and reconstructing which lines belonged to it is
impossible if the key is only on the lines somebody remembered to put it on. So
what is tested is not that a formatter can render a field, but that a module
which knows nothing about runs still emits the id when it logs inside one.
"""

import json
import logging

import pytest

from arrt import logs


@pytest.fixture
def emitted():
    """Lines this test produced, rendered by the shipped formatter as they are logged.

    Wired the way `configure` wires it — formatter and correlation filter on a
    handler — rather than rendered afterwards from captured records. The
    difference is the whole point: the run id is read from the context *at the
    moment of emission*, so a test that stamped records later would be asking
    which run was current when the assertion ran, and would report every line as
    uncorrelated.
    """
    lines: list[dict] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            lines.append(json.loads(self.format(record)))

    handler = Capture()
    handler.setFormatter(logs.JsonFormatter())
    handler.addFilter(logs.RunCorrelationFilter())

    root = logging.getLogger()
    restore = root.level
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    try:
        yield lines
    finally:
        root.removeHandler(handler)
        root.setLevel(restore)


def test_a_line_is_one_json_object_carrying_when_how_bad_where_and_what(emitted):
    logging.getLogger("arrt.example").info("the wall changed")

    line = emitted[0]
    assert line["level"] == "INFO"
    assert line["logger"] == "arrt.example"
    assert line["message"] == "the wall changed"
    assert line["time"].startswith("20")
    assert line["time"].endswith("+00:00"), "timestamps are UTC, so two planes' journals can be read together"


def test_a_line_logged_inside_a_run_carries_that_runs_id(emitted):
    """The correlation key, on a logger that knows nothing about runs."""
    with logs.run_context("run-42"):
        logging.getLogger("arrt.somewhere.deep").warning("a source came back empty")

    assert emitted[0]["run_id"] == "run-42"


def test_a_line_logged_outside_a_run_carries_no_run_id(emitted):
    """Absent rather than null: a key that is always there teaches a reader to
    ignore it, and `null` would read as a run whose id nobody recorded."""
    logging.getLogger("arrt.startup").info("catalogue opened")

    assert "run_id" not in emitted[0]


def test_the_binding_is_undone_on_the_way_out_even_when_the_body_raises(emitted):
    """A run that failed must not leave its id stamped on everything after it."""
    with pytest.raises(ZeroDivisionError), logs.run_context("run-7"):
        raise ZeroDivisionError
    logging.getLogger("arrt.after").info("unrelated work")

    assert logs.current_run_id() is None
    assert "run_id" not in emitted[0]


def test_a_nested_binding_restores_the_outer_one_rather_than_clearing_it(emitted):
    """A re-search inside the run that spawned it must not drop correlation for
    the rest of the outer run."""
    with logs.run_context("outer"):
        with logs.run_context("inner"):
            logging.getLogger("arrt.inner").info("re-searching")
        logging.getLogger("arrt.outer").info("carrying on")

    assert [line["run_id"] for line in emitted] == ["inner", "outer"]


def test_fields_a_call_site_attaches_are_carried_through(emitted):
    """Structure is a keyword argument, not an edit to the formatter."""
    logging.getLogger("arrt.example").info("phase 1 finished", extra={"works_proposed": 20, "event": "run.ready"})

    line = emitted[0]
    assert line["works_proposed"] == 20
    assert line["event"] == "run.ready"


def test_a_value_that_will_not_serialise_is_rendered_rather_than_losing_the_line(emitted):
    """A line that vanished because one field had an odd type is the worst
    outcome available to a logger."""

    class Opaque:
        def __str__(self) -> str:
            return "an opaque thing"

    logging.getLogger("arrt.example").info("something happened", extra={"subject": Opaque()})

    assert emitted[0]["subject"] == "an opaque thing"


def _unreachable_source() -> None:
    raise ValueError("the source was unreachable")


def test_a_traceback_is_one_field_rather_than_trailing_lines(emitted):
    """Multi-line output would break the one-line-one-object rule the shape rests on."""
    try:
        _unreachable_source()
    except ValueError:
        logging.getLogger("arrt.example").exception("phase 1 raised")

    line = emitted[0]
    assert "ValueError: the source was unreachable" in line["exception"]
    assert "\n" not in line["message"]


def test_configuring_twice_does_not_double_every_line():
    """The entry point calls this once; a second call must replace, not stack."""
    root = logging.getLogger()
    before = list(root.handlers)
    # The level as well as the handlers. `configure` sets the root level, and
    # these two tests are the only place in the suite that calls it — so leaving
    # it at INFO leaks the gate every other test's `caplog` depends on, into
    # every test that runs after this one in the same worker. It cost one
    # intermittent failure in `test_artwork_lifecycle.py`, which asserts that
    # opening a catalogue says nothing and was reading an INFO line from a
    # migration two calls earlier.
    before_level = root.level
    try:
        logs.configure()
        logs.configure()
        installed = [handler for handler in root.handlers if getattr(handler, logs._INSTALLED, False)]
        assert len(installed) == 1
    finally:
        root.handlers = before
        root.setLevel(before_level)


def test_configuring_leaves_handlers_it_did_not_install_alone():
    """Evicting every root handler silently disables anything else attached —
    a test harness's capture first, which fails as "nothing was logged" rather
    than as "your logging setup removed my handler"."""
    root = logging.getLogger()
    before = list(root.handlers)
    before_level = root.level  # See the test above: `configure` sets this too.
    someone_elses = logging.NullHandler()
    try:
        root.addHandler(someone_elses)
        logs.configure()
        assert someone_elses in root.handlers
    finally:
        root.handlers = before
        root.setLevel(before_level)


SECRET = "sk-live-123"
KEYED = f"https://api.example.net/v1/search?key={SECRET}&q=x"


def _refuse(url: str) -> None:
    raise RuntimeError(f"401 for url {url}")


def test_a_query_string_is_cut_from_the_message_the_fields_and_the_traceback(emitted):
    """Wherever a key could ride: the message, an argument, an attached field, or the
    message a traceback repeats. The address itself stays, so the line still says where."""
    log = logging.getLogger("arrt.tests.scrub")
    try:
        _refuse(KEYED)
    except RuntimeError:
        log.warning("fetch of %s failed", KEYED, exc_info=True, extra={"fetch_url": KEYED})

    (line,) = emitted
    assert SECRET not in json.dumps(line)
    assert line["message"] == "fetch of https://api.example.net/v1/search?… failed"
    assert line["fetch_url"] == "https://api.example.net/v1/search?…"
    assert "401 for url https://api.example.net/v1/search?…" in line["exception"]


def test_a_url_with_no_query_string_is_left_alone(emitted):
    logging.getLogger("arrt.tests.scrub").info("fetched https://www.artic.edu/iiif/2/abc/info.json")

    assert emitted[0]["message"] == "fetched https://www.artic.edu/iiif/2/abc/info.json"


def test_a_direct_fetch_that_raises_with_a_keyed_url_journals_no_key(emitted, tmp_path):
    """Through the fetcher's own warning, the line that logs the URL it was asked and a traceback."""
    from contextlib import contextmanager

    from arrt.library.acquisition.direct import direct_fetch

    @contextmanager
    def raising(url: str):
        raise ValueError(f"transport refused {url}")
        yield  # pragma: no cover - keeps this a generator

    result = direct_fetch(KEYED, destination=tmp_path / "x.jpg", open_stream=raising, max_bytes=1000)

    assert result.path is None
    warned = [line for line in emitted if "direct fetch of" in line["message"]]
    assert warned and SECRET not in json.dumps(warned)


ACCENTED = f"https://api.example.net/v1/search?q=Dürer&key={SECRET}"


class _Rendered:
    """An object JSON cannot hold, whose `str` carries a keyed URL: an `httpx.URL` is one."""

    def __str__(self) -> str:
        return ACCENTED


def test_a_key_after_an_accented_letter_is_cut_too(emitted):
    """JSON escapes the ü; a scrub after encoding stopped there and kept the rest of the query."""
    log = logging.getLogger("arrt.tests.scrub")
    try:
        _refuse(ACCENTED)
    except RuntimeError:
        log.warning(
            "fetch of %s failed",
            ACCENTED,
            exc_info=True,
            extra={"fetch_url": ACCENTED, "nested": {"urls": [ACCENTED]}, "rendered": _Rendered()},
        )

    (line,) = emitted
    assert SECRET not in json.dumps(line)
    assert line["message"] == "fetch of https://api.example.net/v1/search?… failed"
    assert line["nested"] == {"urls": ["https://api.example.net/v1/search?…"]}
    assert line["rendered"] == "https://api.example.net/v1/search?…"


def test_a_key_after_an_apostrophe_or_backslash_is_cut_too(emitted):
    """httpx leaves both in a query as they are, in the shape its own error message takes."""
    import httpx

    url = str(httpx.URL(f"https://api.example.net/search?q=O'Keeffe&p=a\\b&key={SECRET}"))
    log = logging.getLogger("arrt.tests.scrub")
    try:
        _refuse(f"'{url}'")
    except RuntimeError:
        log.warning("Client error for url '%s'", url, exc_info=True, extra={"fetch_url": url, "by_url": {url: 1}})

    (line,) = emitted
    assert SECRET not in json.dumps(line)
    assert line["message"].startswith("Client error for url 'https://api.example.net/search?…")


def _httpx_leaves_unencoded() -> tuple[str, str]:
    """The characters httpx leaves as they are in a path and in a query, from httpx itself.

    Read rather than copied, so a release that leaves one more character
    unencoded fails here, not in a journal.
    """
    from httpx import _urlparse

    return _urlparse.PATH_SAFE, _urlparse.QUERY_SAFE


@pytest.mark.parametrize("part", ["path", "query"])
def test_no_character_httpx_leaves_unencoded_shields_a_key(part):
    import httpx

    path_safe, query_safe = _httpx_leaves_unencoded()
    leaked = []
    for character in path_safe if part == "path" else query_safe:
        if part == "path":
            url = httpx.URL(f"https://api.example.net/v1/a{character}b/works?key={SECRET}")
        else:
            url = httpx.URL(f"https://api.example.net/v1/works?q=a{character}b&key={SECRET}")
        if SECRET in logs.scrub(f"Client error for url '{url}'"):
            leaked.append(character)

    assert leaked == []
