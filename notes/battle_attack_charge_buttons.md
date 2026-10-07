# Battle command buttons while attacking and charging

This note distinguishes **choosing an Attack order**, **approaching its target**,
**charging**, and **fighting in close combat**. The command panel layout and fixed
controls are described in [game_rules.md, Battle HUD layout](game_rules.md#battle-hud-layout-).
These rules concern the five unit-command slots at the right of the battle panel.
Camera, pause/menu, options, regiment cycling, and minimap controls remain present
while a unit charges or fights.

The five slots are top left (TL), top right (TR), bottom right (BR), bottom left
(BL), and centre (C). A dash means that no button is drawn there. **Items** appears
only if the regiment has items and a living leader figure; see
[battlefield_items.md](battlefield_items.md).

## Attack order: before and after the target click

Pressing **Attack** arms the attack cursor and opens an attack command set. The
next battlefield click chooses a target for the Attack order. This set is a panel
for choosing related commands; it is **not** the panel state of a regiment already
fighting.

| Unit class | TL | TR | BR | BL | C |
|---|---|---|---|---|---|
| Infantry, cavalry, wizard, or monster; items and leader | Charge | — | Items | — | Back |
| Infantry, cavalry, wizard, or monster; no available Items command | Charge | — | — | — | Back |
| Archers; items and leader | Charge | Fire | Items | Halt | Back |
| Archers; no available Items command | Charge | Fire | — | Halt | Back |
| Artillery; items and leader | — | Fire | Items | Halt | Back |
| Artillery; no available Items command | — | Fire | — | Halt | Back |

After a target click, the attack sub-panel closes. While the regiment walks
toward that target **without yet charging or fighting**, its five unit-command
slots show the ordinary idle set:

| Unit class | TL | TR | BR | BL | C |
|---|---|---|---|---|---|
| Infantry, cavalry, archers, monster | Move | Attack | Independent | — | — |
| Artillery | — | Attack | Independent | — | — |
| Wizard | Move | Attack | Independent | Magic | Back |

The Attack order follows and periodically checks the target. When the target
comes into charge reach, the regiment can start a charge; that **state change**
changes the command set. The mere presence of an attack target does not itself
hide the idle buttons. A direct **Charge** command also starts a charge without
first requiring an Attack target.

## While charging

For every ordinary player-commandable unit class, **all five unit-command slots
are empty while its charging state is active**. This includes Back, Halt, Items,
Magic, Fire, Attack, Withdraw, and Fight harder: none is drawn as a unit-command
button during the charge. The charge takes precedence over the melee, braced,
broken, and pursuit panel choices. The selected regiment and the fixed battle
controls can still be displayed.

When the charge ends, the unit-command set is chosen again from the unit's new
state. Contact that produces close combat gives the melee set below; a charge
that ends without combat returns to the applicable idle, broken, or pursuit set.

## While fighting in close combat

Once the unit is **in melee**, the five slots are:

| Unit class | TL | TR | BR | BL | C |
|---|---|---|---|---|---|
| Infantry, cavalry, archers, artillery, monster; items and leader | — | Withdraw | Items | — | Fight harder |
| Infantry, cavalry, archers, artillery, monster; no available Items command | — | Withdraw | — | — | Fight harder |
| Wizard; items and leader | — | Withdraw | Items | Magic | Fight harder |
| Wizard; no available Items command | — | Withdraw | — | Magic | Fight harder |

The panel uses this same set for a **braced** unit, even if it has not made
contact. A visible command is not a promise that its order will succeed:
Withdraw against a living enemy causes a voluntary rout, while item use and
magic have their own checks. The melee set has no Move, Attack, Charge, Halt,
Independent, or Back button.

## Before / action / after examples

| Before | Action | After |
|---|---|---|
| Infantry regiment idle, no items | Press Attack. | Attack cursor armed; Charge at TL and Back at C; the other three unit-command slots are empty. |
| Same regiment, enemy still beyond charge reach | Click that enemy. | Attack order accepted; the regiment approaches; the idle set shows Move, Attack, Independent. |
| Approaching infantry has reached charge range and starts its charge | Advance the battle. | All five unit-command slots become empty for the duration of the charge. The fixed battle controls remain. |
| Charging infantry makes contact and enters close combat | Advance the battle. | Withdraw appears at TR and Fight harder at C; no Move, Attack, or Charge button appears. |
| Wizard in melee, with an item and a living leader | Inspect the unit commands. | Withdraw at TR, Items at BR, Magic at BL, Fight harder at C. |
| Wizard in melee loses its leader but survives | Inspect the unit commands again. | Items is absent; Withdraw, Magic, and Fight harder remain. |
| Unit is braced against an approaching enemy but not yet in contact | Inspect the unit commands. | The melee-style Withdraw / Fight harder set is shown (plus Items or Magic where applicable). |

The state sequence matters: **Attack selected → approach → charge → melee** can
show four different command sets for the same regiment.
