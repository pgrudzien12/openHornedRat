# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""The Load / Save dialog (``notes/builtin_widgets.md`` section 6), presentation-independent.

Opened from the main menu (Load) and from a caravan (Save). The dialog shows the six slots (slot 5,
the automatic "Last Game", in Load mode only), one selectable at a time, with OK and Cancel. Saving
asks for a description first (a modal one-line edit box, 25 characters). The scene keeps no pixels:
the view reads ``mode``, ``slots``, ``selected``, ``editing`` and ``text`` and sends back the events
below.

Events: ``"slot:<n>"``, ``"ok"``, ``"cancel"``, ``"text:<char>"``, ``"edit:backspace"``.

Deviations from the original, both kinder to the player: a failed load or save keeps the dialog open
with a message instead of resetting to the main menu (load) or closing (save).
"""

from collections.abc import Callable
from os import PathLike
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .glue_content import GlueContent
from .glue_fonts import glue_font_asset
from .glue import MissionRef
from .glue_scene import GlueScene
from .savegame import ALL_SLOTS, AUTOSAVE_SLOT, DESCRIPTION_LIMIT, PLAYER_SLOTS, SaveError, SaveStore, SlotInfo
from .scenes import Scene, SceneAssets, SceneEvent, Transition

if TYPE_CHECKING:
    from .campaign_state import CampaignState

SAVE, LOAD = "save", "load"

# PROVISIONAL: the original's captions come from a native dialog that is not in any string table
# (notes/builtin_widgets.md section 6, open item 6); the engine supplies its own.
DEFAULT_DESCRIPTION = "Saved game"
EMPTY_SLOT_LABEL = "Empty"
PROMPT_CAPTION = "Enter Save Description"


def _campaign_from_installation(context: SceneAssets, save_dir: Path) -> "CampaignState":
    """A fresh campaign of the installed game, which a load then overwrites with the saved one."""
    from .campaign_state import CampaignState

    return CampaignState.from_installation(context.locator.installation, context.glue_content(), save_dir=save_dir)


class LoadSaveScene(Scene):
    def __init__(self, mode: str, parent: Scene, campaign: "CampaignState | None" = None,
                 save_dir: str | PathLike[str] | None = None,
                 new_campaign: "Callable[[SceneAssets, Path], CampaignState] | None" = None,
                 release: MissionRef | None = None, unavailable: str = "") -> None:
        if mode not in (SAVE, LOAD):
            raise ValueError(f"unknown load/save mode: {mode!r}")
        if mode == SAVE and campaign is None:
            raise ValueError("saving needs the campaign to save")
        self.mode = mode
        self.parent = parent
        self.campaign = campaign
        self.save_dir = save_dir
        self.release = release  # a finished mission whose caravan is open: saved as already released
        self.unavailable = unavailable  # why saving is refused right now (the dialog opens disabled)
        self.new_campaign = new_campaign or _campaign_from_installation
        self.store: SaveStore | None = None
        self.slots: dict[int, SlotInfo | None] = dict.fromkeys(ALL_SLOTS)
        self.selected: int | None = None
        self.editing = False
        self.text = ""
        self.error = ""
        self.context: SceneAssets | None = None

    def font(self, slot: int) -> Any:
        """One glue font slot, loaded through the scene's assets (for the view)."""
        if self.context is None:
            raise RuntimeError("the load/save scene has not been entered")
        return self.context.load(glue_font_asset(slot))

    def glue_content(self) -> GlueContent:
        if self.context is None:
            raise RuntimeError("the load/save scene has not been entered")
        return self.context.glue_content()

    @property
    def visible_slots(self) -> tuple[int, ...]:
        """Slot 5 is the automatic save: the player can only load it (section 6)."""
        return PLAYER_SLOTS + ((AUTOSAVE_SLOT,) if self.mode == LOAD else ())

    @property
    def ok_enabled(self) -> bool:
        """OK needs a selected slot; in Load mode the slot must hold a save; a text prompt is always confirmable."""
        if self.store is None:
            return False
        if self.editing:
            return True
        if self.selected is None:
            return False
        return self.mode == SAVE or self.slots[self.selected] is not None

    def enter(self, context: SceneAssets) -> None:
        self.context = context
        if self.unavailable:
            self.store, self.error = None, self.unavailable
            return
        save_dir = self.save_dir if self.save_dir is not None else context.save_dir
        if save_dir is None:
            self.store, self.error = None, "No save directory is configured."
            return
        self.store = SaveStore(save_dir)
        self._refresh()

    def _refresh(self) -> None:
        if self.store is not None:
            self.slots = self.store.slots()

    def handle(self, event: SceneEvent, context: SceneAssets) -> Transition | None:
        if not isinstance(event, str):
            return None
        if event == "cancel":
            if self.editing:  # cancelling the edit box returns to the dialog
                self.editing = False
                return None
            return Transition(self.parent, "load/save dialog closed")
        if self.store is None:
            return None
        if event.startswith("slot:") and not self.editing:
            slot = int(event[5:])
            if slot in self.visible_slots:
                self.selected, self.error = slot, ""
            return None
        if event.startswith("text:") and self.editing:
            self.text = (self.text + event[5:])[:DESCRIPTION_LIMIT]
            return None
        if event == "edit:backspace" and self.editing:
            self.text = self.text[:-1]
            return None
        if event == "ok" and self.ok_enabled:
            return self._save(context) if self.mode == SAVE and self.editing else \
                self._load(context) if self.mode == LOAD else self._begin_edit()
        return None

    def _begin_edit(self) -> None:
        assert self.selected is not None
        info = self.slots[self.selected]
        self.text = (info.description if info else DEFAULT_DESCRIPTION)[:DESCRIPTION_LIMIT]
        self.editing, self.error = True, ""

    def _save(self, context: SceneAssets) -> Transition | None:
        assert self.store is not None and self.selected is not None and self.campaign is not None
        try:
            self.store.write(self.selected, self.text.strip() or DEFAULT_DESCRIPTION, self.campaign, self.release)
        except SaveError as error:
            self.error, self.editing = str(error), False
            return None
        return Transition(self.parent, "game saved")

    def _load(self, context: SceneAssets) -> Transition | None:
        assert self.store is not None and self.selected is not None
        try:
            campaign = self.new_campaign(context, self.store.directory)
            self.store.load_into(self.selected, campaign)
        except SaveError as error:
            self.error = str(error)
            return None
        return Transition(GlueScene(campaign=campaign, window="STARTCARAVAN"), "game loaded")
