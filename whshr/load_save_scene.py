# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""The Load / Save dialog (``notes/native-windows.md`` section 8), presentation-independent.

Opened from the main menu (Load) and from a caravan (Save). The dialog shows the six slots (slot 5,
the automatic "Last Game", in Load mode only), one selectable at a time, with OK and Cancel. Saving
asks for a description first (a modal one-line edit box, 24 characters, the New Game name prompt's character filter, the whole
default text pre-selected; the dialog itself is hidden while it is up). The scene keeps no pixels:
the view reads ``mode``, ``slots``, ``selected``, ``editing`` and ``text`` and sends back the events
below.

Events: ``"slot:<n>"``, ``"ok"``, ``"cancel"``, ``"text:<char>"``, ``"edit:backspace"``.

Failures follow the original (section 8.3.8-8.3.9): a failed save shows an error box and the dialog
still closes to its parent; a failed load shows an error box and the game resets to a fresh main menu.
The box is a ``MessageScene`` (OK only). Without a save directory nothing can be listed or written, so
the dialog stays open with its message (the engine's own condition, not in the original).
"""

from collections.abc import Callable
from os import PathLike
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .campaign_scenes import DEFAULT_SEED, MainMenuScene
from .glue_content import GlueContent
from .glue_fonts import glue_font_asset
from .glue_scene import GlueScene
from .new_game import accepts_character
from .savegame import ALL_SLOTS, AUTOSAVE_SLOT, DESCRIPTION_LIMIT, PLAYER_SLOTS, SaveError, SaveStore, SlotInfo
from .message_scene import MessageScene
from .scenes import Scene, SceneAssets, SceneEvent, Transition

if TYPE_CHECKING:
    from .campaign_state import CampaignState

SAVE, LOAD = "save", "load"

# Section 8.4: labels and the default description are string ids of the installation's BRTXT table.
OK_LABEL_ID = {SAVE: 337, LOAD: 336}
CANCEL_LABEL_ID = 307
DEFAULT_DESCRIPTION_ID = 500
STRING_TABLE = "BRTXT"
# PROVISIONAL: the original's literals have no string id (section 8.4); these are the engine's own wording.
# The empty-slot label is the one known verbatim ("-Empty-").
EMPTY_SLOT_LABEL = "-Empty-"
PROMPT_CAPTION = "Enter Save Description"
FALLBACK_DEFAULT_DESCRIPTION = "Saved game"  # only when BRTXT cannot be read (focused tests)
ERROR_CAPTION = "Error"
SAVE_FAILED, LOAD_FAILED = "Save Game Failed.", "Load Game Failed."


def _campaign_from_installation(context: SceneAssets, save_dir: Path) -> "CampaignState":
    """A fresh campaign of the installed game, which a load then overwrites with the saved one."""
    from .campaign_state import CampaignState

    return CampaignState.from_installation(context.locator.installation, context.glue_content())


class LoadSaveScene(Scene):
    def __init__(self, mode: str, parent: Scene, campaign: "CampaignState | None" = None,
                 save_dir: str | PathLike[str] | None = None,
                 new_campaign: "Callable[[SceneAssets, Path], CampaignState] | None" = None) -> None:
        if mode not in (SAVE, LOAD):
            raise ValueError(f"unknown load/save mode: {mode!r}")
        if mode == SAVE and campaign is None:
            raise ValueError("saving needs the campaign to save")
        self.mode = mode
        self.parent = parent
        self.campaign = campaign
        self.save_dir = save_dir
        self.new_campaign = new_campaign or _campaign_from_installation
        self.store: SaveStore | None = None
        self.slots: dict[int, SlotInfo | None] = dict.fromkeys(ALL_SLOTS)
        self.selected: int | None = None
        self.editing = False
        self.text = ""
        self.text_selected = False  # the pre-filled text is all selected: the first edit replaces it
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

    def string(self, identifier: int, fallback: str) -> str:
        """A BRTXT string of the installation, or ``fallback`` when it cannot be read."""
        try:
            return self.glue_content().string(STRING_TABLE, identifier)
        except (KeyError, OSError):
            return fallback

    @property
    def ok_label(self) -> str:
        return self.string(OK_LABEL_ID[self.mode], "OK")

    @property
    def cancel_label(self) -> str:
        return self.string(CANCEL_LABEL_ID, "Cancel")

    @property
    def default_description(self) -> str:
        return self.string(DEFAULT_DESCRIPTION_ID, FALLBACK_DEFAULT_DESCRIPTION)

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
            char = event[5:]
            if accepts_character(char):
                base = "" if self.text_selected else self.text
                if len(base) < DESCRIPTION_LIMIT:
                    self.text, self.text_selected = base + char, False
            return None
        if event == "edit:backspace" and self.editing:
            self.text, self.text_selected = ("" if self.text_selected else self.text[:-1]), False
            return None
        if event == "ok" and self.ok_enabled:
            return self._save(context) if self.mode == SAVE and self.editing else \
                self._load(context) if self.mode == LOAD else self._begin_edit()
        return None

    def _begin_edit(self) -> None:
        assert self.selected is not None
        info = self.slots[self.selected]
        self.text = (info.description if info else self.default_description)[:DESCRIPTION_LIMIT]
        self.editing, self.text_selected, self.error = True, True, ""

    def _save(self, context: SceneAssets) -> Transition | None:
        assert self.store is not None and self.selected is not None and self.campaign is not None
        try:
            # The text is written as typed (section 8.3.6: no trimming, an empty description is allowed).
            self.store.write(self.selected, self.text, self.campaign, self.parent)
        except SaveError as error:
            # Section 8.3.8: an error box, then the dialog closes as after a success.
            return Transition(MessageScene(self.parent, ERROR_CAPTION, f"{SAVE_FAILED} {error}"), "save failed")
        return Transition(self.parent, "game saved")

    def _load(self, context: SceneAssets) -> Transition | None:
        assert self.store is not None and self.selected is not None
        try:
            campaign = self.new_campaign(context, self.store.directory)
            self.store.load_into(self.selected, campaign)
            scene = self.store.load_scene(self.selected, campaign, context.glue_content())
        except SaveError as error:
            # Section 8.3.9: an error box, then the game resets to the main menu.
            menu = MainMenuScene(log_dir=getattr(self.parent, "log_dir", None),
                                 seed=getattr(self.parent, "seed", DEFAULT_SEED))
            return Transition(MessageScene(menu, ERROR_CAPTION, f"{LOAD_FAILED} {error}"), "load failed")
        # A save with no scene chain (an older one) resumes on the start caravan.
        return Transition(scene or GlueScene(campaign=campaign, window="STARTCARAVAN"), "game loaded")
