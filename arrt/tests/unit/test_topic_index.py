"""Library › Topics and a Topic page's library half, read from the facet rows alone.

`TopicService.index` and `page` ask no registry: they read what the topic sweep
wrote, so they answer at once whatever Wikidata is doing. Rows are written here
through the catalogue service, as the sweep writes them, so the counts are
checked against rows the test can see.
"""

import sqlite3

import pytest
from fakes import FakeRegistry

from arrt.library.registry import TopicKind
from arrt.library.services.catalogue import CatalogueService, FacetClaim
from arrt.library.services.topic_sweep import SOURCE_NOTE
from arrt.library.services.topics import TOPICS_NOT_CONFIGURED_NOTE, TopicState
from arrt.persistence.durable import SqliteDurableStore
from arrt.persistence.file import open_catalogue_file
from arrt.persistence.records import FacetDerivation, VocabularyKind
from arrt.persistence.sqlite import CATALOGUE_SCHEMA, SqliteCatalogue
from arrt.persistence.sqlite_discovery import DISCOVERY_SCHEMA
from arrt.services.errors import ServiceError

IMPRESSIONISM = FacetClaim(kind=VocabularyKind.MOVEMENT, value="Impressionism", value_qid="Q40415")
C19 = FacetClaim(kind=VocabularyKind.ERA, value="19th century", value_qid="Q6955")
C20 = FacetClaim(kind=VocabularyKind.ERA, value="20th century", value_qid="Q6927")
PAINTING = FacetClaim(kind=VocabularyKind.MEDIUM, value="painting", value_qid="Q3305213")
#: An item that is both what a work is said to be of and its artist's movement.
ABSTRACT_SUBJECT = FacetClaim(kind=VocabularyKind.SUBJECT, value="abstract art", value_qid="Q128115")
ABSTRACT_MOVEMENT = FacetClaim(kind=VocabularyKind.MOVEMENT, value="abstract art", value_qid="Q128115")


@pytest.fixture
def registry():
    return FakeRegistry(failing=True)


def sourced(service, work, *claims):
    service.replace_sourced_facets(work.id, source_note=SOURCE_NOTE, claims=claims)


@pytest.fixture
def held(service):
    """Three works in circulation and one archived, with facets as the sweep writes them, plus rows that are not topics."""
    monet = service.add_artwork(title="Impression, Sunrise")
    renoir = service.add_artwork(title="Bal du moulin de la Galette")
    kandinsky = service.add_artwork(title="Composition VII")
    archived = service.add_artwork(title="Water Lilies")
    sourced(service, monet, C19, IMPRESSIONISM, PAINTING)
    sourced(service, renoir, C19, IMPRESSIONISM, PAINTING)
    sourced(service, kandinsky, C20, PAINTING, ABSTRACT_SUBJECT, ABSTRACT_MOVEMENT)
    sourced(service, archived, C19, IMPRESSIONISM)
    service.archive_artwork(archived.id)
    # A value nobody tied to an item has no page to open, and a palette is no topic.
    service.record_facet(artwork_id=monet.id, kind=VocabularyKind.SUBJECT, value="harbour", derivation=FacetDerivation.INFERRED)
    service.record_facet(
        artwork_id=monet.id,
        kind=VocabularyKind.PALETTE,
        value="blue",
        derivation=FacetDerivation.INFERRED,
        value_qid="Q1088",
    )
    return monet, renoir, kandinsky, archived


class TestTheIndex:
    def test_counts_match_the_rows_for_works_in_circulation(self, services, held, store):
        index = services.topics.index()

        listed = {group.kind: [(topic.qid, topic.label, topic.works) for topic in group.topics] for group in index.groups}
        assert listed == {
            TopicKind.PERIOD: [("Q6955", "19th century", 2), ("Q6927", "20th century", 1)],
            TopicKind.MOVEMENT: [("Q128115", "abstract art", 1), ("Q40415", "Impressionism", 2)],
            TopicKind.SUBJECT: [("Q128115", "abstract art", 1)],
            TopicKind.MEDIUM: [("Q3305213", "painting", 3)],
        }
        # Recounted from the rows themselves, so the index cannot agree with
        # itself and disagree with the table.
        circulating = set(store.accepted_artwork_ids())
        for group in index.groups:
            for topic in group.topics:
                carriers = {
                    work_id
                    for work_id in circulating
                    for facet in store.list_facets(work_id)
                    if facet.value_qid == topic.qid and facet.kind is _FACET_OF[group.kind]
                }
                assert topic.works == len(carriers), topic

    def test_a_work_carrying_one_item_under_two_values_is_counted_once(self, services, service):
        """A later inferred value may name an item the sweep's value already names."""
        monet = service.add_artwork(title="Impression, Sunrise")
        sourced(service, monet, IMPRESSIONISM)
        service.record_facet(
            artwork_id=monet.id,
            kind=VocabularyKind.MOVEMENT,
            value="Impressionist",
            derivation=FacetDerivation.INFERRED,
            value_qid="Q40415",
        )

        (movement,) = [group for group in services.topics.index().groups if group.kind is TopicKind.MOVEMENT]

        assert [(topic.qid, topic.label, topic.works) for topic in movement.topics] == [("Q40415", "Impressionism", 1)]

    def test_every_kind_is_listed_period_first_even_when_empty(self, services):
        index = services.topics.index()

        assert [group.kind for group in index.groups] == [
            TopicKind.PERIOD,
            TopicKind.MOVEMENT,
            TopicKind.SUBJECT,
            TopicKind.MEDIUM,
        ]
        assert all(group.topics == () for group in index.groups)

    def test_it_asks_no_registry(self, services, held, registry):
        """The registry here fails every question; the index answers anyway."""
        assert services.topics.index().state is TopicState.KNOWN


class TestTheLibrarysHalfOfATopicPage:
    def test_your_works_in_it_by_title_in_circulation_only(self, services, held):
        monet, renoir, _kandinsky, _archived = held

        page = services.topics.page("Q40415")

        assert (page.label, page.kinds, list(page.work_ids)) == ("Impressionism", (TopicKind.MOVEMENT,), [renoir.id, monet.id])

    def test_an_item_carried_under_two_kinds_lists_both_and_each_work_once(self, services, held):
        _monet, _renoir, kandinsky, _archived = held

        page = services.topics.page("Q128115")

        assert page.kinds == (TopicKind.MOVEMENT, TopicKind.SUBJECT)
        assert list(page.work_ids) == [kandinsky.id]

    def test_a_topic_no_work_is_in_has_no_label_and_no_works(self, services, held):
        page = services.topics.page("Q1311")

        assert (page.state, page.label, page.kinds, tuple(page.work_ids)) == (TopicState.KNOWN, None, (), ())

    def test_a_value_on_a_kind_that_is_not_a_topic_opens_no_page(self, services, held):
        assert services.topics.page("Q1088").work_ids == ()

    def test_an_address_that_is_not_a_qid_is_refused(self, services):
        with pytest.raises(ServiceError, match="not a Wikidata item id"):
            services.topics.page("Impressionism")


class TestWithNoRegistry:
    @pytest.fixture
    def registry(self):
        return None

    def test_both_say_topics_need_a_user_agent_and_still_read_the_rows(self, services, held):
        index, page = services.topics.index(), services.topics.page("Q40415")

        assert (index.state, index.note) == (TopicState.NOT_CONFIGURED, TOPICS_NOT_CONFIGURED_NOTE)
        assert (page.state, page.note) == (TopicState.NOT_CONFIGURED, TOPICS_NOT_CONFIGURED_NOTE)
        assert len(page.work_ids) == 2


class TestTheColumnReachesAnOlderFile:
    """`value_qid` is added by widening: a file written before it gains it on the next open."""

    def test_an_older_file_gains_the_column_and_keeps_its_rows(self, tmp_path):
        path = tmp_path / "catalogue.sqlite"
        before = CATALOGUE_SCHEMA.replace(",\n    value_qid    TEXT", "").replace(
            "CREATE INDEX IF NOT EXISTS work_facets_by_item ON work_facets(value_qid);", ""
        )
        older = SqliteDurableStore(path, before + DISCOVERY_SCHEMA)
        columns = {row["name"] for row in older.select_rows("SELECT name FROM pragma_table_info('work_facets')")}
        assert "value_qid" not in columns, "the older file already has the column, so this proves nothing"
        work = CatalogueService(SqliteCatalogue(older)).add_artwork(title="Written before topics")
        older.close()
        with sqlite3.connect(path) as connection:
            connection.execute(
                "INSERT INTO work_facets (id, artwork_id, kind, value, derivation, source_note, created_at) "
                "VALUES ('f-1', ?, 'era', '20th c.', 'inferred', NULL, '2026-08-12T00:00:00+00:00')",
                (work.id,),
            )
        connection.close()

        reopened = open_catalogue_file(path)
        try:
            service = CatalogueService(SqliteCatalogue(reopened))
            (kept,) = service.facets_for(work.id)
            assert (kept.value, kept.value_qid) == ("20th c.", None)
            service.replace_sourced_facets(work.id, source_note=SOURCE_NOTE, claims=[C20])
            assert {(facet.value, facet.value_qid) for facet in service.facets_for(work.id)} == {
                ("20th c.", None),
                ("20th century", "Q6927"),
            }
        finally:
            reopened.close()


_FACET_OF = {
    TopicKind.PERIOD: VocabularyKind.ERA,
    TopicKind.MOVEMENT: VocabularyKind.MOVEMENT,
    TopicKind.SUBJECT: VocabularyKind.SUBJECT,
    TopicKind.MEDIUM: VocabularyKind.MEDIUM,
}
