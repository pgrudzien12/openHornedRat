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

Armour artwork is not implemented. Existing public notes identify six legacy ICON2
armour images, but do not provide the battle resource/frame mapping for armour codes.
A separate researcher report is needed with resource, frame, panel position, and code
mapping (including mounted codes). Useful vectors: unit armour 0/1/2/5/8/13, toggle
between different troop and leader armour, and select a unit without a leader. For each,
report before-state, action, and visible after-state. Do not infer armour save semantics
from the shield visible in the screenshot.
