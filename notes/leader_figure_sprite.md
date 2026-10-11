# The leader figure's sprite set

Public behavioural report for the implementer's question "is the leader figure drawn with the leader block's own
`troopsprites`?". Companions: `game_rules.md` "Formations" (where the leader stands; war machines' layout follows the
leader's sprite), "Figure animation" (families and groups), "Death kinds"; `casualty_bookkeeping.md` (leader removal);
`allied_npc_merge.md` (which fields a merge copies); `FORMATS.md` (`troopsprites`, `VoidType`).

## 1. Rule

- Every figure carries **its own sprite set**. When the battle creates a unit's figures, each gets the **unit's**
  `troopsprites` set (with its variant number).
- If the unit's leader block names a sprite set (anything but `VoidType`), **one figure becomes the leader**: the first
  figure of the unit's model list. That figure's sprite set is replaced by the **leader block's `troopsprites`**
  (and its variant), and its profile is the leader's stat line. It is also the figure whose death sends "leader killed"
  (event 0x17).
- If the leader block's sprite is `VoidType` (or there is no leader block), there is **no leader figure**: every figure
  uses the unit's set and the unit has no leader for leadership or items.
- When the leader sprite equals the troop sprite, the leader looks like everybody else; the rule is unchanged.

## 2. Q1–Q3: drawing, animation and death

- **Everything about a figure's look comes from its own set**: the animation family (move, stand, attack, shoot, dead,
  idle groups and their frame programs, timing), the direction frames, the corpse, the burning sequence for fire and
  warpfire deaths (`game_rules.md` "Death kinds": the death script of the figure's own family decides whether it burns).
  The unit class still drives *behaviour* (what the unit does); the *frames* are looked up per figure. So a foot leader
  in a cavalry unit animates as a foot figure, and a leader set with fewer groups simply uses its own groups.
- **War machines**: the leader figure is the machine (its set is the machine's), the crew use the troop set;
  the layout already follows the leader's sprite (`game_rules.md` "Formations").
- **Single-figure units** (heroes, wizards, monsters with a leader block): the only figure is the leader, drawn with the
  leader set.
- **After the leader dies** its corpse uses the leader set. Its leader role ends (`casualty_bookkeeping.md`); **no other
  figure ever takes the leader set or role**. The surviving figures keep their own sets even when the model list is
  compacted.

## 3. Q4, Q5

- Nothing else in the battle screen draws the leader's `troopsprites`: the panel uses the separate `leaderportrait`
  set 🟡 (no other use was found).
- No battle event changes a figure's sprite set mid-battle. An allied NPC merge keeps the **battle script's** troop and
  leader sprites (`allied_npc_merge.md` table), so the script wins.

## 4. Test vectors

| Before | Action | After |
|---|---|---|
| Grudgebringer Cavalry, N figures, troop set = the cavalry set, leader block `troopsprites:MercCaptain` | battle load | figure 1 (the leader, front-rank centre) uses MercCaptain; figures 2…N use the cavalry set |
| same | the leader figure is killed | its dying and corpse frames come from MercCaptain; "leader killed" is sent; no other figure changes set |
| unit with leader block sprite `VoidType` | battle load | all figures use the troop set; no leader figure |
| cannon (machine + crew), leader block = the machine set | battle load | the machine figure uses the leader set, the crew the troop set |
| a foot leader set in a mounted unit | the unit moves / attacks | the leader plays its own (foot) groups; the riders their mounted groups |

## 🟡 Open

- Whether any other display (panel, roster icon) uses the leader's battle sprite set; none found.
