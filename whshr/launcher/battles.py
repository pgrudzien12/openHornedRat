"""Lists the playable battles of a recognized installation for the launcher's battle picker."""

from dataclasses import dataclass
from typing import Optional

from whshr import script


@dataclass(frozen=True)
class BattleEntry:
    id: str
    map: Optional[str]


def list_battles(installation):
    """Every ``.BTS`` under SCRIPT that is an actual battle (has a ``loadScript``), not a plot file."""
    entries = []
    for path in sorted(installation.file_dir("SCRIPT").iterdir()):
        if path.suffix.upper() != ".BTS":
            continue
        data = script.load_battle(str(path), with_merc=False)
        if data["field"]["script"] is None:
            continue
        entries.append(BattleEntry(id=path.stem, map=data["field"]["map"]))
    return entries
