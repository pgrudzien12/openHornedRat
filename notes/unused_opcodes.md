# Unit-script opcodes that shipped play never reaches

Public implementation report, batch 11 of the interpreter requests (GitHub #3). It confirms that the 25 opcodes with
zero shipped uses cannot be reached in shipped play, and for modding says which used opcode each one mirrors.
Companion to `script_queries.md`, `script_magic.md`, `threat_events_nodes.md` and `unit_script_control.md`.

## 1. Checks made

| # | check | result |
|---|---|---|
| 1a | **Which script DLLs exist.** Every `.DLL` under the installation was listed. Unit scripts live only in `FILE/SCRIPT/` (the 44 `BFxxx.DLL` plus `NULL.DLL`, which holds only the shared library). `UPDATE/` and `REMOTE/` contain no script DLLs, and no two script DLLs differ only in case. | `script_dlls()` already covers every script DLL. |
| 1b | **Script ids.** Each DLL exports two id ranges, mission ids 0…n and library ids 100–170, both without holes. Every id's script is walked. Every `set:script=N` in the 39 campaign battle files names an id that exists in that battle's DLL (466 checks). The test and editor battle files (`B`, `DB015`, `PLOT1`, `RLTEST*`, `SPRED`, `WIZTEST`, `_DESTEST`, `_KFTEST`) have no DLL of their own and can only run one of the 45 DLLs. | No unreferenced script id. |
| 1c | **Script words outside every script.** Every 32-bit word in each DLL's script area that no walked script covers was examined. Apart from the id tables and padding, the only script-like words are **one unreferenced script body in `BF027.DLL`**, stored after script 5. It is an artillery fire loop (`FindTargetOfClass 40/32`, `FindTarget`, `GosubScript 116`, `FireAtNode 12`) and uses only implemented opcodes. No id points to it, so it never runs. | Nothing reachable added. |
| 2 | **Decoding blind spots.** Every 4-byte-aligned 32-bit word of **every byte** of all 45 script DLLs (code, data, tables, padding, the unreferenced script) was compared with the 25 opcode words. **There are zero occurrences.** None of them appears even as an operand, a stray word or an off-alignment decode. The disassembler's only "stray" words are the known single zero words after library scripts 152 and 155. | Cannot be reached by mis-decoding. |
| 3 | **Indirect paths.** The game runs an opcode's routine only through the interpreter's per-instruction dispatch. No other part of the game calls any of these 25 routines directly. The periodic behaviour codes reuse the `Query` cases (`script_behaviours.md` Part 1), not opcode routines. Player orders and UI actions turn into **events** handled by scripts (`threat_events_nodes.md`), never into instructions. No code builds or patches script instructions at run time: scripts are read in place from the DLLs. | No indirect path. |
| 4 | **Campaign and save data.** Saves (`savegame.N`) hold glue-interpreter state, rosters (`.MRC` text with `set:script` ids), the debrief and the mission record (`campaign.md`, `save_resume.md`). They hold **no battle-script state and no bytecode**. The glue only chooses **which DLL** a battle loads (`setmissionscript`/`setbattlescript`), and every candidate DLL is covered by checks 1–2. | Data cannot select a script outside the DLLs. |

**Verdict:** none of the 25 opcodes is reachable in shipped play.

## 2. Per-opcode table and mirrors

"Mirrors" names the used opcode with the same behaviour apart from the stated difference. That is enough to
implement it cheaply for mods; none is needed for shipped data.

| opcode | words | checks | verdict | mirrors / behaviour (for mods) |
|---|---|---|---|---|
| `RestartIfFalse` 0x04 | 1 | 1–4 | unreachable | `Restart` 0x03, only when the condition is false (otherwise continue) |
| `ReturnGosubIfFalse` 0x15 | 1 | 1–4 | unreachable | `ReturnGosub` 0x13, only when the condition is false |
| `WaitWhileMoveState` 0x2C | 2 | 1–4 | unreachable | `WaitWhileUnitFlags` 0x22, tested against the unit's **movement state** (any of the operand's states on) instead of its unit flags |
| `WaitUntilMoveState` 0x2D | 2 | 1–4 | unreachable | `WaitUntilUnitFlags` 0x23, on the movement state |
| `FindFriendTarget` 0x7F | 1 | 1–4 | unreachable | `FindTarget` 0x7B with the **friendly** side set instead of the enemy set (`threat_events_nodes.md` §A) |
| `FindFriendTargetOfClass` 0x80 | 2 | 1–4 | unreachable | `FindTargetOfClass` 0x7C, friendly side set |
| `FindFriendTargetAnyRange` 0x81 | 1 | 1–4 | unreachable | `FindTargetAnyRange` 0x7D, friendly side set |
| `FindFriendTargetOfClassAnyRange` 0x82 | 2 | 1–4 | unreachable | `FindTargetOfClassAnyRange` 0x7E, friendly side set |
| `IfPlayerPower` 0x9B | 2 | 1–4 | unreachable | `IfEnemyPower` 0x9A on the **player** pool: condition = player pool ≥ n |
| `ChooseAllyAndSpellPay` 0x9E | 1 | 1–4 | unreachable | `ChooseEnemyAndSpellPay` 0x9C, but the target is the nearest unit of the **allied side** (exactly that side, not the player army) instead of the nearest hostile unit (`script_magic.md` §2.1) |
| `ChooseAllyOfClassAndSpellPay` 0x9F | 2 | 1–4 | unreachable | `ChooseEnemyOfClassAndSpellPay` 0x9D, allied-side target |
| `TargetNearestAlly` 0xA5 | 1 | 1–4 | unreachable | `TargetNearestEnemy` 0xA3, allied-side candidates |
| `TargetNearestAllyOfClass` 0xA6 | 2 | 1–4 | unreachable | `TargetNearestEnemyOfClass` 0xA4, allied-side candidates |
| `AddPlayerPower` 0xAB | 2 | 1–4 | unreachable | `AddEnemyPower` 0xAC on the player pool (clamped 0…8); the spell buttons are refreshed |
| `SubPlayerPower` 0xAD | 2 | 1–4 | unreachable | player pool := clamp(pool − n); the spell buttons are refreshed; no condition |
| `SubEnemyPower` 0xAE | 2 | 1–4 | unreachable | enemy pool := clamp(pool − n); no condition |
| `AttackNearestEnemyOfClassB` 0xB5 | 2 | 1–4 | unreachable | `AttackNearestEnemyOfClass` 0xB4 with the other side set ("opposing army only" vs "enemy set", `threat_events_nodes.md` §A) 🟡 which of the two |
| `AttackNthNearestEnemyOfClass` 0xB8 | 3 | 1–4 | unreachable | `AttackNthNearestEnemy` 0xB6 with a class filter |
| `AttackNthNearestEnemyOfClassB` 0xB9 | 3 | 1–4 | unreachable | as 0xB8, with the other side set (cf. 0xB5) |
| `AttackNearestAlly` 0xBA | 1 | 1–4 | unreachable | `AttackNearestEnemy` 0xB0, friendly side set |
| `AttackNearestVisibleAlly` 0xBB | 1 | 1–4 | unreachable | `AttackNearestVisibleEnemy` 0xB1, friendly side set |
| `AttackNthNearestAlly` 0xBC | 2 | 1–4 | unreachable | `AttackNthNearestEnemy` 0xB6, friendly side set |
| `AttackNthNearestVisibleAlly` 0xBD | 2 | 1–4 | unreachable | `AttackNthNearestVisibleEnemy` 0xB7, friendly side set |
| `ShowMessage` 0xC1 | 2 | 1–4 | unreachable | if the unit has a leader model: battle message `GMTXT n` with the unit's name, and the unit is brought to the player's attention (🟡 selected or highlighted); no condition |
| `IfTaggedUnitFlags` 0xD2 | 3 | 1–4 | unreachable | `TestUnitFlags` 0x24 applied to the live unit carrying tag `t` (operands: tag, mask; `threat_events_nodes.md` tags). Condition = such a unit exists and any of the mask's states is on; false if no unit has the tag |

The search mirrors share the candidate filters, key and tie rules of their used counterparts in
`threat_events_nodes.md` §A. Only the side set changes. The "friendly" set means non-hostile units other than the
searcher. 🟡 For `FindFriend*` and `Attack*Ally*`, the exact friendly side set was read from the shared search
routine's arguments and not traced further; the `*Ally*` spell/target variants (0x9E, 0x9F, 0xA5, 0xA6) take the
allied side **only**, which was checked.

## 3. Test vectors (mods only)

| before | instruction | after |
|---|---|---|
| condition true | `RestartIfFalse` | continue at the next instruction |
| condition false | `RestartIfFalse` | as `Restart` |
| player pool 3 | `IfPlayerPower 3` / `IfPlayerPower 4` | true / false |
| player pool 1 | `SubPlayerPower 2` | player pool 0 |
| enemy pool 7 | `SubEnemyPower 9` | enemy pool 0 |
| unit with tag 0xABC0 broken | `IfTaggedUnitFlags 0xABC0 0x2000` | true (operand 0x2000 = the broken state) |
| no unit with tag 0xABC0 | `IfTaggedUnitFlags 0xABC0 0x2000` | false |
