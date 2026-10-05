"""The matching command as it is actually invoked.

Run through `main` for the reason the seed command's test gives: what a command
does with the objects it builds is only proven by running the command. The
registry is a fake, installed where the command would build the real one, so
nothing here reaches Wikidata.
"""

import pytest

from arrt.identify import __main__ as command
from arrt.library.registry import RegistryUnavailable
from arrt.library.registry.identifiers import IdentifierScheme
from arrt.library.services.catalogue import CatalogueService
from arrt.persistence.file import open_catalogue_file
from arrt.persistence.records import AcquisitionMethod, RightsStatus, SourceClass
from arrt.persistence.sqlite import SqliteCatalogue


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    """This process's environment and nothing else, so a run can never write to the real art tree."""
    monkeypatch.setattr("arrt.config.load_dotenv", lambda **_: False)
    monkeypatch.setenv("ART_ROOT", str(tmp_path / "art"))
    monkeypatch.delenv("WIKIDATA_USER_AGENT", raising=False)
    (tmp_path / "art").mkdir()


@pytest.fixture
def catalogue_path(tmp_path):
    path = tmp_path / "art" / "catalogue.sqlite"
    opened = open_catalogue_file(path)
    service = CatalogueService(SqliteCatalogue(opened), art_root=tmp_path / "art")
    kline = service.add_artist(name="Franz Kline", born=1910, died=1962)
    work = service.add_artwork(title="Painting", artist_id=kline.id)
    service.add_source(
        artwork_id=work.id,
        url="https://www.artic.edu/artworks/102581/painting",
        provider="artic",
        source_class=SourceClass.INSTITUTIONAL,
        acquisition_method=AcquisitionMethod.DIRECT_HTTP,
        rights_status=RightsStatus.PUBLIC_DOMAIN,
    )
    opened.close()
    return path


class FakeWikidata:
    def __init__(self, *, user_agent, fail=False):
        self.user_agent = user_agent
        self.fail = fail

    def works_by_identifier(self, scheme, values):
        if self.fail:
            raise RegistryUnavailable("Wikidata answered HTTP 503.")
        return {"102581": frozenset({"Q20266396"})} if scheme is IdentifierScheme.ARTIC else {}

    def creators_of(self, work_qids):
        return {"Q20266396": frozenset({"Q374492"})}

    def people_named(self, name):
        return []

    def close(self):
        pass


def test_without_a_user_agent_it_matches_nothing_and_says_how_to_fix_it(catalogue_path, capsys):
    assert command.main([]) == 2
    assert "WIKIDATA_USER_AGENT" in capsys.readouterr().err


def test_it_matches_the_catalogue_and_reports_what_it_found(catalogue_path, monkeypatch, capsys):
    monkeypatch.setenv("WIKIDATA_USER_AGENT", "arrt-test (+https://example.org)")
    built = []
    monkeypatch.setattr(command, "WikidataRegistry", lambda **kw: built.append(FakeWikidata(**kw)) or built[-1])

    assert command.main([]) == 0

    assert built[0].user_agent == "arrt-test (+https://example.org)"
    out = capsys.readouterr().out
    assert "Works: 1 matched" in out
    assert "Artists: 1 matched" in out
    opened = open_catalogue_file(catalogue_path)
    try:
        assert [artist.wikidata_qid for artist in SqliteCatalogue(opened).list_artists()] == ["Q374492"]
    finally:
        opened.close()


def test_an_outage_is_reported_as_one_rather_than_as_nothing_found(catalogue_path, monkeypatch, capsys):
    monkeypatch.setenv("WIKIDATA_USER_AGENT", "arrt-test (+https://example.org)")
    monkeypatch.setattr(command, "WikidataRegistry", lambda **kw: FakeWikidata(fail=True, **kw))

    assert command.main([]) == 1
    assert "HTTP 503" in capsys.readouterr().err
