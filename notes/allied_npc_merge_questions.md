# Allied NPC regiments in the campaign: engine status and questions for research

Part of the debrief work (#123, `notes/native-windows.md` 9.10: "allied NPC regiments are not merged back").
What the public notes already say is in `notes/campaign.md` 3.1 and 4.8, `notes/casualty_bookkeeping.md`
2.3, 2.5 and B5 and `notes/debrief_evaluation.md` 3.3. This file records what the engine does today and what
is still needed from the original before the feature can be implemented from a public report.

## 1. What the engine does today

- A battle script's "NPC units" army is loaded with each unit's own side code; code `0x40` becomes `Side.NEUTRAL`
  (`whshr/engine.py`, `Battle.from_script`). The unit's `whoami` is read from its `set:whoami` line, one byte,
  **0 when the line is absent** (the field is documented as "0 for ordinary mission units").
- **No army merging at battle start.** The NPC keeps its script values (strength, experience, spells, items).
  The player's army is substituted for the script's "merc" section only (`Battlefield` / `SceneAssets.load_battle`).
- **No write-back.** `BattleScene._store_played_results` builds `UnitOutcome` only for the marching player
  regiments, so an allied NPC's losses, kills and experience never reach the roster, the P3 troop table or the
  wounded bookkeeping.
- Objective `G` / `I` ("NPC merging enabled") is known to the objectives code (`siege`), but nothing uses it for
  this purpose.

## 2. What is documented and could be implemented as is

Write-back filter and counters (`casualty_bookkeeping.md` 2.5): surviving and removed NPC units with
`whoami < 50` are written like player units when the battle defines `G` or `I`; a removed NPC only has its
casualties zeroed; kills and experience credit to the NPC itself (2.3). Roster merge, wounded and healing then
follow the player-unit rules (B5).

## 3. Questions (observable behaviour only)

Q1. **Which shipped battles are affected?** For every campaign battle that defines objective `G` or `I`, list
the NPC units (side code `0x40`) with their `whoami`, name and strength as the battle script gives them, and
whether that `whoami` exists in the 38-entry roster table. (A data table; needs the installation's battle scripts.)

Q2. **Is the merge at battle start gated like the write-back?** `campaign.md` 4.8 says every NPC with
`whoami < 50` is matched against the army. Does that happen in every battle, or only when `G`/`I` is defined?

Q3. **How is an NPC without a `whoami` told apart from roster regiment 0?** The value defaults to 0 and
`0 < 50`. Is roster entry 0 a real regiment that can be in the army, and does an ordinary NPC (peasants,
mercenaries) without the line get merged with it, written back, or excluded some other way?

Q4. **Exactly which fields does the merge copy, and which stay from the script?** The note lists profile,
psychology, experience, spells and items. Please state per field group (model count / current strength,
characteristics, weapons and armour, experience, leader, position, facing, side, behaviour script) whether the
NPC takes the army regiment's value or keeps its own. Especially: does the NPC fight with the army regiment's
**current model count** (after earlier battles' casualties and healing) or the script's?

Q5. **Army regiment not marching, or marching.** The note says an NPC is deleted when its regiment is in the
marching orders, and kept as is when no army regiment is found. What happens to an NPC whose regiment is in the
army but not marching: merged and fighting as an ally (the intended case), or something else? Is a regiment that
is "wounded" or at 0 models treated as "in the army"?

Q6. **Result accounting for a merged NPC.** At the end, does the roster regiment take the NPC's final strength
as its new strength (`PLAY.MRC` merge), with the NPC's casualty counter starting at 0 and its experience at the
copied career value, so that "gained" is final minus start? Does the unit's `exp_at_start` come from the army
regiment? Do routed models of an NPC return at the end like a player unit's?

Q7. **P3 troop table.** Are merged allied NPCs listed (and in which position: after the player units, or in
file order of `debrief.dbf`)? Is the "hired" colouring applied to them? (`native-windows.md` 9.12 lists this as
open.)

Q8. **Side switch.** Does a neutral unit ever become player-allied in a way that changes which of the above
applies (open question 5 in `neutral_units.md`)?

## 4. Suggested hand-off

Answers to Q1-Q6 as a public report section (a table for Q1, a field table for Q4, a few worked examples for
Q5-Q6) are enough to implement the merge at battle start and the write-back; Q7 only affects the P3 listing and
Q8 is not needed for the first version.
