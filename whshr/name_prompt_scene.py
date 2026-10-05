"""The New Game commander-name prompt (notes/native-windows.md §7.3.2-§7.3.4).

A modal one-line edit box with no buttons: Enter is OK, Esc is Cancel, and either way the campaign starts
in the start caravan with the main menu's frame still on the context stack. Cancel keeps the default name.
"""

from typing import Any

from .campaign_state import CampaignState
from .glue_content import GlueContent
from .glue_fonts import glue_font_asset
from .glue_scene import GlueScene
from .new_game import NAME_LIMIT, accepts_character
from .scenes import Quit, Scene, SceneAssets, SceneEvent, Transition

MAIN_MENU_WINDOW = "MAINMENU"


class NamePromptScene(Scene):
    def __init__(self, campaign: CampaignState) -> None:
        self.campaign = campaign
        self.default = campaign.commander_name[:NAME_LIMIT]
        self.text = self.default
        self.selected = True  # the pre-filled text is all selected: the first edit replaces it
        self.context: SceneAssets | None = None

    def enter(self, context: SceneAssets) -> None:
        self.context = context

    def font(self, slot: int) -> Any:
        """One glue font slot, loaded through the scene's assets (for the view)."""
        if self.context is None:
            raise RuntimeError("the name prompt has not been entered")
        return self.context.load(glue_font_asset(slot))

    def glue_content(self) -> GlueContent:
        if self.context is None:
            raise RuntimeError("the name prompt has not been entered")
        return self.context.glue_content()

    def _edit(self, text: str) -> None:
        self.text, self.selected = text, False

    def handle(self, event: SceneEvent, context: SceneAssets) -> Transition | Quit | None:
        if not isinstance(event, str):
            return None
        if event.startswith("text:"):
            char = event[5:]
            if accepts_character(char):
                base = "" if self.selected else self.text
                if len(base) < NAME_LIMIT:
                    self._edit(base + char)
            return None
        if event == "edit:backspace":
            self._edit("" if self.selected else self.text[:-1])
            return None
        if event == "ok":
            # An emptied box would leave the leader nameless; keep the default (provisional, §7.3.1 step 6).
            name = self.text.strip()
            if name:
                self.campaign.rename_commander(name)
        elif event != "cancel":
            return None
        return Transition(GlueScene(campaign=self.campaign, window="STARTCARAVAN", parent_window=MAIN_MENU_WINDOW),
                          "new campaign started")
