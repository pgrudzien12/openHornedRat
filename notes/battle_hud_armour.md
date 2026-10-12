# Battle HUD armour artwork

The battle information panel uses **ICONS frames 218–223**, not the six legacy
`ICON2` armour images. Frame indices below are zero-based. The installed
`ICONS.FOL` / `ICONS.BOP` / `ICONS.PAL` supply the artwork; use the normal UI
palette decoding. All seven frames 218–224 are 44×51 pixels.

The frame mapping and panel geometry are established; the decoded artwork was
visually checked. 🟡 A matching capture of the original running game has not been
made, including the two-column crop described below.

## 1. Armour code to frame

Read the displayed subject's current `s_armr` code, separately for troops and
leader. This is an artwork mapping, not a conversion from the combat saving
throw. The armour and save meanings remain those in
[game_rules.md, Armour saves](game_rules.md#armour-saves-).

| `s_armr` code | Documented meaning | ICONS frame | Visual identification |
|---:|---|---:|---|
| 0 | Foot rating 0 | 218 | Brown tunic |
| 1 | Foot rating 1 | 219 | Wooden round shield, metal rim |
| 2 | Foot rating 2 | 220 | Wooden round shield with metal boss |
| 3 | Foot rating 3 | 221 | Metal round shield |
| 4 | Foot rating 4 | 222 | Plain metal pointed shield |
| 5 | Foot rating 5 | 223 | Decorated metal pointed shield |
| 6 | Regeneration | 223 | Same decorated shield |
| 7 | Void/reserved | 223 | Same decorated shield |
| 8 | Mounted rating 1 | 218 | Brown tunic |
| 9 | Mounted rating 2 | 219 | Wooden round shield, metal rim |
| 10 | Mounted rating 3 | 220 | Wooden round shield with metal boss |
| 11 | Mounted rating 4 | 221 | Metal round shield |
| 12 | Mounted rating 5 | 222 | Plain metal pointed shield |
| 13 | Mounted rating 6 | 223 | Decorated metal pointed shield |
| 14–15 | No established gameplay meaning | 223 | Same decorated shield |
| No selected unit | Empty readout | 224 | Blank parchment tile |

Codes 8–13 deliberately reuse the images for codes 0–5, respectively. Do not add
an extra artwork step for a mount or select an image from the save threshold.
In particular, code 5 still shows the decorated shield despite its anomalous
combat save; code 6 has no dedicated regeneration picture. Codes 7 and 14–15
are included as display boundary cases, not claims that campaign units use them.

## 2. Placement

Coordinates are unscaled pixels in the original 640×480 client area, measured
from each named area's top-left corner.

| Area | Origin | Size |
|---|---|---|
| Bottom command panel, relative to screen | (0, 304) | 640×176 |
| Information panel, relative to command panel | (197, 62) | 246×114 |
| Armour image, relative to information panel | (7, 54) | 42×51 destination |
| Armour image, relative to command panel | (204, 116) | 42×51 destination |
| Armour image, relative to screen | **(204, 420)** | **42×51 destination** |

Copy the top-left 42×51 pixels of the chosen 44×51 frame at native size: source
columns 0–41, rows 0–50. The rightmost two source columns are excluded. This is
not a 44-to-42 horizontal rescale, a centred crop, or sprite-anchor positioning.
The same rectangle is used for the blank frame 224. The information-panel
background is restored from the matching region of ICONS frame 98 before its
contents are drawn, so switching images does not retain previous pixels.

## 3. Subject and timing

The information panel's unit/leader view determines the armour source. Unit
view uses troop armour; leader view uses leader armour. Switching view redraws
the image immediately with the new subject's code. It changes display state,
not either armour value, mount status, equipment, or combat save.

The two alternate view buttons use ICONS 64/65 (helmet, switch to unit view) and
66/67 (masked head, switch to leader view). Their position (140, 4) is relative
to the **information panel**, hence screen (337, 370); they are not message-log
buttons. In unit view the leader button is available; in leader view the unit
button is available. A repaint reads current armour rather than caching the
frame chosen at initial selection. There is no armour animation or turn delay.

A leader must be present and have a portrait identity for leader view to be
available. If that is not the case, the readout uses troop armour and hides both
view buttons. With exactly one remaining figure, it uses leader armour if that
leader is available, otherwise troop armour; both view buttons are hidden.
Enemy selection uses troop armour and hides the unit/leader buttons. With no
selection, use frame 224 and hide both buttons. This specification applies while
the information panel is visible; spell/item panes can occupy its area instead.

## 4. Before / action / after vectors

These are specification test vectors, not original-runtime screenshots. Unless
specified otherwise, use a friendly unit with multiple figures and an available
leader. Every listed image occupies screen (204, 420), cropped to 42×51.

| Before state | Action | After state |
|---|---|---|
| Unit view; troops 1, leader 4; frame 219 | Switch to leader | Leader view, frame 222; armour values remain 1 and 4 |
| Leader view; troops 1, leader 4; frame 222 | Switch to unit | Unit view, frame 219 |
| Unit view; troops 10, leader 13; frame 220 | Switch to leader | Leader view, frame 223 |
| Leader view; troops 10, leader 13; frame 223 | Switch to unit | Unit view, frame 220 |
| Unit view; troops 8, leader 9; frame 218 | Switch to leader | Leader view, frame 219 |
| Unit view; troops 5, leader 6; frame 223 | Switch to leader | Leader view, still frame 223 despite different save semantics |
| Unit view; troops 0, leader 0; frame 218 | Switch to leader | Leader view, still frame 218 |
| Leader view; leader code changes from 4 to 5 | Repaint information panel | Frame 222 becomes 223 |
| Leader preferred; troops 2; leader unavailable | Refresh selected unit | Unit view, frame 220, no view buttons |
| Troops 2, leader 4; exactly one figure and leader available | Refresh selected unit | Leader view, frame 222, no view buttons |
| Leader view preferred; enemy troops 3, leader 5 | Select enemy | Troop frame 221, no view buttons |
| Any selected unit and armour image | Clear selection and repaint | Blank frame 224 replaces previous image |

## 5. Corrections and implementation hand-off

The implementer's separate troop/leader armour values are sufficient: select the
appropriate value by readout subject, then use section 1. No new armour model or
legacy resource loader is needed.

The older statement in `btp_sprite_leftovers.md` that armour icons are missing
from `ICONS` was misleading: its particular legacy pictures differ, but the live
sheet has the replacement artwork at 218–223. `sprite_names.md` now points here.
The older HUD description in `game_rules.md` omitted the information panel and
placed its view toggles in the message area; the table is corrected there.

🟡 Remaining verification: compare an original-game screenshot in unit and leader
view, particularly the native two-column crop. No claim is made here about the
exact latency of an armour-changing spell or item triggering a panel repaint.
