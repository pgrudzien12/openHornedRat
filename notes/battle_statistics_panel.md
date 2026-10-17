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
art occupies a 72×104 box at panel-local (369,68).

The nine characteristics sit on small parchment cells. These come from **ICONS frame 211**, a
118×60 3×3 grid, and not from the ICONS 98 background, which has only the bare plate under them.
Drawn at panel-local (250,112), the frame's border lines up with that plate. Its cells are
32×13, the first at frame-local (5,4), with columns 38 pixels apart and rows 19 apart. Each
value is drawn one pixel inside its cell, starting at panel-local (256,117). The engine also
draws the empty grid when nothing is selected, next to the blank armour tile. That is an
engine choice: the original's empty-selection panel has not been observed.

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

## Unit-information text block ✅ (static; 🟡 no capture of the running original)

Answers the implementer's questions about the text left of the unit/leader head toggle. Coordinates are relative to
the bottom command panel (screen (0,304)). The information panel's origin is (197,62)
(`battle_hud_armour.md` §2).

### Layout

- **Block**: 129×36 at (204,71): panel-local (7,9) of the information panel.
- **Text rectangle**: inset 2 px left, 1 px top, and 2 px narrower: x 206…333. One line tall; it moves down one
  line pitch per line.
- **Font**: the battle's second font, `PCTEXTA.FON` ("WarhammerA", 12 px, no external leading). Line pitch
  **H = 12**, so line tops sit at y = **72, 84, 96**: exactly three lines.
- **Alignment**: names and the weapon are left-aligned. The model count is right-aligned to x = 333, **on the same
  line as the weapon**.
- **Long text**: no wrapping and no ellipsis. A line longer than 127 px is clipped at the rectangle's right edge.
  The count is drawn over the right end of the weapon line, so a long weapon name and the count can overlap.
- **Colour**: transparent background. The painter sets no colour, so text uses the panel's default text colour,
  black 🟡.
- **Line break**: a `<` in a name is the line break (`Grudgebringer<Cavalry` → two lines). `_` shows as a space,
  as in every name display (`FORMATS.md`; 🟡 assumed converted when the army file is read, since the painter does
  not touch it).

### Lines per mode

| Mode | Line 1 (y 72) | Line 2 (y 84) | Line 3 (y 96) |
|---|---|---|---|
| unit, name without `<` | unit name | troop weapon name · count at right | — |
| unit, name with `<` | name before `<` | name after `<` | troop weapon name · count at right |
| leader, name without `<` | leader name | (empty) | **leader's** weapon name · count at right |
| leader, name with `<` | before `<` | after `<` | leader's weapon name · count at right |
| no subject (empty selection) | — | — | — (only the blank armour tile 224) |

### Data sources

- **Unit name**: the unit's `addunit:` name (army or battle file).
- **Leader name**: the unit's `addleader:` name.
- **Weapon name**: string `BRTXT 200 + s_weponame` (`game_rules.md` token 38). Unit mode uses the troop block's
  value, leader mode the leader block's. If that string id does not exist, the weapon text is skipped, and the count
  is still drawn. Melee-only units show whatever their `s_weponame` names: e.g. a lance on Reiksguard, a halberd, a
  spear (`game_rules.md`'s list of checked names). The text does not come from `s_weap` (the weapon class) or from
  `S_BalWeap`. No mount, item, rank, experience or status text appears.
- **Count**: `"%d/%d"` = current models (`s_size`) / original models (`s_orgsize`) of the **unit**, in both modes.
  Routed models are not added. Example from `game_rules.md`: Mercenary Crossbows: "Crossbow" with "12/12".

### Which mode is shown

| Selected unit | Mode |
|---|---|
| none | nothing (blank armour only) |
| enemy | unit mode forced, toggle hidden. The player's mode choice is saved and restored on the next friendly selection |
| one model, has a leader model with a portrait (wizard, hero, single monster with a leader block) | leader mode forced, toggle hidden |
| one model, no leader/portrait | unit mode forced, toggle hidden |
| several models, leader with portrait | the player's choice: the head buttons set unit or leader mode |
| several models, no leader/portrait | unit mode forced, toggle hidden |

**Correction of the engine choice above:** the original keeps the player's unit/leader choice **across selections**,
re-applying it to each newly selected unit whenever that unit allows it. It does not reset to unit mode.

### Refresh

The block is repainted:

- when the selection changes;
- when a head button is pressed (immediately);
- during the battle tick, in the focused unit's own step (`battle_tick_order.md` §2.2 step 7): its model count or
  one of its displayed states has changed (charging, in melee, broken, pursuing, hidden, and similar). So
  casualties update the count in the tick in which the model is removed.

The same panel runs in deployment, and the deployment selection uses the same rules.

### Vectors

| Before | Action | After (lines at y 72 / 84 / 96) |
|---|---|---|
| select Grudgebringer Cavalry (`Grudgebringer<Cavalry`), unit mode, 16 of 16 | paint | `Grudgebringer` / `Cavalry` / `<BRTXT 200+w>` … `16/16` |
| select Vannheim's 75th (`Vannheim's_75th`), unit mode | paint | `Vannheim's 75th` / `<BRTXT 200+w>` … `18/18` / — |
| same unit, leader mode (`Siegfried_Vannheim`) | press the leader head | `Siegfried Vannheim` / (empty) / `<BRTXT 200+leader w>` … `18/18` |
| the unit loses 2 models | tick of removal | count becomes `16/18` |
| select a one-model wizard with a leader portrait | paint | leader mode forced: wizard's leader name, leader weapon, `1/1` |
| select an enemy unit after a friendly unit in leader mode | paint; then select the friendly unit again | enemy: unit mode; friendly: leader mode again |
| `s_weponame` with no string | paint | weapon text skipped; the count still at the right of that line |
| nothing selected | paint | no text; blank armour tile |

Note: the art box (banner/portrait) is 72×104 at (368,67) from the panel geometry. The section above measured
(369,68) from the screenshot. 🟡 Use (368,67).
