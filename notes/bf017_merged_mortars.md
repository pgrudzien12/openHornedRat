# BF015/BF017: the NPC mortar crews are not merged and drive out with the column

Public implementation report (batch 16, follow-up of [`bf015_gate_npc_column.md`](bf015_gate_npc_column.md)).
Behaviour only. It answers what the original does with `NPC_1st_Mortar_Crew` and `NPC_2nd_Mortar_Crew` in the siege
battles BF015 and BF017 (objective `G:1,4`, the army merge of `allied_npc_merge.md` §3.1).

## 1. The deciding fact: the merge skips rolling stock

`allied_npc_merge.md` §3.1 says "a wagon-type NPC found in the company is counted but not changed". Made precise here:

- "Wagon-type" is decided by the **battle file's own unit**, before anything is copied. It means the class encoded in
  that unit's `s_race` is **RollingStock** (class 7), which gives the wagon formation kind.
- Such an NPC is **counted** in G's second value, but **nothing** is copied from the company: no name, model count,
  profile, class, armour, weapons, psychology, experience, spells or items. It keeps every value of the battle file.

Both mortar NPCs are exactly this case. Their battle-file entry has `setstats:s_mount=0,0,10,56,12,0`, so `s_race` is
56 = class 7 × 8 + race 0, Human RollingStock (the file even carries the comment "S_RACE is Human RollingStock").
The company's Mortar Crew regiments (whoami 16 and 17, class Artillery) are found, counted and **not copied**.

## 2. Q6 (a): what the two units are in battle

| Property | Value (battle file, unchanged) |
|---|---|
| class / formation kind | **RollingStock**, the wagon layout: 2 models, team (`PackPony`) and limbered mortar (`MrtWagon` leader) 22 units apart front to back, facing snapped to 45° steps (`game_rules.md` "Formations", wagons) |
| anchored | **no**. Only the war-machine formation kind (class Artillery) is anchored at set-up |
| side | 64 (neutral / allied NPC), from the file |
| strength | the file's 2 models (`s_side=64,2,2,2`), not the company's crew count |
| speed | neutral rule, M′ = 2 (`s_move` M = 2; `s_armr` 0, so not mounted) → `s_rlmv` = trunc(4.8) + 4 = **8**, the same as the column's other wagons |
| name | `NPC_1st_Mortar_Crew` / `NPC_2nd_Mortar_Crew` from the file |
| figures | the limber families of `machine_figure_animation.md` §2.8 (`MrtWagon` and the team) |

So they are wagons of the column, not war machines. An engine that applies the company's Artillery class to them
(and with it the anchor) diverges.

## 3. Q6 (b): node opcodes and anchoring (general rule)

For any unit (relevant if an engine ever has an anchored unit on such a script):

| Opcode | Anchored war machine | Unanchored unit (these mortars) |
|---|---|---|
| `PlaceAtNode n` | **moves it**: no anchor test (only an inactive node stops it). The re-form it queues is cancelled by its own snap anyway | moves it, models snapped (`bf015_gate_npc_column.md` Q2) |
| `TeleportToNode n` | moves it: no anchor test | moves it; models walk to their slots |
| `MoveToNode n` | **refused**: condition false, nothing moves (`movement_formation.md` §3.1) | ordinary point move |

## 4. Q6 (c): where they end up

Both run BF015/BF017 script 0, like the rest of the NPC column (`bf015_gate_npc_column.md` Q2):

1. `SetUnitFlags 0x30000000`. They wait off-field, hidden, not shown, at (1783, 1977) and (1850, 1977), facing 26.
2. When node 15 is free: `PlaceAtNode 15`. The unit is at (507, 24) facing 26 on that tick, with both figures in
   their wagon slots. `ClearUnitFlags 0x30000000`. `ReformBlock`, then wait for the re-form.
3. `MoveToNode 12`: they drive at `s_rlmv` 8 with the column to the gate area (1000, 1940).
4. In node 12's area: the first arrival opens the gate (state 2). `SetUnitFlags 0x20000000` (no minimap marker),
   `MoveToNode 13`: they drive through the gate to (1000, 2290), then `ExcludeFromArmy; RemoveFromBattle`.

So they **leave through the gate with the column**. They neither stand at node 15 nor stay off-map. Their hidden
state follows the ordinary rules for hidden allied units (`hidden_reserves_off_field.md`).

## 5. Test vectors

| Before | Step | After |
|---|---|---|
| battle file NPC with `s_race` 56 (RollingStock), company has whoami 16 (Artillery, 4 models) | G merge at battle start | counted; unit keeps class RollingStock, 2 models, file profile and name; not anchored |
| battle file NPC with `s_race` 8 (Human Infantry), company has its whoami | G merge | merged: company name, strength, class, profile … (`allied_npc_merge.md` §3.1) |
| mortar NPC at (1783, 1977), node 15 free | `PlaceAtNode 15` | at (507, 24), facing 26, team and limber in their slots, same tick |
| same, after `ReformBlock` settles | `MoveToNode 12` | moving, `s_rlmv` 8 |
| an **anchored** war machine (class Artillery, not destroyed) | `PlaceAtNode n` | placed at the node |
| same | `MoveToNode n` | refused, condition false |

## 6. Consequence for the write-back (pointer)

**Correction:** the exit script first sets **kept for return**, then runs `ExcludeFromArmy; RemoveFromBattle`.
G's final cleanup discards kept-for-return RollingStock from removal accounting without reactivating it.
The exited mortar placeholders therefore reach neither result section and do not overwrite the company's mortar
regiments with their two-model battle-file state. See [exclude_from_army.md](exclude_from_army.md) for the separate
exclusion, removal, credit and final-cleanup effects.

## Correction to existing public notes

- `allied_npc_merge.md` §3.1: "A wagon-type NPC (rolling stock) found in the company is counted but not changed" now
  says that "wagon-type" means the battle-file unit's own class, and names the BF015/BF017 mortar crews as the shipped
  case.
