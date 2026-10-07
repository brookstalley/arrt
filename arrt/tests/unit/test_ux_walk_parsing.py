"""`tools/ux_walk.py` reads the route table from the file; these hold that reading.

The walk's first finding is the difference between the screens the client
declares and the ones a curator can reach, so a parser that dropped a route
would report a missing screen that exists, and one that invented a route from a
comment would report an orphan that does not.
"""

import signal
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import ux_walk  # tools/ is not a package; the path is inserted above

#: The shapes the real table uses, plus the member that would make a careless
#: parser wrong: a comment naming a key with a colon after it, and an object
#: nested inside an entry.
TABLE = """
const SECTIONS = [{ key: "artworks", label: "Artworks" }];
const ROUTES = {
  collection: { render: viewCollection, section: "artworks", page: "Artworks" },
  // Contextual rather than a page: returns to Ask. A note once read as a field.
  theme: { render: viewTheme, detail: OPTIONAL_ID, section: "artworks", page: "Themes" },
  /* review: { render: nothing } — commented out, so not a route */
  run: { render: viewRun, detail: true, opensFrom: "queue", nested: { inner: { deeper: 1 } } },
};
install(ROUTES, {});
"""


def test_it_reads_every_top_level_route_and_nothing_else():
    routes = ux_walk.declared_routes(TABLE)

    assert list(routes) == ["collection", "theme", "run"]
    assert routes["collection"] == ux_walk.Route("collection", "absent", "artworks", "Artworks")
    assert routes["theme"].detail == "optional"
    assert routes["run"].detail == "required"
    assert routes["run"].section is None


def test_it_reads_the_shipped_table_in_its_order():
    """The first route is the home page (`app.js`), which the crawl relies on when the shell lands on no hash."""
    routes = ux_walk.declared_routes(ux_walk.APP_JS.read_text(encoding="utf-8"))

    assert next(iter(routes)) == "collection"
    assert {"work", "run", "review", "conversation", "topic"} <= {k for k, r in routes.items() if r.detail == "required"}
    assert routes["theme"].detail == "optional"


def test_a_table_it_cannot_find_fails_by_name():
    with pytest.raises(ValueError, match="const ROUTES"):
        ux_walk.declared_routes("const NOT_ROUTES = { a: { } };")


@pytest.mark.parametrize(
    ("fragment", "expected"),
    [
        ("#works", ux_walk.Address("collection")),
        ("#work/12?from=collection", ux_walk.Address("work", "12")),
        ("#search?q=monet&from=queue", ux_walk.Address("search", "", (("q", "monet"),))),
        ("#theme", ux_walk.Address("theme")),
    ],
)
def test_addresses_resolve_aliases_and_drop_only_the_opener(fragment, expected):
    aliases = ux_walk.fragment_aliases(ux_walk.ROUTE_JS.read_text(encoding="utf-8"))

    assert ux_walk.parse_fragment(fragment, aliases) == expected


@pytest.mark.parametrize("fragment", ["#", "", "https://example.org/#x", "#/nothing", "#?q=1"])
def test_what_is_not_a_route_is_refused(fragment):
    assert ux_walk.parse_fragment(fragment, {}) is None


def test_the_home_address_is_the_bare_shell():
    assert ux_walk.Address("").fragment == ""
    assert ux_walk.Address("").slug == "home"


def _visit(fragment, *, how="link", links=(), buttons=(), settled=("idle",)):
    address = ux_walk.parse_fragment(fragment, {})
    visit = ux_walk.Visit(address=address, reached_by=how, depth=None, links_to=list(links), buttons_to=list(buttons))
    visit.captures = [ux_walk.Capture(address, f"variant-{n}", "x.png", state) for n, state in enumerate(settled)]
    return visit


def test_the_summary_names_each_finding_by_its_own_rule():
    """One member per summary field that would make it non-empty, and one beside it that must not."""
    declared = {key: ux_walk.Route(key, "absent", None, None) for key in ("collection", "walls", "work", "taste")}
    visits = [
        _visit("#collection", how="home", links=["#walls", "#walls?x=1"], buttons=[{"button": "A", "to": "#work/1"}]),
        _visit("#walls", links=["#collection"], settled=("idle", "busy")),
        _visit("#work/1", how="button", buttons=[{"button": "Back", "to": "#collection"}]),
        _visit("#ghost", how="link", settled=("blank",)),
    ]
    walk = ux_walk.Walk(base_url="x", synthetic=None, declared=declared, visits={v.address: v for v in visits})
    walk.refused_writes = [{"method": "POST", "url": "/api/seen"}, {"method": "POST", "url": "/api/x", "after_click": "Hang"}]

    summary = ux_walk.summarise(walk)

    assert summary["reached_only_by_button"] == ["work"]
    assert summary["declared_not_reached_by_link"] == ["taste", "work"]
    assert summary["declared_never_visited"] == ["taste"]
    assert summary["reached_not_declared"] == ["ghost"]
    # A page whose only way on is a button is not a dead end; one with neither is.
    assert summary["dead_ends"] == ["#ghost"]
    assert summary["unsettled"] == ["#ghost (blank)", "#walls (busy)"]
    # Counted once per page linking in, not once per link.
    assert summary["pages_linking_in"] == {"collection": 1, "walls": 1}
    assert summary["refused_on_load"] == [{"method": "POST", "url": "/api/seen"}]
    assert [entry["after_click"] for entry in summary["refused_after_click"]] == ["Hang"]


def test_a_tampered_axe_is_not_run(tmp_path, monkeypatch):
    """A cached script that is not the pinned release is not trusted, and with no network it reads as not run."""
    cache = tmp_path / "axe.min.js"
    cache.write_text("window.axe = {run: async () => ({violations: []})};", encoding="utf-8")
    monkeypatch.setattr(ux_walk, "AXE_URL", "http://127.0.0.1:9/axe.min.js")

    source, why = ux_walk._fetch_axe(cache)

    assert source is None
    assert why.startswith("not run: axe-core could not be fetched")


class _StubbornServer:
    """A server that does not exit on SIGTERM: `wait` times out, as `subprocess.Popen.wait` would."""

    def __init__(self):
        self.signals = []

    def send_signal(self, number):
        self.signals.append(number)

    def wait(self, timeout):
        raise subprocess.TimeoutExpired(cmd="python -m arrt", timeout=timeout)


def test_a_server_that_ignores_sigterm_still_loses_its_scratch_library_and_says_so(tmp_path):
    """`stop_synthetic`'s promise: the scratch ART_ROOT goes either way, and the timeout reaches the caller."""
    root = tmp_path / "ux-walk-scratch"
    (root / "raw").mkdir(parents=True)
    server = _StubbornServer()

    with pytest.raises(subprocess.TimeoutExpired):
        ux_walk.stop_synthetic(server, root)

    assert server.signals == [signal.SIGTERM]
    assert not root.exists()
