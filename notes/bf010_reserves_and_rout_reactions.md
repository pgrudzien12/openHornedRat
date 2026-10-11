# BF010: the Skaven reserves' release, and how units react when their opponent routs

Public behavioural report for the implementer's BF010 playtest questions. It cites `game_rules.md` "Opcode 0x53 in
full" and "Pursuit" (the rout reaction), `script_queries.md` §0.3 (`UnitScore`), §7–§9 (Query 9, 10, 22),
`script_behaviours.md` §1 (behaviours 11 and 15), `threat_events_nodes.md` (`AttackNearestEnemy` and the node
opcodes), `unit_script_control.md` (event dispatch, switches) and `movement_formation.md` §4 (`Rally`).

## 0. Shared state (read this first)

- **Hostile** means one unit belongs to the player army or the allied side and the other to the enemy army. The player
  army and the allied side are **never hostile to each other**; a neutral unit is hostile to nobody. This one rule is
  used by the rout reaction's "another opponent" search, by `UnitScore`, and by the target searches.
- **Event 0x0A** ("engaged in close combat") is queued to **both** units whenever an engagement starts (a charge
  contact, or a unit joining a fight). It is the trigger for BF010's reserves (§3).
- **Event 0x0F** (rout) goes to the router's hostile units. A unit reacts to it only when the router is its own
  current opponent (`game_rules.md` "Opcode 0x53 in full").

## 1. Q1: a shared fight, the enemy routs

**The "another opponent" search never picks a non-hostile unit.** It looks only at the opponents of the searcher's own
figures (the units whose figures are paired with its figures), and accepts one that is not the router, is on a battle
grid, and is **hostile to the searcher**. The allied Dwarfs can therefore never pick the player's cavalry, and the
cavalry can never pick the Dwarfs.

| Before | Action | After |
|---|---|---|
| grid {Dwarfs (allied, handler 151), Cavalry (player), Clanrats (enemy)}; Dwarfs' and Cavalry's figures paired only with Clanrat figures | Clanrats rout (0x0F to both) | **Dwarfs**: their opponent is the router, they are in melee and no other hostile opponent is paired → the condition is true → handler 151 `IfSwitchScriptHigh 164` → **they pursue** (leave the grid, re-form, "Destroy them!", may divert to a stronger threat, then the pursuit). **Cavalry**: the same through its own handler → **pursues**. |
| same, but some Dwarf figures are also paired with a second enemy unit E still fighting | Clanrats rout | Dwarfs **switch to E**: pairings with the router dropped, attack direction reset, current target E, **no pursuit**. Cavalry unchanged (pursues if it has no other hostile opponent) |
| Dwarfs not in melee, not charging, opponent = Clanrats | Clanrats rout | Dwarfs send themselves 0x1B, and library 152 turns that into 0x19 → `DropTarget` → script 163 (halt, re-form, restart) |

The engine fix (player and neutral are never each other's enemy there) matches the original.

## 2. Q2: shooters, wizards and artillery whose opponent routs

The class handlers differ. All run the same in-melee search first (§1).

| Unit | Before | Action: its opponent routs, and no other hostile opponent is paired | After |
|---|---|---|---|
| **Shooter** (handler 156), **not** independent | in melee with X | 0x0F from X | condition true → it **sends itself 0x19** ("opponent gone") → library 152 `DropTarget` → script **163**: `Rally`, wait for the re-form, `ReformToScriptRanks`, `Restart`. Ends **out of the grid**, re-formed, back at its restart point, with no target and no pursuit. Your provisional 0x19 is exactly this path |
| **Shooter**, **independent** | in melee with X | 0x0F from X | condition true → `IfSwitchScriptHigh` **127**: leaves the grid, re-forms to its script ranks, "Destroy them!", picks the best threat (Query 1) and diverts to it if it outweighs its own worth. Otherwise it clears its combat states (charging, in melee and the like) and **loops the independent hunt** (script 122: re-target, approach, fire). It does not pursue |
| **Wizard** (handler 155) | in melee | 0x0F | as the shooter: not independent → 0x19 → 163; independent → script **148** (the same as 127 but with the AI wizard loop 140). **A wizard that is casting ignores the rout event entirely** |
| **Artillery / static** (handler 154) | in melee with X | 0x0F | the static variant counts other **hostile** units on the same battle grid. None → `LeaveSharedGrid`, `Rally` (clears its states and re-forms **in place**); its main script is **not** restarted, so it carries on where it was. Some → its target switches to one of them, no rally |
| Artillery | not in melee, **braced** | 0x0F | `LeaveSharedGrid`, `Rally` (unbraces) |
| Artillery | not in melee, not braced | 0x0F | nothing |
| any of the above | in melee with X **and** another hostile opponent paired | 0x0F from X | switches to that opponent, stays in melee (no 0x19) |

The same reactions apply to event 0x09 in these handlers (cases 15 and 9 share the code).

## 3. Q3: BF010's Skaven reserves

### 3.1 What the scripts do

| Unit (battle file order) | Script | Behaviour |
|---|---|---|
| Clanrat Warriors at (1105, 476) and at (1153, 151) | 2 | attack the nearest enemy every 10 ticks; if none, march to node 11; handler 7 |
| Clanrat Warriors at (1201, 372) | 3, tag 0xABC1 | march to node 6, then node 5; then attack the nearest enemy every 10 ticks (march to node 5 if none) |
| Stormvermin at (1230, 223) | 4, tag 0xABC2, parent = the 0xABC1 unit | march to node 6, then node 10; then **stand** (wait 100, loop) |
| Ilmarin at (1217, 263) | 1, tag 0xABC0, marked | follows its parent (if one is set); on event 0x0C (from handler 8) it runs script 9: face node 12, "rout" line, flee ahead |
| Rat Ogre | 5 | attack the 2nd-nearest enemy every 10 ticks |
| Dwarf Warriors (allied NPC) | 0, handler 151, behaviour 11 | attack the nearest enemy, else march to nodes 8 and 9 |

**The release trigger.** In handler 7, which all the Skaven units use, event **0x0A** ("engaged in close combat") does:
`SendEventToTag 0xABC0 12; SendEventToTag 0xABC1 17; SendEventToTag 0xABC2 17`, then the usual melee switch (165).
Handler 7 case **17** is `SwitchScript 6`, and script 6 is "every 10 ticks `AttackNearestEnemy`; if none, march to
node 5".

So **the first time any handler-7 Skaven unit is engaged in close combat** (normally a script-2 Clanrat unit meeting the
Dwarfs or the player):
- both reserves (scripts 3 and 4) **abandon their march** and switch to script 6. Within 10 ticks they attack the
  **nearest enemy on the whole battlefield**: any hostile unit that is not hidden, broken, marked or a building,
  **including units already in melee** (`game_rules.md` "Scripted nearest-enemy search");
- Ilmarin gets 0x0C and flees towards node 12.

That is why the user remembers them fighting the Dwarfs. The march to the southern nodes is only what they do
**until the first close-combat engagement** of a script-2 unit. Later engagements repeat the 0x11. A unit already
running script 6 ignores the switch to its own script (`unit_script_control.md`), so this changes nothing.

### 3.2 Other links, checked

- **Threat behaviour (15)**: your numbers are right. Worth = size × s_pntval for ordinary units: Clanrats #2 12 × 8 = 96,
  Dwarfs 14 × 10 = 140. `UnitScore(Clanrats, Dwarfs)` at octagonal distance 216 with range 240 is
  `trunc(140 × 24 / 60) = 56`, which does not outweigh 96: no 0x03. And while the Dwarfs are **in melee** their score is
  **0** anyway. Threat tracking never pulls the reserves into a fight the Dwarfs are already in.
- **0x13 / 0x14 (Query 9)**: library 159 (threat attack) broadcasts 0x13 to its own side, and 158 (attack approach)
  reports 0x14 to its parent. The script-2 units attack through `AttackNearestEnemy` → 158; they have no parent, so they
  send nothing. Any Skaven unit that attacks through **159** (after a threat reaction) does broadcast 0x13. A reserve
  without a target, within 240 of that unit, then joins its target. This is a secondary route.
- **Parent link**: the Stormvermin's parent is the 0xABC1 Clanrats. When an enemy announces an attack on the
  Stormvermin (0x05 → Query 6 true), the parent gets 0x15 → Query 10. The parent attacks that threat if it has no target
  and the threat is within 240 of it.
- **Footprint contact** with the Dwarfs while marching starts an engagement (0x0A to both) like any contact. The
  reserve then fights there, and its own 0x0A also sends the 0x11s.
- **Objectives**: nothing in BF010's objective lines diverts these units.

### 3.3 Test vectors

| Before | Event | After |
|---|---|---|
| reserves marching (scripts 3/4); Clanrats (script 2) charge the Dwarfs | contact → 0x0A to Clanrats and Dwarfs | Clanrats' handler 7: 0x0C to Ilmarin, **0x11 to both reserves**, Clanrats → 165 |
| reserve (script 3) at the start of its next tick | 0x11 | `SwitchScript 6`: march abandoned; within 10 ticks `AttackNearestEnemy` → 0x04 (nearest hostile, e.g. the Dwarfs at 216) → 158 approach and attack |
| Stormvermin (script 4), standing at node 10 | 0x11 | the same: script 6, attacks its nearest enemy |
| reserves already in script 6 | another 0x0A on a script-2 unit → 0x11 | switch to the running script ignored; no change |
| no Skaven unit ever engaged | – | reserves march to nodes 5 / 10; the Clanrats (script 3) attack the nearest enemy every 10 ticks after reaching node 5, while the Stormvermin stand |

## 4. Differences from the engine model

1. Implement handler 7's 0x0A case: `SendEventToTag` to 0xABC0 (12), 0xABC1 (17), 0xABC2 (17), and case 17 →
   script 6. The engagement must queue **0x0A to both** engaged units even when the engine handles engagement natively.
2. The rout reactions in §2 replace the provisional 0x19 for independent shooters and wizards (127 / 148), and for
   artillery (rally in place, no restart). Non-independent shooters and wizards: 0x19 → 163 is correct.
3. Your `UnitScore` numbers are correct; Dwarfs in melee score 0.

## 🟡 Open

- None of these BF010 sequences was observed in a running original game; they follow from the battle's own scripts and
  the public rules above.
