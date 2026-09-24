"""Fixed front-end portrait control-panel rules (notes/mission_selection.md §9.3–9.4)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ControlPanel:
    """One executable control-panel variant, with slots ordered bottom to top."""

    bitmap: str
    labels: tuple[int, ...] = ()
    actions: tuple[str | None, ...] = ()

    @property
    def slot_count(self):
        return len(self.labels)

    @property
    def height(self):
        return 8 + 20 * self.slot_count


# Labels are BRTXT ids. The map's and the encounter windows' actions are traced (notes/activity_results.md §3); unknown
# actions remain deliberately disabled instead of being guessed.
_PANELS = {
    0: ControlPanel("FRAMEBOTTOM"),
    1: ControlPanel("FRAMEPANEL3", (311, 309, 310),
                    ("abort_briefing", "accept_briefing", "toggle_pause")),
    2: ControlPanel("FRAMEPANEL3", (333, 309, 313),
                    ("return_to_caravan", "open_troop_select", "open_briefing")),
    3: ControlPanel("FRAMEPANEL1", (331,), ("encounter_battle",)),
    4: ControlPanel("FRAMEPANEL2", (330, 329), ("encounter_evade", "encounter_attack_status")),
    5: ControlPanel("FRAMEPANEL4", (311, 309, 332, 313)),
    6: ControlPanel("FRAMEPANEL3", (311, 309, 310)),
    7: ControlPanel("FRAMEPANEL3", (338, 309, 313), ("encounter_evade", None, None)),
    8: ControlPanel("FRAMEPANEL1", (329,), ("encounter_battle",)),
    9: ControlPanel("FRAMEPANEL3", (333, 339, 310)),
    10: ControlPanel("FRAMEPANEL3", (333, 309, 313)),
}

PORTRAIT_HEIGHT = 152


def control_panel(value):
    """Return the fixed panel definition for a glue ``controlpanel`` value."""
    return _PANELS.get(value, _PANELS[0])


def portrait_window_height(value, portrait_height=PORTRAIT_HEIGHT):
    """Return the frame height: top/side start + portrait + panel + lower margin."""
    return 12 + portrait_height + control_panel(value).height + 8


def button_y(value, slot, portrait_height=PORTRAIT_HEIGHT):
    """Return a button's y coordinate for a bottom-to-top panel slot."""
    panel = control_panel(value)
    if not 0 <= slot < panel.slot_count:
        raise ValueError(f"panel {value} has no slot {slot}")
    return portrait_window_height(value, portrait_height) - 12 - 20 * (slot + 1)
