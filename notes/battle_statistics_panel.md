# Battle statistics panel

## Visual reference

The user-provided original-game screenshot and description (2026-10-12) establish:

- The bottom centre panel has unit and leader modes, switched by the head button beside the name.
- Unit mode shows the troop profile, banner, and armour artwork.
- Leader mode shows the leader profile and portrait in place of the banner.
- The nine characteristics are arranged M/WS/BS, S/T/W, I/A/Ld.
- The compass/reaction portrait at the left is independent of these modes.
- Portrait status overlays are outside this implementation's scope.

Banner frame 0 is documented in `sprite_names.md`. The existing portrait renderer uses
portrait frame 0 as its base. The panel uses the existing ICONS background and toggle
frames 64–67 (`game_rules.md`, Battle HUD layout).

## Implementation choices and remaining facts

Positions are measured from the reference and need an in-game visual check. The unit/leader
art occupies a 72×104 box at panel-local (369,68). The profile starts at (253,117),
with columns 38 pixels apart and rows 19 pixels apart.

The engine defaults to unit mode and resets it when selection changes. This is an engine
UI choice; the original's persistence across selection changes is not established.
Missing profile values display a dash. Values come from the selected troop or leader
profile; tabletop M is retained separately from simulation movement speed. The existing
class label and current/initial model count remain on the second unit-information line;
the exact weapon text shown in the reference is not reproduced yet.

Armour artwork and subject eligibility now follow `battle_hud_armour.md` §§1–4:
ICONS 218–223 map the troop/leader armour code, and 224 clears an empty selection.
The 44×51 source is cropped to its leftmost 42 columns at panel-local (204,116).
Repaints use current armour; cached textures contain only artwork. The whole panel
background is drawn first, preventing stale pixels after a subject switch.

Leader view requires a living leader and portrait identity. Enemy units show troop
information. A lone available leader is shown automatically. Both toggles are hidden
for these forced views and for empty selection. Names, profiles, portraits and armour
share the same effective subject. The preference still resets on selection changes.
Original-game screenshot comparison remains outstanding, as noted in the report.
