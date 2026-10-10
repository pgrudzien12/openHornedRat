# Battlefield item list, leader figure, and melee item bonuses

This note covers the item list in the battle command panel, Potion of Strength, and
Grudgebringer's passive melee bonus. Item projectile behaviour is in
[spell_blades_flock_items.md §4](spell_blades_flock_items.md#4-banner-of-wrath-and-grudgebringer-activated-items);
general melee item effects are in [game_rules.md §5.6](game_rules.md#magic-item-effects-).

## Battlefield item list

The **Items** command in the Attack set (and the melee set where available) opens the
selected regiment's item list. That command is offered when the regiment has items **and a
living leader figure**. Pressing Items again closes the list. Selecting another regiment
shows that regiment's own list when Items is opened for it. The list uses the order of the
regiment's `addmagicitem:` entries; it does not sort by item name or effect.

The list occupies a **240 × 108** rectangle at **(200, 64)** within the battle command
panel, whose top begins at screen y = 304 in the 640 × 480 layout. Five **232 × 18**
rows begin at x = 5 within that rectangle, at y = 8, 27, 46, 65, and 84. Thus the first
row starts at panel (205, 72), or screen (205, 376). Unfilled rows show the list
background. Each occupied row names the item. A usable row has the raised appearance;
a disabled row has the muted appearance. A usable row shows its pressed appearance
while held and activates on release. An active effect and a pending selection can also
have small status marks beside the row. **Used** is a rule state that disables the row;
there is no separate required "used" label.

| Item state | Row behaviour |
|---|---|
| Passive item, such as a sword or armour | Visible, disabled; its passive rule can still apply in combat. |
| Potion of Strength, unused | Enabled. Clicking immediately activates it and spends its single use. No battlefield target is requested. |
| Potion of Strength, active and used | Disabled for the rest of this battle; its Strength bonus remains active. A wind of magic does not rearm it. |
| Banner of Wrath or Grudgebringer, ready | Enabled. Clicking spends this wind's use and enters battlefield targeting. |
| Banner of Wrath or Grudgebringer, selected for targeting | The row shows the pending selection. A battlefield click sends the item order; cancelling clears the selection but leaves the use spent. |
| Banner of Wrath or Grudgebringer, used | Disabled until the next wind of magic, whether the order launched, failed, or was cancelled. The next wind rearms these items on both sides. |

Changing the command, closing the list, or cancelling a pending target clears the
pending selection. It does **not** refund a reusable item's spent use. A target click
uses the unit's **current target** if it has one; otherwise it uses the clicked point.
The item order can still fail after the click, for example because it is out of range,
outside the launch arc, or the bearer is held. These failures do not refund the use.
The active projectile is separate from the row's used state: a later wind can rearm a
reusable item even while its earlier projectile still exists. See the companion report
for launch checks and effects.

## Potion of Strength and Grudgebringer in melee

**Potion of Strength** takes effect as soon as its row is clicked. It gives **+3 Strength
to the leader figure's attacks** for the remainder of the battle. It is not a timed
spell effect and cannot be dispelled. Ordinary figures in the same regiment do not gain
the bonus. The leader's displayed Strength also reflects the active Potion. Drinking it
does not add a line to the original battle message window; see
[potion_strength_battle_message.md](potion_strength_battle_message.md).

**Grudgebringer** gives **+1 Strength and +1 Weapon Skill** when the bearer regiment's
**leader figure attacks in melee**. Other figures in that regiment do not receive
either bonus. This passive bonus is present whether or not Grudgebringer's Fireball use
is ready, spent, pending, or active. The active Fireball is a separate item action.
The melee calculation applies its usual caps after item bonuses: Strength at 9 and
Weapon Skill at 10.

## How the leader figure is tracked

The battle treats the leader as a **particular figure in the regiment**, with its own
position, wounds and stat profile. The regiment retains that figure's identity as models
move and reform; it does not infer the leader from whichever ordinary figure happens to
stand nearest the centre. In a block formation the front-rank centre position is
reserved for that figure, unless the regiment is fleeing. Combat tests whether the
attacking figure is that leader before applying leader-only items. Other systems also
use its identity: spells may aim at a target's leader figure, the leader can play a
distinct animation, and its death generates the leader-killed event. A regiment whose
leader has died does not acquire a replacement leader merely because another figure
moves into the centre position. War machines use their machine figure as the equivalent
leader figure for these identity tests.

## Before / action / after examples

| Before | Action | After |
|---|---|---|
| A regiment has Potion of Strength in its first item entry and Grudgebringer in its second; both unused. | Open Items. | Two occupied rows appear at panel (205, 72) and (205, 91), in that order; the Potion and Grudgebringer rows are enabled. |
| Potion unused; leader S 4; two ordinary figures S 3. | Click Potion. | Potion row disabled and active. Leader attacks at S 7; both ordinary figures still attack at S 3. No target cursor or battlefield order is needed. |
| Potion active; a wind of magic arrives. | Wind resolves. | Potion remains active and disabled; the leader retains +3 S. |
| Grudgebringer ready; leader WS 5, S 4; ordinary figure WS 3, S 3. | Resolve one melee attack by each figure. | Leader attacks with WS 6, S 5; ordinary figure attacks with WS 3, S 3. |
| Grudgebringer ready; leader is fighting and the regiment already targets enemy E. | Click Grudgebringer, then click empty ground. | This wind's use is spent; the item order aims at E's leader figure, regardless of the ground click. The passive melee bonus remains. |
| Grudgebringer ready; regiment has no current target. | Click Grudgebringer, then cancel targeting. | The pending selection disappears; no Fireball is ordered; the row stays disabled until the next wind. |
| Grudgebringer use spent. | A wind of magic arrives. | Its row becomes enabled again; its passive melee bonus never stopped. |
| A regiment's leader dies while ordinary figures survive. | Re-form the regiment. | The leader-killed event has occurred. An ordinary figure may occupy a central position, but it does not become the leader or gain leader-only item bonuses. |

The numbers in these examples are illustrative combat stats. Panel positions and the
item behaviours above describe the original battle interface.
