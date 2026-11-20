"""`DisplaySettings`: where this installation keeps each wall's files, and the pace a wall inherits.

Its own module so that the collaborators
`display.py` composes (`feeds.py`, `walls.py`, `scenes.py`, `reports.py`) import
it at run time without importing the facade that builds them. `display.py`
re-exports it, so `from arrt.programming.display import DisplaySettings` names
this same class (`__main__.py`, `services/container.py`).
"""

from dataclasses import dataclass
from pathlib import Path

from arrt.programming.manifest.heartbeat import heartbeat_path_in
from arrt.programming.manifest.v2 import manifest_v2_path_in


@dataclass(frozen=True, slots=True)
class DisplaySettings:
    """The deployment facts the walls' operations need.

    **Named for the service rather than for a wall**, because a wall is now a
    first-class entity with a name and an id: a type called `WallSettings` beside
    `Services.bind(wall=…)` read as though the container were being handed a
    wall, when what it is handed is where this installation publishes and the
    pace a theme inherits when it has expressed none of its own.

    Passed in rather than read from the environment here, because a service that
    resolved its own configuration could not be tested against two deployments
    and would make every caller share one.
    """

    #: The art root, where this server keeps each wall's feed and heartbeat. They
    #: are named from it **per wall**, so this holds the root and not a file: the catalogue
    #: names as many walls as the curator has rooms, and each one has its own
    #: pair of files.
    art_root: Path
    #: What a wall that has chosen no pace of its own plays at.
    rotation_interval_seconds: int
    shuffle: bool

    def manifest_v2_path(self, wall_id: str) -> Path:
        """Where this server publishes one wall's feed."""
        return manifest_v2_path_in(self.art_root, wall_id)

    def heartbeat_path(self, wall_id: str) -> Path:
        """Where one wall's last heartbeat is kept: written by `record_heartbeat`, from what its Player POSTs."""
        return heartbeat_path_in(self.art_root, wall_id)
