# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""The engine's own save games: one JSON file per slot in the engine's save directory.

Not the original ``savegame.N`` RIFF (``notes/save_resume.md``): the engine keeps no save-format
compatibility (``CLAUDE.md``, "saves are the engine's own"). A save holds the *campaign* -- the
explicit fields of :class:`~whshr.campaign_state.CampaignState` plus the company as ``.MRC`` text --
and a load resumes on the start caravan, from where the flow replays up to the saved step. Slots
0-4 are the player's; slot 5 is the automatic "Last Game" slot, listed by the Load dialog only
(``notes/builtin_widgets.md`` section 6). Files are written atomically (temporary file, then rename).
"""

import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from os import PathLike
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import roster
from .glue import MissionRef

if TYPE_CHECKING:
    from .campaign_state import CampaignState

SAVE_VERSION = 1
PLAYER_SLOTS = (0, 1, 2, 3, 4)
AUTOSAVE_SLOT = 5
ALL_SLOTS = PLAYER_SLOTS + (AUTOSAVE_SLOT,)
DESCRIPTION_LIMIT = 25  # notes/builtin_widgets.md section 6: the edit box takes 25 characters


class SaveError(Exception):
    """A slot could not be written or read (missing, damaged, or from a different game version)."""


@dataclass(frozen=True)
class SlotInfo:
    """What the Load/Save dialog shows for an occupied slot."""

    slot: int
    description: str
    saved_at: str  # ISO-8601 UTC


def _ref(mission: MissionRef) -> dict[str, Any]:
    return {"window": mission.window, "record_index": mission.record_index}


def _unref(data: Mapping[str, Any]) -> MissionRef:
    return MissionRef(str(data["window"]), int(data["record_index"]))


def campaign_to_dict(campaign: "CampaignState") -> dict[str, Any]:
    """The persistent part of a campaign as JSON-ready data."""
    order = {regiment.whoami: index for index, regiment in enumerate(campaign.company)}
    return {
        "flow": campaign.flow,
        "flow_history": list(campaign.flow_history),
        "flow_step": campaign.flow_step,
        "mission_window": campaign.mission_window,
        "completed": sorted(campaign.completed),
        "coffers": campaign.coffers,
        "army_units": sorted(campaign.army_units),
        "march_units": sorted(campaign.march_units, key=lambda whoami: order.get(whoami, len(order))),
        "reinforcements": {str(whoami): count for whoami, count in campaign.reinforcements.items()},
        "selected_mission": None if campaign.selected_mission is None else _ref(campaign.selected_mission),
        "taken_missions": [_ref(mission) for mission in sorted(campaign.taken_missions)],
        "book_flags": {str(book): sorted(pages) for book, pages in campaign.book_flags.items()},
        "tentpos": campaign.tentpos,
        "pending_join": sorted(campaign.pending_join),
        "bonus_counter": campaign.bonus_counter,
        "objective_results": {letter: [met, list(values)]
                              for letter, (met, values) in campaign.objective_results.items()},
        "flawless_result": campaign.flawless_result,
        "company": roster.company_text(campaign.company),
    }


def restore_campaign(campaign: "CampaignState", data: Mapping[str, Any]) -> None:
    """Overwrite ``campaign`` (a fresh one for the same installation) with saved ``data``."""
    rows = {regiment.whoami: regiment.row for regiment in (*campaign.master, *campaign.company)}
    try:
        values: dict[str, Any] = {
            "company": roster.parse_company(str(data["company"]), rows),
            "flow": str(data["flow"]),
            "flow_history": [str(name) for name in data["flow_history"]],
            "flow_step": int(data["flow_step"]),
            "mission_window": data["mission_window"],
            "completed": {int(value) for value in data["completed"]},
            "coffers": int(data["coffers"]),
            "army_units": {int(value) for value in data["army_units"]},
            "march_units": {int(value) for value in data["march_units"]},
            "reinforcements": {int(whoami): int(count) for whoami, count in data["reinforcements"].items()},
            "selected_mission": None if data["selected_mission"] is None else _unref(data["selected_mission"]),
            "taken_missions": {_unref(item) for item in data["taken_missions"]},
            "book_flags": {int(book): {int(page) for page in pages} for book, pages in data["book_flags"].items()},
            "tentpos": int(data["tentpos"]),
            "pending_join": {int(value) for value in data["pending_join"]},
            "bonus_counter": int(data["bonus_counter"]),
            "objective_results": {letter: (bool(met), tuple(int(v) for v in values))
                                  for letter, (met, values) in data["objective_results"].items()},
            "flawless_result": bool(data["flawless_result"]),
        }
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise SaveError(f"damaged save: {error!r}") from error
    for name, value in values.items():  # nothing is touched unless the whole save parsed
        setattr(campaign, name, value)
    company = values["company"]
    # Per-mission state that a save between missions never carries.
    campaign.mission_cash, campaign.mission_paid = None, False
    campaign.refresh_speaker([regiment for regiment in company if regiment.whoami in campaign.march_units])


class SaveStore:
    """The slots of one save directory."""

    def __init__(self, save_dir: str | PathLike[str]) -> None:
        self.directory = Path(save_dir)

    def path(self, slot: int) -> Path:
        if slot not in ALL_SLOTS:
            raise ValueError(f"no such save slot: {slot}")
        return self.directory / f"slot{slot}.json"

    def info(self, slot: int) -> SlotInfo | None:
        """The slot's listing, or None when it is empty or unreadable."""
        try:
            data = self._read(slot)
        except SaveError:
            return None
        return SlotInfo(slot, str(data.get("description", "")), str(data.get("saved_at", "")))

    def slots(self) -> dict[int, SlotInfo | None]:
        return {slot: self.info(slot) for slot in ALL_SLOTS}

    def write(self, slot: int, description: str, campaign: "CampaignState") -> None:
        payload = {"version": SAVE_VERSION, "description": description[:DESCRIPTION_LIMIT],
                   "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "campaign": campaign_to_dict(campaign)}
        target = self.path(slot)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            handle, temporary = tempfile.mkstemp(dir=target.parent, prefix=f".slot{slot}.", suffix=".tmp")
            try:
                with os.fdopen(handle, "w", encoding="utf-8") as stream:
                    json.dump(payload, stream, indent=1)
                os.replace(temporary, target)
            except BaseException:
                Path(temporary).unlink(missing_ok=True)
                raise
        except OSError as error:
            raise SaveError(f"cannot write slot {slot}: {error}") from error

    def load_into(self, slot: int, campaign: "CampaignState") -> None:
        restore_campaign(campaign, self._read(slot)["campaign"])

    def _read(self, slot: int) -> dict[str, Any]:
        try:
            data = json.loads(self.path(slot).read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise SaveError(f"slot {slot} is empty") from error
        except (OSError, ValueError) as error:
            raise SaveError(f"slot {slot} is unreadable: {error}") from error
        if not isinstance(data, dict) or data.get("version") != SAVE_VERSION or "campaign" not in data:
            raise SaveError(f"slot {slot} is not a save of this version")
        return data
