# Player Magic order and spell panel (from the Magic button to event 0x2B)

Public implementation report (behaviour only), answering the implementer's request: the battle HUD's Magic button
and spell list, the power display, and every path from a click to the cast order. Companions, cited rather than
repeated: `game_rules.md` "Winds of magic and casting" (costs, pool, winds), "Player orders" (order 0x17);
`spell_lasting_effects.md` §0.2, §5.4, §8 (entry states **selected / cast ordered / active**, Dispel once per battle);
`script_magic.md` §4 (`TakeSpellEventTarget`, the cast order); `script_grid_events.md` (events 0x28–0x2F);
`battlefield_items.md` (the item list in the same rectangle); `battle_attack_charge_buttons.md` (panel sets);
`react_portrait.md` (the compass/portrait rectangle); `player_missile_orders.md` §5 (order picking, minimap).

## 0. Shared state (read this first)

| state | meaning |
|---|---|
| **list area** | the rectangle at (200, 64) of the panel (`game_rules.md` "Player orders"). It shows exactly one of: the selected unit's **info card** (default), its **spell list**, or its **item list**. Showing one hides the others. |
| **pending order mode** | one per battle screen: none, Move, Attack, Fire, Face, or **Magic**. Magic mode carries a **pending spell**, either a spell code or **none** ("wand without a spell", §3). It sets the wand cursor (`GMCUR` 103); leaving the mode restores the default cursor. |
| **spell entry states** | per entry of the selected wizard's spell list: **selected**, **cast ordered**, **active** (`spell_lasting_effects.md` §0.2). **Usable** = not selected **and** cost ≤ the **player** pool. Active does **not** make a spell row unusable (unlike item rows). |
| **focused unit** | the selected unit whose panel is shown. **The Magic order is applied only to the focused unit**, even when several units are selected. |
| **player pool** | 0–8 (`game_rules.md`). Every spell row and the compass display read the player's pool. |

**Cost is paid on the row click**, never at the target click (except Ctrl re-orders, §4.3). **Nothing ever refunds
it.** Every cancel path below only clears **selected**.

## 1. Q1: the Magic button and the spell list

**Who has it (Q3).** The Magic button is part of the **Wizard-class** panel sets only: the idle set (BL slot) and the
melee set (`battle_attack_charge_buttons.md`). It is not in the broken/pursuing set, it is not shown while charging
(empty set), and it is not shown during deployment. A leader that merely carries the casting weapon (the Orc shaman
on a Wyvern, Monster class) has **no** Magic button: only the AI casts with such units. The button is shown whatever
the spell list holds; with no spells the list is just empty.

While the focused wizard is **casting** (`IfCasting` sense: a spell pending or being channelled), its command slots
are **empty**, both when it is selected and from the target click on (§4.2). The usual set returns when the cast is
resolved (launch, failure or refusal). 🟡 The exact refresh moment is not traced; re-selecting the unit always
recomputes it.

**Pressing Magic** (left click, no Ctrl):

| before | press Magic | after |
|---|---|---|
| list area shows the info card or the item list | Magic | the **spell list** of the focused wizard is shown. Showing it clears **selected** on the *item* list (no refund). Rows are refreshed (§1.1). Pending mode is cleared; the cursor is unchanged. |
| list area already shows the spell list | Magic | the list stays. Every **selected** spell row is cleared (no refund). The mode becomes **Magic with no spell**, with the wand cursor (§3). |

So Magic is **not** a toggle that closes the list. To leave the spell list, press another command (Move, Attack,
Fire, Items, …) or Back (§5). **Items** works the same way, except that pressing Items while the item list is
showing goes back to the info card (clearing selected in both lists).

### 1.1 Rows

- **Up to 5 rows**, one per entry of the unit's spell list (the `.BTS`/`.MRC` `addspell:` lines), **in file order**.
  Rows sit at the same positions as item rows (`battlefield_items.md`: x 5, y 8/27/46/65/84 inside the area,
  232 × 18). Unfilled rows show the list background.
- **Background**: the raised row frame when usable, the muted frame when not usable *and* while the mouse button is
  held on it (ICONS 207 / 206, as for items).
- **Text**: the spell's name from **`GMTXT`** (string id = the spell's id in the spell/item table,
  `game_rules.md`: 30004 Wind Blast, 30005 Azure Blades, …, 30019 Dispel Magic, …). Spell rows draw the name in a
  text box about 190 px wide starting 5 px into the row, then the **cost as a plain number** (`%d`) in a 20 px box
  after it. Item rows draw only the name (wider box), no cost.
- **Status marks** (ICONS frames, as for items): **active** → 210, **selected** → 209, **cast ordered** → 208.
  They are drawn at the row's left, stepped further left as more of them apply. An entry can show several.
- Usability is refreshed for **all** rows whenever the pool changes (a payment, a wind) or the list is shown.
- **Click on an unusable row: nothing.**

## 2. Q2: the power display

The player's pool **is shown, on the compass**. This is the panel rectangle that alternates with the reaction
portrait (`react_portrait.md`). The compass draws **one marker per point of the player's pool** (0–8) along an arc
near its top, at compass-local positions (34, 63), (40, 58), (47, 54), (55, 52), (63, 52), (71, 54), (78, 58),
(84, 63), in that order (first point leftmost). 🟡 The marker is frame 107 of the panel sprite sheet; check it
visually. The enemy pool is **not** shown.

It is redrawn when the pool changes (row payment, Ctrl re-order, wind) and when the compass returns after a portrait
pop-up. While a portrait is up, the pool is not visible. 🟡 The compass also carries a wind-cycle indicator: it turns
with the 50 s wind clock and plays a short animation during the last 10 s before each wind.

## 3. "Magic with no spell": automatic casting orders

Pressing Magic while the spell list is already shown gives the wand cursor with **no spell**. The next battlefield
click is then classified like a Fire click (first footprint within `max(radius, 48)` of the point, any side,
`player_missile_orders.md` §5). The result is a **wizard attack/search order** that lets the wizard choose its own
spells (library 129–136; `script_magic.md` "Player wizards also run these choosers"):

| click on | event to the wizard (independent wizard in brackets) | message (`GMTXT`) |
|---|---|---|
| another unit, **any side** | 0x29 (0x2F) → auto-cast at that unit | 2012 "have targeted the regiment" |
| a building | 0x28 (0x2F) | 2011 "have targeted the building" |
| the wizard itself | 0x2A (0x2E) → search for targets | 2013 "searching for a target" |
| open ground | **nothing** | – |

Like every Magic order, it is **not** gated by the unit's state (§6). The pending mode ends after the click, and the
spell list stays shown. No cost is paid at the click; the scripts pay per cast from the player pool.

## 4. Q4–Q6: choosing a spell and the target click

### 4.1 Row click (left, no Ctrl, row usable)

In this order:
1. Every **selected** row of the spell list is cleared (no refund). 🟡 The Magic button is also redrawn as held down
   while the spell list is shown.
2. By the spell:
   - **Azure Blades, Fists of Gork** (no target): the **Magic order is issued at once** (§4.4) with point = the
     focused wizard's **regiment position**. Pending mode is cleared and the cursor stays default. The row gets
     **cast ordered** (not selected), so it stays **usable** while the pool allows: clicking it again orders
     (and pays for) another cast.
   - **Dispel Magic** (no target): the order is issued at once, as above. The row gets **selected**, which nothing
     clears, so once per battle (`spell_lasting_effects.md` §5.4).
   - **Any other spell**: wand cursor (if not already in Magic mode); pending mode = Magic with this spell; the row
     gets **selected**.
3. **Pay** the cost: pool −= cost. The compass and all rows' usability are refreshed.

Clicking **another targeted row while targeting** therefore: the first row's selected is cleared (its cost is
**lost**), the second is paid and selected, and the pending spell becomes the second.

### 4.2 Target click (Magic mode with a spell)

Q5. The point is the **ground point under the cursor** in the 3D view. There is no unit snapping in the main view:
the unit under the point is resolved only at the launch (`spell_lasting_effects.md` §0.1). **Minimap clicks are
accepted**. On the minimap, if the minimap pick finds a unit (any side; repeated clicks on the same pixel cycle
through overlapping units, `player_missile_orders.md` §5), the point becomes **that unit's centre**. Otherwise it is
the map point. This minimap snap is the "panel mode" snap mentioned in `script_grid_events.md`.

**Nothing is checked at the click**: no range, arc, sight or "unit under the point". All of that is checked at the
launch (`game_rules.md`).

On the click:
1. The cursor returns to default. The row gets **cast ordered**. The wizard's command slots become **empty**
   (casting state, §1).
2. The Magic order (§4.4) is issued with this spell and point.
3. **Without Ctrl**: the row's **selected** is cleared, its usability is refreshed, and pending mode ends.
4. **With Ctrl** and pool ≥ cost: the cost is **paid again**, the row **stays selected** and **Magic mode stays on**
   with the same spell. Each further Ctrl+click orders the spell again and pays again. A busy wizard refuses the
   extra orders in its script (`GMTXT 2014`) and the power is lost. With Ctrl but pool < cost: as without Ctrl.

### 4.3 No-target spells (Q6)

As §4.1: the order is queued on the row click, with point = the focused wizard's regiment position. There is no
cursor step.

### 4.4 The Magic order itself

The order is applied to the **focused unit** at the start of its next tick (`unit_script_control.md`). It is
**not** subject to the charging/in-melee/broken/pursuing/braced gate (`game_rules.md` "Player orders").
- **Held** (Tangling Thorn): refused silently. The entry's cast-ordered mark is cleared, the panel set is restored,
  and the **power is lost**.
- Otherwise: event **0x2B** to the wizard (source none, parameter = the spell's effect code, point). If queued and
  the wizard is moving (walking, turning or pursuing), it is **halted at once** with halt-and-re-form. A broken or
  pursuing wizard refuses the halt, but the event is still queued.
- The rest is public: `TakeSpellEventTarget` → library 132 → … → `CastPending` (`script_magic.md`). A busy wizard
  refuses in the script with `GMTXT 2014` (Q9: yes, that message comes from the script refusal, not the UI).

## 5. Q4: cancel paths

| action while a targeted spell is selected | effect |
|---|---|
| **Back** (centre skull of the Wizard idle set) | selected cleared (**no refund**), rows refreshed, default cursor, pending mode ends. If nothing was selected: the list area returns to the info card; in Magic-with-no-spell mode only the mode ends and the spell list stays |
| another command button (Move, Attack, Fire, Items, previous/next regiment, …) | the list area switches and **selected is cleared** (no refund); the new command's mode replaces Magic |
| selecting another unit | if in Magic mode: selected cleared in both lists (no refund). The pending mode ends when the panel set changes (another class or state). 🟡 Selecting another **idle wizard** keeps the same panel set; the original then appears to keep Magic mode and the open list of the previous wizard. An engine should cancel the mode and rebind or close the list |
| the wizard breaks / starts pursuing / is charged into melee | the panel set changes and pending mode ends. 🟡 whether selected is cleared at that moment; it is cleared at the next list switch in any case |
| the wizard dies (unit removed) | as deselection |
| right click, Esc | no cancel found 🟡 |

**No path refunds**, and none clears **cast ordered** or **active**.

## 6. Q7: gates

- **The button** exists only on the Wizard-class idle and melee sets (§1). So the player can start a Magic order
  while idle or **in melee**, but not while charging, broken, pursuing, during deployment, or while the wizard is
  casting (empty slots).
- **The order** ignores the unit-state gate. Only **held** refuses it (§4.4). The script refuses a busy wizard
  (2014).
- **Moving**: the order halts the wizard when it is **applied** (the focused unit's next tick), not at the click.

## 7. Q8: Ctrl+click on a row

- **Ctrl+click on a row whose entry is active**: cancels **all** of this wizard's effects with that spell code
  (`game_rules.md`), clears the active mark and refreshes the row. **No** selection, **no** payment, **no** order.
- **Ctrl+click on a row that is not active: nothing.** It is not an ordinary click.
- **Ctrl+Magic** (and Ctrl+Shift, Ctrl+Shift+Tab) are developer keys: a spell-mode cycle with a message box, and a
  "both pools to 8" cheat. They are not gameplay; an engine should omit them.

## 8. Q9: feedback

- Row click, Back, target click: **no message, no speech**. Only the UI click sound of the button press
  (`battle_hud` behaviour: buttons click on mouse down) and the cursor change.
- No-spell wizard orders: `GMTXT` 2011 / 2012 / 2013 (§3).
- After the order: the script and launch messages (2014 busy; 2021 failed launch; `script_magic.md`).

## 9. The engine model, confirmed or corrected

| implementer's plan | original |
|---|---|
| Magic **toggles** a spell list in the (200,64) rectangle | **Shows** the spell list; a second press does **not** close it but enters Magic-with-no-spell (§3). The list replaces the info card or item list; Items replaces it in turn |
| usable row click pays and marks selected | ✅, plus: it first clears any other selected row (no refund) |
| Azure/Dispel/Fists queued at once, point = unit position | ✅ (the regiment position; the focused unit). Azure/Fists get **cast ordered**, not selected, so they can be clicked again. Dispel gets selected for good |
| otherwise wand cursor → ground click → Event(0x2B, code, x, y), clears selected | ✅, plus: minimap clicks snap to a picked unit's centre; the order is applied next tick to the **focused** unit and halts a moving wizard then; **Ctrl+click re-orders and re-pays, staying in targeting** |
| cancelling clears selected without a refund | ✅ (Back, other commands, unit change); no right-click/Esc cancel 🟡 |
| — | add: the compass pool markers (§2); the cost number on spell rows; marks 208/209/210; empty command slots while casting; held wizards refuse silently |

## 10. Test vectors

Wizard W focused, idle, spells in file order [Lightning (cost 1), Fireball (1), Azure Blades (1), Dispel Magic (1),
Storm of Shemtek (3)], player pool 4, list area showing the info card.

| before | action | after |
|---|---|---|
| as above | press Magic | spell list shown: 5 rows, costs 1 1 1 1 3, all usable (pool 4); pending none; compass shows 4 markers |
| spell list shown | press Magic again | Magic with no spell, wand cursor; list stays |
| Magic with no spell | click an enemy regiment E (no Ctrl) | event 0x29 to W (source E), `GMTXT 2012`; pending ends; pool unchanged |
| spell list shown | click Lightning | Lightning selected, pool 3, wand cursor, pending = Lightning; Storm row still usable (3 ≤ 3) |
| Lightning selected, pool 3 | click Fireball | Lightning **unselected, not refunded**; Fireball selected; pool 2; Storm row unusable (3 > 2) |
| Fireball selected, pool 2 | click ground point P | Fireball cast ordered, selected cleared, pool 2; cursor default; W's slots empty; next W tick: event 0x2B (Fireball, P); W halted if it was moving |
| Fireball selected, pool 2 | Ctrl+click P | order for P; pool 1; Fireball **still selected**, still targeting |
| same, then Ctrl+click Q | – | order for Q; pool 0; still targeting. W (busy with P) refuses Q in its script: `GMTXT 2014`, power lost |
| Fireball selected, pool 2 | press Back | selected cleared, pool 2 (no refund), cursor default |
| spell list shown, pool 2 | click Azure Blades | order at once (point = W's position), Azure cast ordered (still usable), pool 1 |
| pool 1 | click Dispel Magic | order at once; Dispel **selected for the rest of the battle**; pool 0; all rows unusable |
| pool 0 | click Lightning | nothing (unusable) |
| Azure Blades active on W | Ctrl+click the Azure row | W's Azure Blades effects cancelled, active mark cleared, pool unchanged |
| Lightning not active | Ctrl+click the Lightning row | nothing |
| W held by Tangling Thorn, Lightning selected | click P | order applied next tick → refused silently; Lightning's cast-ordered mark cleared; power lost |
| W in melee | press Magic | allowed (melee set has Magic); the order is not gated |
| W charging | – | no command slots: no Magic |
| W Monster-class shaman with the casting weapon | – | no Magic button |
| Magic mode with Lightning; the minimap pick finds enemy regiment E | click the minimap | point = E's centre |

## 🟡 Open

- Marker sprite frame for the pool display, and the wind-indicator art on the compass.
- Exact moment the empty "casting" command set is replaced after the cast resolves.
- Switching between two idle wizards while the spell list is open or Magic mode is on (the original appears not to
  rebind; recommend cancelling).
- Whether a break/charge on the wizard clears selected at once.
- No right-click/Esc cancel was found.
