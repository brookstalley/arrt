"""Making a held original wall-ready, and deciding when there is anything to do.

What is asserted here is the policy above the mat engine and the master maker,
which are tested beside this: when a model is worth paying for, what counts as a
current presentation master, and what a curator's own colour does.

The staleness rules get the most attention because they are the ones a green
suite is least able to notice going wrong — a master that is silently served
stale looks exactly like one that is correct, on every surface, until someone
walks past the wall.
"""

import sqlite3
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from PIL import Image

from arrt.library.acquisition.master import MASTER_RULE
from arrt.library.acquisition.mat import MatChoice, MatEngine
from arrt.library.acquisition.preparation import (
    PreparationOutcome,
    PreparationService,
    PreparationSettings,
)
from arrt.persistence.discovery_records import SpendCategory
from arrt.persistence.records import (
    AcquisitionMethod,
    FetchStatus,
    MatColor,
    MatMethod,
    RenditionKind,
    RightsStatus,
    SourceClass,
)
from arrt.programming.manifest.v2 import read_published
from arrt.services.errors import ServiceError


@pytest.fixture
def prep(services) -> PreparationService:
    return services.preparation


@pytest.fixture
def prep_settings(settings) -> PreparationSettings:
    return PreparationSettings(art_root=settings.art_root)


def _spending_engine(hex_rgb: str, cost: Decimal) -> MatEngine:
    """A mat engine that answers as a paid model would, without a network.

    Substituting the *choice* rather than the transport, because what is under
    test here is what the service does with a cost — not how a cost is parsed,
    which `test_mat_engine.py` drives through the real client.
    """

    class _Paid(MatEngine):
        def choose(self, image_path):
            return MatChoice(
                hex_rgb=hex_rgb,
                method=MatMethod.VISION_MODEL,
                reason="A canned answer.",
                model_id="qwen/qwen3.7-flash",
                cost_usd=cost,
            )

    return _Paid(None, image_max_edge=256)


def _work_with_original(service, settings, *, width=2400, height=1800, colour=(30, 60, 120), content_hash="hash-one"):
    """A catalogued work whose original is real bytes on disk.

    Real, because everything downstream decodes them: a stand-in would make every
    assertion here depend on Pillow never being asked to open the file.
    """
    work = service.add_artwork(title="Nighthawks")
    source = service.add_source(
        artwork_id=work.id,
        url="https://gallery.example.com/a.jpg",
        provider="gallery_site",
        source_class=SourceClass.CONTEMPORARY_WEB,
        acquisition_method=AcquisitionMethod.DIRECT_HTTP,
        rights_status=RightsStatus.UNKNOWN,
        is_primary=True,
    )
    originals = settings.art_root / "raw"
    originals.mkdir(parents=True, exist_ok=True)
    path = originals / f"{work.id}.jpg"
    Image.new("RGB", (width, height), colour).save(path, format="JPEG", quality=90)
    service.record_original(
        artwork_id=work.id,
        source_id=source.id,
        path=str(path.relative_to(settings.art_root)),
        width=width,
        height=height,
        byte_size=path.stat().st_size,
        content_hash=content_hash,
        fetch_status=FetchStatus.OK,
    )
    return work, path


class TestPreparingAWorkForTheFirstTime:
    def test_it_gets_a_mat_a_master_and_a_rendition_row(self, prep, service, settings):
        work, _ = _work_with_original(service, settings)

        result = prep.prepare(work.id)

        assert result.outcome is PreparationOutcome.PREPARED
        assert service.current_mat_color(work.id) is not None
        made = settings.art_root / result.relative_path
        assert made.is_file()
        with Image.open(made) as master:
            assert master.size == (2400, 1800), "a master below the cap keeps the original's own size"

    def test_the_master_names_no_geometry(self, prep, service, settings):
        """Geometry in columns, not in the filename. The 2024 tree's `_w648_h480`
        suffix is why a recovered catalogue pointed at a panel that no longer
        existed."""
        work, _ = _work_with_original(service, settings)

        prep.prepare(work.id)

        [view] = masters(service, work.id)
        assert Path(view.rendition.relative_path).name == f"{work.id}.jpg"

    def test_the_master_is_born_current(self, prep, service, settings):
        work, _ = _work_with_original(service, settings)

        prep.prepare(work.id)

        [view] = masters(service, work.id)
        assert view.stale is False

    def test_a_deployment_with_no_key_records_the_mechanical_method(self, prep, service, settings):
        """The suite wires no model client, which is the keyless deployment
        exactly. The colour is real and it says where it came from."""
        work, _ = _work_with_original(service, settings)

        result = prep.prepare(work.id)

        assert result.mat_method == MatMethod.DOMINANT_COLOR_FALLBACK.value
        assert service.current_mat_color(work.id).method is MatMethod.DOMINANT_COLOR_FALLBACK

    def test_nothing_is_composed_for_a_screen(self, prep, service, settings):
        """Each Player draws its own mat, so preparation writes the master and nothing else."""
        work, _ = _work_with_original(service, settings)

        prep.prepare(work.id)

        assert [view.rendition.kind for view in service.list_renditions(work.id)] == [RenditionKind.PRESENTATION_MASTER]
        assert not (settings.art_root / "ready").exists()


class TestPreparingAgain:
    def test_a_current_work_is_left_alone(self, prep, service, settings):
        work, _ = _work_with_original(service, settings)
        first = prep.prepare(work.id)

        second = prep.prepare(work.id)

        assert second.outcome is PreparationOutcome.UNCHANGED
        assert second.relative_path == first.relative_path

    def test_re_preparing_never_re_chooses_the_mat(self, prep, service, settings):
        """**The reason a remake is free.** Re-asking a model for a colour the
        work already has would both spend money and quietly replace a decision —
        including a curator's own, which is the worst version of it."""
        work, _ = _work_with_original(service, settings)
        prep.prepare(work.id)
        service.record_mat_color(artwork_id=work.id, hex_rgb="#6b6b6b", method=MatMethod.MANUAL)

        prep.prepare(work.id, force=True)

        current = service.current_mat_color(work.id)
        assert current.hex_rgb == "#6b6b6b"
        assert current.method is MatMethod.MANUAL

    def test_force_makes_a_current_master_again(self, prep, service, settings):
        work, _ = _work_with_original(service, settings)
        prep.prepare(work.id)
        [before] = masters(service, work.id)

        forced = prep.prepare(work.id, force=True)

        [after] = masters(service, work.id)
        assert forced.outcome is PreparationOutcome.PREPARED
        assert after.rendition.generated_at > before.rendition.generated_at

    def test_only_one_master_row_accumulates_per_work(self, prep, service, settings):
        """A row per make would make "which master is current" a question with
        several answers."""
        work, _ = _work_with_original(service, settings)
        prep.prepare(work.id)
        prep.prepare(work.id, force=True)
        prep.prepare(work.id, force=True)

        assert len(masters(service, work.id)) == 1


def _forget_the_master(settings, artwork_id):
    """Leave a work as it was before masters existed: a mat, and no master row.
    Nothing in the product deletes a rendition, so this reaches the file directly."""
    connection = sqlite3.connect(settings.catalogue_path)
    with connection:
        connection.execute(
            'DELETE FROM renditions WHERE "artwork_id" = ? AND "kind" = ?',
            (artwork_id, str(RenditionKind.PRESENTATION_MASTER)),
        )
    connection.close()


def masters(service, artwork_id):
    return [view for view in service.list_renditions(artwork_id) if view.rendition.kind is RenditionKind.PRESENTATION_MASTER]


class TestThePresentationMaster:
    def test_a_first_preparation_makes_a_current_master_at_the_cap(self, prep, service, settings):
        work, _ = _work_with_original(service, settings, width=9000, height=6000)

        prep.prepare(work.id)

        [view] = masters(service, work.id)
        assert view.stale is False
        assert view.rendition.relative_path == f"presentation/{work.id}.jpg"
        with Image.open(settings.art_root / view.rendition.relative_path) as written:
            assert written.size == (7680, 5120)
        assert view.rendition.content_sha256, "a Player fetches it by this hash"

    def test_a_work_with_a_mat_and_no_master_gets_its_master_and_nothing_else(self, prep, service, settings):
        """The state every work held before masters existed is in: the backfill
        reaches it through `prepare`, which makes the master and keeps the mat."""
        work, _ = _work_with_original(service, settings)
        prep.prepare(work.id)
        _forget_the_master(settings, work.id)
        assert masters(service, work.id) == []

        mat = service.current_mat_color(work.id)

        result = prep.prepare(work.id)

        assert result.outcome is PreparationOutcome.PREPARED
        assert result.detail == "its presentation master was made"
        assert len(masters(service, work.id)) == 1
        assert service.current_mat_color(work.id) == mat

    def test_a_current_master_is_left_alone(self, prep, service, settings):
        work, _ = _work_with_original(service, settings)
        prep.prepare(work.id)
        [before] = masters(service, work.id)

        result = prep.prepare(work.id)

        [after] = masters(service, work.id)
        assert after.rendition.generated_at == before.rendition.generated_at
        assert "presentation master was made" not in result.detail

    def test_a_new_original_makes_the_master_stale_and_it_is_replaced(self, prep, service, settings, store):
        work, path = _work_with_original(service, settings)
        prep.prepare(work.id)
        [before] = masters(service, work.id)
        source = service.list_sources(work.id)[0]
        Image.new("RGB", (1600, 1200), (200, 40, 40)).save(path, format="JPEG", quality=90)
        service.record_original(
            artwork_id=work.id,
            source_id=source.id,
            path=str(path.relative_to(settings.art_root)),
            width=1600,
            height=1200,
            byte_size=path.stat().st_size,
            content_hash="hash-two",
            fetch_status=FetchStatus.OK,
        )
        assert masters(service, work.id)[0].stale is True
        assert store.works_owing_a_presentation_master(MASTER_RULE) == [work.id], "the startup backfill sees it too"

        prep.prepare(work.id)

        [after] = masters(service, work.id)
        assert after.stale is False
        assert store.works_owing_a_presentation_master(MASTER_RULE) == []
        assert after.rendition.id == before.rendition.id, "one row per work, rewritten"
        assert after.rendition.content_sha256 != before.rendition.content_sha256

    def test_a_master_made_by_an_older_rule_is_made_again(self, prep, service, settings, store):
        """The hash cannot see a changed cap or quality: the Original is the same.
        So a master records the rule it was made by, and one made the old way is
        owed again, at startup and in `prepare`."""
        work, _ = _work_with_original(service, settings)
        prep.prepare(work.id)
        [before] = masters(service, work.id)
        assert before.rendition.layout == MASTER_RULE
        store.update_rendition(replace(before.rendition, layout="presentation-master long-edge=4096 jpeg-q=85"))
        assert store.works_owing_a_presentation_master(MASTER_RULE) == [work.id]

        prep.prepare(work.id)

        [after] = masters(service, work.id)
        assert after.rendition.layout == MASTER_RULE
        assert after.rendition.generated_at > before.rendition.generated_at
        assert store.works_owing_a_presentation_master(MASTER_RULE) == []

    def test_a_master_missing_from_disk_is_made_again(self, prep, service, settings):
        work, _ = _work_with_original(service, settings)
        prep.prepare(work.id)
        [view] = masters(service, work.id)
        (settings.art_root / view.rendition.relative_path).unlink()

        prep.prepare(work.id)

        assert (settings.art_root / view.rendition.relative_path).is_file()

    def test_a_new_mat_leaves_the_master_as_it_was(self, prep, service, settings):
        """The master carries no mat, so a mat change must not touch it: a Player
        holding it by hash keeps a copy that is still right."""
        work, _ = _work_with_original(service, settings)
        prep.prepare(work.id)
        [before] = masters(service, work.id)

        service.record_mat_color(artwork_id=work.id, hex_rgb="#ff0000", method=MatMethod.MANUAL)
        prep.prepare(work.id)

        [after] = masters(service, work.id)
        assert after.rendition.content_sha256 == before.rendition.content_sha256
        assert after.rendition.generated_at == before.rendition.generated_at


class TestChoosingTheMatAgain:
    def test_it_supersedes_without_discarding_the_previous_choice(self, prep, service, settings):
        """Mat quality is this product's subjective bar, so "the new model picked
        a worse colour" has to be both answerable and reversible."""
        work, _ = _work_with_original(service, settings)
        prep.prepare(work.id)
        service.record_mat_color(artwork_id=work.id, hex_rgb="#123456", method=MatMethod.MANUAL)

        prep.choose_mat(work.id)

        history = service.mat_color_history(work.id)
        assert len(history) >= 2
        assert sum(1 for colour in history if colour.is_current) == 1
        assert any(colour.hex_rgb == "#123456" and not colour.is_current for colour in history)

    def test_the_new_colour_leaves_the_master_as_it_was(self, prep, service, settings):
        """The colour rides each wall's feed, so choosing again makes nothing: a
        Player holding the master by hash keeps a copy that is still right."""
        work, _ = _work_with_original(service, settings)
        prep.prepare(work.id)
        [before] = masters(service, work.id)

        result = prep.choose_mat(work.id)

        [after] = masters(service, work.id)
        assert after.rendition.content_sha256 == before.rendition.content_sha256
        assert result.relative_path == before.rendition.relative_path
        assert service.current_mat_color(work.id).hex_rgb == result.mat_hex

    def test_the_fallback_reason_reaches_the_caller(self, prep, service, settings):
        work, _ = _work_with_original(service, settings)

        result = prep.choose_mat(work.id)

        assert result.mat_fallback_detail is not None
        assert result.cost_usd == Decimal(0)


class TestACuratorsOwnColour:
    def test_it_is_recorded_as_manual_and_reaches_the_feed(self, prep, service, settings, display, wall_id):
        """Recorded, and on every wall showing the work at once: the Library
        announces the change and each feed carries the new colour."""
        work, _ = _work_with_original(service, settings)
        prep.prepare(work.id)
        theme = display.add_theme(name="Under test")
        display.add_to_theme(theme_id=theme.id, artwork_id=work.id)
        display.activate_theme(theme.id, wall_id=wall_id)

        result = prep.set_mat(work.id, "#27285b")

        assert result.mat_hex == "#27285b"
        assert service.current_mat_color(work.id).method is MatMethod.MANUAL
        feed = read_published(settings.manifest_v2_path(wall_id))
        assert feed.works[work.id]["mat_color"] == "#27285b"

    @pytest.mark.parametrize("spelling", ["#27285B", "27285b", "#abc"])
    def test_a_person_may_spell_a_colour_the_way_the_model_is_allowed_to(self, prep, service, settings, spelling):
        """One answer to "what is a hex colour", whoever is asking.

        The mat engine's reader is deliberately lenient about shorthand, a missing
        `#` and upper case — measured leniency, a probed model really did answer
        `3F6F7A`. The catalogue's own check takes only lower-case `#rrggbb`. Until
        these were joined the product accepted `#abc` from a model and refused it
        from a person, on a tool whose parameter says only "a hex triplet".
        """
        work, _ = _work_with_original(service, settings)
        prep.prepare(work.id)

        result = prep.set_mat(work.id, spelling)

        # Stored in the one spelling the catalogue compares by, so re-choosing the
        # colour already in force still reads as no change rather than as history.
        assert result.mat_hex == result.mat_hex.lower()
        assert service.current_mat_color(work.id).hex_rgb == result.mat_hex
        assert result.mat_hex.startswith("#")
        assert len(result.mat_hex) == 7

    def test_an_unreadable_colour_is_refused_before_anything_is_written(self, prep, service, settings):
        work, _ = _work_with_original(service, settings)
        prep.prepare(work.id)
        before = service.current_mat_color(work.id).hex_rgb

        with pytest.raises(ServiceError):
            prep.set_mat(work.id, "octarine")

        assert service.current_mat_color(work.id).hex_rgb == before

    def test_a_colour_below_the_floor_is_refused_before_anything_is_written(self, prep, service, settings):
        """A person's colour is held to the floor too (owner, 2026-10-03).
        Accepted, it would be on the wall against the ruling, and the next
        preparation would choose again over the person's head. `#252525` is
        L* 14.7, the darkest grey just under the floor."""
        work, _ = _work_with_original(service, settings)
        prep.prepare(work.id)
        before = service.current_mat_color(work.id).hex_rgb

        with pytest.raises(ServiceError, match=r"darker than the mat floor of L\* 15"):
            prep.set_mat(work.id, "#252525")

        assert service.current_mat_color(work.id).hex_rgb == before

    def test_the_darkest_colour_at_the_floor_is_accepted(self, prep, service, settings):
        """The boundary's other side: `#262626` is L* 15.2."""
        work, _ = _work_with_original(service, settings)
        prep.prepare(work.id)

        assert prep.set_mat(work.id, "#262626").mat_hex == "#262626"


class TestWhatItRefuses:
    def test_a_work_with_no_original_is_refused_with_the_remedy(self, prep, service):
        work = service.add_artwork(title="Nighthawks")

        with pytest.raises(ServiceError, match="acquire it first"):
            prep.prepare(work.id)

    def test_an_original_missing_from_disk_names_itself_rather_than_failing_inside_pillow(self, prep, service, settings):
        """This is what a restored catalogue looks like before re-acquisition
        refills the tree, and "no such file" from deep inside a decoder would
        send whoever reads it to entirely the wrong place."""
        work, path = _work_with_original(service, settings)
        path.unlink()

        with pytest.raises(ServiceError, match="Re-acquire it"):
            prep.prepare(work.id)


class TestWhatItCosts:
    """**Two Critic reviewers found this independently, and it was documented
    backwards.** `regenerate` was published as spending nothing, while the first
    preparation of every acquired work chooses a mat — because a work cannot be
    shown without one and `acquire()` does not prepare. The claim was false on
    exactly the call a curator makes first.
    """

    def test_the_first_preparation_of_a_work_reports_what_choosing_its_mat_cost(
        self, service, discovery, settings, prep_settings
    ):
        work, _ = _work_with_original(service, settings)
        engine = _spending_engine("#27285b", Decimal("0.00006626"))

        result = PreparationService(service, engine, prep_settings, spend=discovery).prepare(work.id)

        assert result.cost_usd == Decimal("0.00006626")

    def test_a_second_preparation_costs_nothing_and_says_so(self, service, discovery, settings, prep_settings):
        """The other half. A field only ever populated on the paying path would be
        indistinguishable from one the caller forgot to read."""
        work, _ = _work_with_original(service, settings)
        engine = _spending_engine("#27285b", Decimal("0.00006626"))
        prep = PreparationService(service, engine, prep_settings, spend=discovery)
        prep.prepare(work.id)

        again = prep.prepare(work.id, force=True)

        assert again.cost_usd == Decimal(0)
        assert again.outcome is PreparationOutcome.PREPARED

    def test_a_mat_chosen_for_a_work_whose_master_is_current_reports_what_it_paid(
        self, service, discovery, settings, prep_settings
    ):
        """A work whose master survived a lost mat row pays for a new mat on a
        call that makes nothing else, and the cost travels with that answer."""
        work, _ = _work_with_original(service, settings)
        engine = _spending_engine("#27285b", Decimal("0.00006626"))
        prep = PreparationService(service, engine, prep_settings, spend=discovery)
        prep.prepare(work.id)
        # The master stays; the mat row goes, as a restored catalogue can leave it.
        for colour in service.mat_color_history(work.id):
            service._store.update_mat_color(replace(colour, is_current=False))

        result = prep.prepare(work.id)

        assert result.outcome is PreparationOutcome.PREPARED
        assert result.detail == "its mat was chosen"
        assert result.cost_usd == Decimal("0.00006626")

    def test_a_fallback_on_the_first_preparation_reaches_the_caller(self, prep, service, settings):
        """The suite's engine has no client, so every first preparation falls
        back — and the reason has to travel, because `regenerate` is where most
        works actually get their mat."""
        work, _ = _work_with_original(service, settings)

        result = prep.prepare(work.id)

        assert result.mat_fallback_detail is not None


def _mat_spend(discovery_store):
    """Every mat spend row, as (artwork, cost, model, units), in no promised order."""
    return {
        (record.artwork_id, record.cost_usd, record.model_id, record.units)
        for record in discovery_store.list_spend_records()
        if record.category is SpendCategory.MAT_COLOR_VISION
    }


class TestWhatItSpendsIsRecorded:
    """A paid mat call writes a `mat_color_vision` row naming the work, on every path that asks.

    Unattended preparation (the acquisition queue) turns an occasional cost into
    a routine one, so the month total has to include it. The row is written where
    the model is asked, so `regenerate`, `set_mat_color` with no colour and the
    queue all record it without any of them knowing to.
    """

    def test_a_first_preparation_records_what_the_model_cost_against_the_work(
        self, service, discovery, discovery_store, settings, prep_settings
    ):
        work, _ = _work_with_original(service, settings)
        prep = PreparationService(service, _spending_engine("#27285b", Decimal("0.00006626")), prep_settings, spend=discovery)

        prep.prepare(work.id)

        assert _mat_spend(discovery_store) == {(work.id, Decimal("0.00006626"), "qwen/qwen3.7-flash", 1)}

    def test_a_preparation_that_asks_nothing_records_nothing_more(
        self, service, discovery, discovery_store, settings, prep_settings
    ):
        work, _ = _work_with_original(service, settings)
        prep = PreparationService(service, _spending_engine("#27285b", Decimal("0.00006626")), prep_settings, spend=discovery)
        prep.prepare(work.id)

        prep.prepare(work.id, force=True)

        assert len(_mat_spend(discovery_store)) == 1

    def test_choosing_the_mat_again_records_a_second_call(self, service, discovery, discovery_store, settings, prep_settings):
        work, _ = _work_with_original(service, settings)
        prep = PreparationService(service, _spending_engine("#27285b", Decimal("0.00006626")), prep_settings, spend=discovery)
        prep.prepare(work.id)

        prep.choose_mat(work.id)

        assert [record.artwork_id for record in discovery_store.list_spend_records()] == [work.id, work.id]

    def test_a_billed_answer_the_engine_could_not_use_is_recorded_against_the_model_asked(
        self, service, discovery, discovery_store, settings, prep_settings
    ):
        """The fallback's `model_id` is None, since no model chose the colour; the model that billed is named anyway."""

        class _BilledFallback(MatEngine):
            @property
            def model_id(self):
                return "qwen/qwen3.7-flash"

            def choose(self, image_path):
                return MatChoice(
                    hex_rgb="#2d2d2d",
                    method=MatMethod.DOMINANT_COLOR_FALLBACK,
                    reason="derived",
                    cost_usd=Decimal("0.00004"),
                    fallback_detail="the model answered with no colour",
                )

        work, _ = _work_with_original(service, settings)
        prep = PreparationService(service, _BilledFallback(None, image_max_edge=256), prep_settings, spend=discovery)

        prep.prepare(work.id)

        assert _mat_spend(discovery_store) == {(work.id, Decimal("0.00004"), "qwen/qwen3.7-flash", 1)}

    def test_a_keyless_preparation_records_no_spend(self, prep, service, discovery_store, settings):
        """The container's own engine has no client: nothing is asked, so a row would claim a call never made."""
        work, _ = _work_with_original(service, settings)

        prep.prepare(work.id)

        assert discovery_store.list_spend_records() == []


class TestAnUndecodableOriginal:
    """**The divergence `library/services/imaging.py` was written to prevent, reproduced.**
    The mat engine translated Pillow's failures and the image maker did not, so
    an undecodable original raised a bare `UnidentifiedImageError` from whichever
    path reached it first — and the path that reaches it first is the common one,
    because a work with a mat skips the engine entirely.
    """

    def _corrupt(self, service, settings):
        work, path = _work_with_original(service, settings)
        path.write_bytes(b"certainly not a JPEG")
        return work

    def test_a_work_with_a_mat_already_recorded_is_refused_by_name(self, prep, service, settings):
        """This is the case that escaped: `prepare` finds a mat, skips the engine,
        and hands the file straight to the master maker."""
        work = self._corrupt(service, settings)
        service.record_mat_color(artwork_id=work.id, hex_rgb="#27285b", method=MatMethod.MANUAL)

        with pytest.raises(ServiceError, match="could not be read"):
            prep.prepare(work.id)

    def test_setting_a_colour_on_one_records_it_and_reads_no_image(self, prep, service, settings):
        """A colour is the curator's decision about the work, and nothing is drawn
        from it on this side, so the bytes are not read and the colour stands. The
        work stays off the wall by its own reason until a master can be made."""
        work = self._corrupt(service, settings)

        result = prep.set_mat(work.id, "#27285b")

        assert result.mat_hex == "#27285b"
        assert service.current_mat_color(work.id).hex_rgb == "#27285b"
        assert result.relative_path is None

    def test_a_work_with_no_mat_yet_is_refused_the_same_way(self, prep, service, settings):
        """The path that already worked, kept honest: both routes now give the
        same named refusal rather than two different exceptions."""
        work = self._corrupt(service, settings)

        with pytest.raises(ServiceError, match="could not be read"):
            prep.prepare(work.id)


def _legacy_mat(service, artwork_id, hex_rgb):
    """Make `hex_rgb` the work's current mat, written to the store directly.

    The service refuses a colour below the floor, so a mat from before the floor
    (the 2024 index's) can only be set up the way it arrived: as a row already in
    the file.
    """
    for colour in service.mat_color_history(artwork_id):
        if colour.is_current:
            service._store.update_mat_color(replace(colour, is_current=False))
    service._store.add_mat_color(
        MatColor(
            id=str(uuid.uuid4()),
            artwork_id=artwork_id,
            hex_rgb=hex_rgb,
            method=MatMethod.MANUAL,
            chosen_at=datetime.now(UTC),
            reason="Carried from 2024.",
        )
    )


class TestAMatBelowTheFloor:
    """A mat darker than the floor predates the owner's ruling of 2026-10-03, and
    preparing the work chooses it again."""

    def _prepared_in(self, service, settings, prep_settings, discovery, hex_rgb):
        """A prepared work whose mat is now `hex_rgb`, and a service whose engine
        answers `#27285b`."""
        work, _ = _work_with_original(service, settings)
        first = PreparationService(service, _spending_engine("#6e4848", Decimal(0)), prep_settings, spend=discovery)
        first.prepare(work.id)
        _legacy_mat(service, work.id, hex_rgb)
        prep = PreparationService(service, _spending_engine("#27285b", Decimal("0.0001")), prep_settings, spend=discovery)
        return work, prep

    def test_it_is_chosen_again(self, service, settings, prep_settings, discovery):
        work, prep = self._prepared_in(service, settings, prep_settings, discovery, "#1c1c1c")

        result = prep.prepare(work.id)

        assert result.outcome is PreparationOutcome.PREPARED
        assert result.mat_hex == "#27285b"
        assert result.cost_usd == Decimal("0.0001")
        assert service.current_mat_color(work.id).hex_rgb == "#27285b"
        # The old colour is history, not gone.
        assert "#1c1c1c" in {colour.hex_rgb for colour in service.mat_color_history(work.id) if not colour.is_current}

    def test_a_mat_at_the_floor_is_kept_and_costs_nothing(self, service, settings, prep_settings, discovery):
        """The guard's other side: `#262626` is L* 15.2, and re-choosing it would
        pay to replace a legal colour on every preparation."""
        work, prep = self._prepared_in(service, settings, prep_settings, discovery, "#262626")
        history = len(service.mat_color_history(work.id))

        result = prep.prepare(work.id)

        assert result.mat_hex == "#262626"
        assert result.cost_usd == Decimal(0)
        assert len(service.mat_color_history(work.id)) == history
        assert result.outcome is PreparationOutcome.UNCHANGED
