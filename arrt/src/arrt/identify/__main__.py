"""Match the catalogue's works and artists to Wikidata: `uv run python -m arrt.identify`.

Hand-run, like the seed command, and for the same reason its report goes to
stdout: the point of running it is to read what it found. It fills only
identities nobody has set, so running it again is safe and writes nothing new
unless the catalogue or the registry has changed. Stop the server first: both
would write the same file.
"""

import argparse
import logging
import sys

from arrt import logs
from arrt.config import Settings
from arrt.library.registry import RegistryUnavailable
from arrt.library.registry.wikidata import WikidataRegistry
from arrt.library.services.identity import IdentityReport, IdentityService
from arrt.persistence.file import open_catalogue_file
from arrt.persistence.sqlite import SqliteCatalogue


def main(argv: list[str] | None = None) -> int:
    """Match, then print what happened."""
    logs.configure(level=logging.INFO)
    parser = argparse.ArgumentParser(prog="python -m arrt.identify", description=__doc__.splitlines()[0])
    parser.parse_args(argv)

    settings = Settings.from_env()
    if not settings.wikidata_user_agent:
        print(  # noqa: T201 -- the report is this tool's output
            "WIKIDATA_USER_AGENT is not set, so nothing was matched. Wikidata asks callers to name themselves "
            "and give a contact; set it in .env (see .env.example) and run this again.",
            file=sys.stderr,
        )
        return 2

    registry = WikidataRegistry(user_agent=settings.wikidata_user_agent)
    catalogue_file = open_catalogue_file(settings.catalogue_path, wall_name=settings.wall_name)
    try:
        report = IdentityService(SqliteCatalogue(catalogue_file), registry).match()
    except RegistryUnavailable as exc:
        # Nothing half-written to explain: works are written in one transaction
        # after every answer is in, and each artist is written once decided.
        print(  # noqa: T201 -- a hand-run command; its operator reads stderr
            f"Wikidata could not be asked: {exc} What was matched before this stands.", file=sys.stderr
        )
        return 1
    finally:
        catalogue_file.close()
        registry.close()

    for line in render(report):
        print(line)  # noqa: T201 -- the report is this tool's output
    return 0


def render(report: IdentityReport) -> list[str]:
    """The report as a person reads it: what was found, then what needs a hand."""
    lines = [
        (
            f"Works: {report.works_matched} matched, {len(report.works_ambiguous)} ambiguous, "
            f"{report.works_unknown} not on Wikidata, {report.works_without_identifier} with no museum identifier."
        ),
        (
            f"Artists: {report.artists_matched} matched, {len(report.artists_ambiguous)} ambiguous, "
            f"{len(report.artists_undated)} undated, {len(report.artists_unknown)} not found."
        ),
    ]
    for heading, names in (
        ("Works whose sources name more than one item (set by hand: art_catalogue set_work_qid)", report.works_ambiguous),
        ("Artists with several candidates left (set by hand: art_catalogue set_artist_qid)", report.artists_ambiguous),
        ("Artists with no birth or death year, so a name alone could not be trusted", report.artists_undated),
    ):
        if names:
            lines.append(f"{heading}:")
            lines.extend(f"  {name}" for name in names)
    return lines


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
