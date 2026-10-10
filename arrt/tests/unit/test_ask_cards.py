"""Which items a reply offers as cards, and what each card says.

The payloads here are written out by hand, for the edge cases a fixture of the
real surface would not reach. The real ones are read in
`tests/integration/test_registry_tools.py`, one case per action Ask is offered,
so a binding that renames a field fails there rather than leaving these green.
"""

from arrt.ask.cards import cards_for, items_in, qids_named

HUNTERS = "Q500985"
BRUEGEL = "Q43270"
ROTHKO = "Q160149"
KHM = "Q95569"
RENAISSANCE = "Q4692"

SEARCH = {
    "success": True,
    "artists": [{"qid": ROTHKO, "name": "Mark Rothko", "born": 1903, "died": 1970, "artist_id": None}],
    "works": [
        {
            "qid": HUNTERS,
            "title": "The Hunters in the Snow",
            "image": "https://commons.example/Hunters.jpg",
            "creator": {"qid": BRUEGEL, "name": "Pieter Brueghel the Elder", "artist_id": None},
            "held_artwork_ids": [],
        }
    ],
}

#: An artist's page: the works list its makers on the page, not the work, and the museums carry names and QIDs too.
ARTIST_HOLDING_HUNTERS = {
    "success": True,
    "qid": BRUEGEL,
    "name": "Pieter Brueghel the Elder",
    "born": 1525,
    "died": 1569,
    "artist_id": "artist-7",
    "works": [{"qid": HUNTERS, "title": "The Hunters in the Snow", "held_artwork_ids": ["work-1"]}],
    "holdings": [{"qid": KHM, "name": "Kunsthistorisches Museum", "works": 12}],
}

TOPIC = {"success": True, "topics": [{"qid": RENAISSANCE, "label": "Renaissance", "kinds": ["period", "movement"]}]}


def test_each_shape_is_read_as_its_kind():
    found = {**items_in(SEARCH), **items_in(TOPIC)}

    assert found[HUNTERS].kind == "work"
    assert found[HUNTERS].label == "The Hunters in the Snow"
    assert found[HUNTERS].detail == "Pieter Brueghel the Elder"
    assert found[HUNTERS].image == "https://commons.example/Hunters.jpg"
    assert found[HUNTERS].held is None
    assert found[BRUEGEL].kind == "artist"
    assert found[ROTHKO].kind == "artist"
    assert found[ROTHKO].detail == "1903–1970"
    assert found[RENAISSANCE].kind == "topic"
    assert found[RENAISSANCE].kinds == ("period", "movement")


def test_a_museum_is_not_an_artist():
    found = items_in(ARTIST_HOLDING_HUNTERS)

    assert KHM not in found
    assert found[BRUEGEL].kind == "artist"
    assert found[BRUEGEL].held == "artist-7"


def test_only_what_the_answer_names_becomes_a_card_in_the_answers_order():
    answer = f"Try Rothko [{ROTHKO}], and The Hunters in the Snow [{HUNTERS}]."

    cards = cards_for(answer, [SEARCH])

    assert [card["qid"] for card in cards] == [ROTHKO, HUNTERS]
    assert BRUEGEL not in {card["qid"] for card in cards}


def test_an_item_no_tool_returned_gets_no_card():
    cards = cards_for(f"The Hunters [{HUNTERS}] and something invented [Q999999999].", [SEARCH])

    assert [card["qid"] for card in cards] == [HUNTERS]


def test_the_librarys_answer_wins_whichever_payload_came_first():
    for payloads in ([SEARCH, ARTIST_HOLDING_HUNTERS], [ARTIST_HOLDING_HUNTERS, SEARCH]):
        (card,) = cards_for(f"[{HUNTERS}]", payloads)
        assert card["held"] == "work-1"


def test_a_qid_named_twice_is_one_card():
    assert qids_named(f"[{HUNTERS}] then [{ROTHKO}] then [{HUNTERS}] again") == [HUNTERS, ROTHKO]
    assert len(cards_for(f"[{HUNTERS}] and again [{HUNTERS}]", [SEARCH])) == 1


def test_years_say_what_is_known():
    def years(**person):
        return items_in({"qid": "Q1", "name": "Someone", **person})["Q1"].detail

    assert years(born=1900, died=1980) == "1900–1980"
    assert years(born=1950, died=None) == "born 1950"
    assert years(born=None, died=1500) == "died 1500"
    assert years(born=None, artist_id=None) == ""


def test_a_work_read_from_the_library_becomes_a_held_card():
    """`art_catalogue(action='get')` names its item `wikidata_qid` and its library id `artwork_id`.

    Neither is the registry's `qid`, so a card built only from that key never
    offered a work the agent read from the library.
    """
    payload = {
        "success": True,
        "artwork": {
            "artwork_id": "work-9",
            "title": "Hunters in the Snow",
            "wikidata_qid": HUNTERS,
            "artist": {"artist_id": "artist-7", "name": "Pieter Brueghel the Elder", "born": 1525},
        },
    }

    (card,) = cards_for(f"You hold it [{HUNTERS}].", [payload])

    assert (card["kind"], card["qid"], card["held"]) == ("work", HUNTERS, "work-9")
    assert card["detail"] == "Pieter Brueghel the Elder"
