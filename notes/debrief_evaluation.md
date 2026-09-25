# Debrief and objective evaluation (battle result → campaign)

Behavioral specification of what the campaign front end does with the battle result file `debrief.dbf`: the objective records and
their `Result:` values, the per-mission **debrief evaluator** table, the hidden defeat conditions (objectives `Z`, `G`, `Y`), the exact
behaviour of `testmission` / `testobjective`, and where crowns are paid. It extends `notes/campaign.md` §5 and §2.5 and closes
`ROADMAP.md` B1–B3. Marks: ✅ read from the executables and cross-checked on shipped data, 🟡 read from code but not observable in
shipped data or only partly traced, ⬜ open.

Sources: the objective evaluators of `GAMEF.DLL` (26 letters), the debrief/end-screen/campaign-over behaviour and the balance-sheet
interpreter of `WHSHR.EXE`; the `.BTS` objective
lines of all 54 battles; all 120 glue scripts; the owner's `debrief.dbf` of `bf003` (checked in §2.3). String ids below are `BKTXT`
ids (table 5); texts are not quoted, only paraphrased.

## 1. Pipeline ✅

1. Before a battle the glue records the **evaluator index** `n − 1` in the current mission record: `setdebrief:n`, `debrief:n`,
   `debriefwithsummary:n`, the `,n` of `playgame*,<bf>,n`, and `debrief:n` in a `[MISSION]` record. **`n = 0` (or a missing number,
   as in `ENMISSION1`'s bare `debrief:`) leaves the previous index unchanged**; it is not a reset. A new game starts at index 0 (`n = 1`).
2. `GAMEF.DLL` evaluates its objectives during the battle and writes `debrief.dbf`: a `Result:` line per defined objective, then the
   surviving and the dead/routed units (`notes/campaign.md` §4.8).
3. On return `WHSHR.EXE` loads `debrief.dbf` and runs the **evaluator** selected by the index (§4). One run yields
   - the **T-result** (1 = victory, 0 = not), used by the end screen and by `testmission`;
   - the **text program** to show on the debrief page (one of up to three lists A/B/C of the entry), or "none";
   - for one evaluator (E7) a change of the glue status bits (§5).
4. Order after a battle: campaign-over test (§3) → wounded/`PLAY.MRC` bookkeeping → debrief screen (mode 2/6 pages: text, troops,
   balance sheet; mode 7: text, balance sheet; mode 4: balance sheet only) → Done: payment and army merge (§6).

## 2. Objective records and `Result:` values

### 2.1 Line format ✅

`Result:<L>,<met>,<v1>,<v2>,<v3>,<v4>` for every objective letter defined in the battle's `.BTS` (`Objective:L,a,b`). The front end
stores per letter: *present*, *met* (0/1) and the four values, in that order. In the game's own terms the values are:

| Field | Content |
|---|---|
| `met` | the letter's evaluator result at the end of the battle (1 = the letter's condition was met). **For `Z`, `G`, `Y` a met flag means defeat** (§3). |
| `v1` | `a` from the `.BTS` for most letters, but several letters overwrite it at battle start with a measured quantity (below) |
| `v2` | `b` from the `.BTS`, or a measured start count |
| `v3`, `v4` | computed at the end (percentage / count now / lost), see the table |

A letter that is not defined in the battle has no record: `testobjective`, the evaluators and the balance sheet then see it as absent
(not met). Objective records are looked up by letter (`A`..`Z`, case-insensitive).

### 2.2 The 26 letters ✅ (GAMEF evaluators)

Evaluator modes: 1 = battle start, 2 = every tick (flag `0x2` letters), 3 = final pass (flag `0x8` letters). Flags (`notes/game_rules.md`
"Missions and objectives"): `0x1` ends the battle when met, `0x4` no line in the end-of-battle list, `0x20` custom end-of-battle line, `0x10` still evaluated after
the battle is decided. "Side" = unit side bits: `0x00` player, `0x40` allied NPC, `0x80` enemy, `0x20` neutral/structures.

| L | Flags | What is measured / when `met` | v1 | v2 | v3 | v4 | Consumers |
|---|---|---|---|---|---|---|---|
| A | 0x03 | enemy (side `0x80`): **all** enemy regiments counted at start are dead, or gone from the field | enemy models at start | enemy regiments at start | 0 | 0 | default evaluator, end screen key `A`, cash `A` letters |
| B | 0x28 | ≥ `a`% of the units of class 6 (villagers, slaves) survive (alive or routed off alive) | `a` = required % | class-6 models at start | % now | count now | text ops, cash 0x3C/0x3F/0x54, evaluator E2/E5, `bonusadd` |
| C | 0x28 | ≥ `a`% of the side-`0x20` units (buildings) survive | `a` | structures at start | % now | count now | text ops, cash 0x3D |
| D | 0x08 | wagons lost (class `0x38`, side `0x40`) ≤ `a` (0 in shipped data) | `a` | wagons at start | lost | wagons now | cash 0x3E (−A × v3), text op D, `testobjective:D` |
| E | 0x08 | ≥ `a`% (100) of the enemy models **killed** (routed enemies do not count) | `a` | enemy models at start | % killed | killed | `testobjective:E` (BPMission5) |
| F | 0x07 | like A but routed/fled units do not count as gone | enemy count | — | 0 | 0 | ends BF009 |
| G | 0x08 | siege "Inside the gates" **loss** flag (§3.3) | `a` | regiments merged | — | — | campaign-over test, evaluator E4 |
| H | 0x07 | battle state 7 reached (siege gate breached; `H(0,0)` only in BF015/BF017) | — | — | — | — | ends the siege battles |
| I | 0x0C | configuration letter (`I(1,4)`): `a ≠ 0` merges NPC artillery into the player army at start; never met | `a` | — | — | — | selects NPC merging in the debrief unit list |
| J | 0x16 | (BF038) met once the battle is decided and the battle state is < 2, then sets state 2 | — | — | — | — | none |
| K | 0x16 | **item pickup**: a player unit reaching node `a` picks up magic item `b`; never a win condition | node | item id | handle/whoami of the picker | item-table index | none |
| L | 0x0C | information only (never met): enemy models at start and at the end | enemy models at start | regiments at start | enemy models left | regiments left | text op "escaped" (BF004_3) |
| M | 0x0C | never met, no code | — | — | — | — | none |
| N | 0x03 | BF014 "past the dragon": enemies gone (A condition) **and** a player unit stands in node `a` | node | — | — | — | ends BF014 |
| O | 0x08 | BF009 "capture the leader": the target unit (`whoami` = a) carries the *captured* flag | `a` | — | — | — | default evaluator (must be met) |
| P | 0x28 | protected unit (`whoami` = a) is still in the battle | `a` | — | — | — | evaluator E3 |
| Q | 0x08 | BF024 "protect the forest": ≥ `a`% (60) of the tree furniture objects still standing | `a` | trees at start | % standing | trees standing | evaluator E6, text op Q |
| R | 0x0C | no evaluator; `a` selects which of the custom end-of-battle caption strings B/C/P print | `a` | — | — | — | in-battle end list only |
| S | 0x08 | **always met** in the final pass (BF001 "capture Hiln") | — | — | — | — | default evaluator |
| T | 0x08 | **always met** in the final pass (BF010 "rescue Ilmarin") | — | — | — | — | default evaluator |
| U | 0x0E | (BF012/018/019, `a` = 4) timer that sends an order message to a player unit every tick period; never met; at the final pass raises the "battle lost" latch (§3.3) | `a` | — | — | — | feeds Y |
| V | 0x0C | units of class `a` killed (dead + routed-away are subtracted); always met | class | count at start | — | **killed** | `bonusadd:4,V` (Skaven heads), text |
| W | 0x0C | artillery (`0x8e & 0xF8 == a`, 32 = rock lobbers, side `0x80`) destroyed; always met | `a` | count at start | — | **destroyed** | cash 0x51/0x52, text op W |
| X | 0x16 | item pickup like K (BF012/018/019/034) | node | item id | picker | item index | none |
| Y | 0x0C | "campaign lost" mirror: G's flag if G is defined, else the latch set by G/U (§3.3) | — | — | — | — | campaign-over test |
| Z | 0x0F | **all player models gone**: every player regiment counted at start is dead or has left the field routed (with NPC allies included when G or I is defined) | models at start | regiments at start | regiments lost | 0 | everything; a met flag is **defeat** |

`v1`/`v2` of `A`/`Z` are re-measured at battle start; the `.BTS` numbers are only a snapshot. Unit class = low 3 bits (`& 7`) or
high 5 bits (`& 0xF8`) of a unit byte; class 6 = villagers/slaves, `0x38` = rolling stock (wagons, gate).

### 2.3 Verification on the owner's file ✅

`debrief.dbf` of `bf003` (Protect Schnappleburg): `Z,0,28,2,0,0` (28 player models, 2 regiments, none lost), `R,0,1,…`,
`A,1,32,2,0,0` (32 enemy models in 2 regiments, all gone; equals the `.BTS` `A(32,2)`), `B,1,80,12,100,12` (≥ 80 % required,
12 villagers, 100 % and 12 alive), `C,1,80,7,100,7`, `K,0,13,10,0,39` (node 13, item 10, not picked up). Default evaluator (§4.1):
`Z` not met, `A`,`B`,`C` met, `R`,`K` ignored → **victory**, as the balance sheet of `notes/campaign.md` §2.5 assumed.

## 3. Defeat and campaign-over conditions

### 3.1 The rule ✅

Run right after every battle (before the debrief screen), on `debrief.dbf` and the roster:

```
commander_dead = the Grudgebringer Cavalry regiment (whoami 2, always in the army) is present and has no survivors
                 (models + routed + wounded == 0)
if not commander_dead:
    campaign_over = (G present and G.met) or (Y present and Y.met)        # movie "death02"
else:
    if Z present and Z.met:  campaign_over                                 # movie "death01"
    else: Cavalry.routed += 1 and write the file                           # commander cannot die unless the whole army does
if campaign_over: play the death movie, then end the game to the title screen; no debrief screen, no payment, no army merge
```

`death01` is chosen when the commander regiment is dead, `death02` otherwise (re-evaluated when the movie starts). ✅ Payment and
army merge are skipped because the wrapper returns before them.

### 3.2 `Z` ✅

`Z` is the hidden loss condition (caption "silent"). `met = 1` when every regiment counted at start (player side, plus NPC allies
when G or I is defined) is dead or has left the field. Consequences: the battle ends (flag `0x1`); the end screen shows failure for
keys `Z`/`z`; **every "returning wounded" counter of the roster is cleared** (`BKTXT 10063` "the wounded could not be recovered"
is the matching text op in some lists); `Z` met alone is only game over if the commander regiment is also dead (§3.1).

### 3.3 `G`, `Y`, `U` ✅ (data) / 🟡 (G's exact test)

- `G` is defined only in BF015/BF017 (siege of Zhufbar/Nuln gates, `G(1,4)`). Its evaluator runs in the final pass and reports
  **met = 1 unless** a gate-breaking condition holds (a gate/rolling-stock unit with `whoami` 100 was handled by the cleanup pass **and**
  units `whoami` 2 and 29 are still present); when it returns 1 it also raises the battle-lost latch. The debrief evaluator E4 uses
  the inverse: victory ⇔ `G` present and **not** met. So in the two siege battles "G met" = the assault failed = campaign over
  (`death02`) when the commander regiment survived. 🟡 which unit `whoami` 100 is and what exactly "handled" means (rolling-stock
  cleanup); the branch structure is certain.
- `Y` is defined in BF001, BF010, BF011, BF014, BF034 as `Y(0,0)`. Its result is `G.met` if G is defined, else the battle-lost latch.
  The latch is written only by `G` and `U`; none of the five battles defines either, so **`Y` is never met in shipped data**: the
  `Y` half of the campaign-over test is dead. `Y` is ignored by the default evaluator.
- `U` (BF012/018/019) raises the latch at the end, but those battles define no `Y`; also dead in shipped data.
- The latch also selects the victory/defeat stinger of the battle-end dialog (`G`-defined battles play the victory sound only when
  the campaign flag is off).

## 4. Debrief evaluators

### 4.1 The eight evaluator kinds ✅

Every entry names one evaluator; a table entry without a function uses **E0**. `present(L)` = the letter has a record; `met(L)`;
`T` = T-result. Lists A/B/C are the text programs of the entry (§4.3); `none` = null.

| Id | Logic | T | Lists |
|---|---|---|---|
| **E0** (default) | walk **all** present objectives; victory iff every present letter **not** in `{F,H,I,J,K,N,R,X,Y}` is met, except `Z`, which must **not** be met | 1 on victory | A on victory, else B |
| **E1** "survive" | `Z` present and not met | 1 iff so | A if so, else B |
| **E2** | `Z` present and not met, `B` present and `B.v4 ≠ 0` (at least one rescued/alive, its % is ignored) | 1 iff so | A if `T`, else B |
| **E3** | `Z` not met → victory (A, T=1). `Z` met → T=0: if `P` present and **not** met → list C, else B | as stated | A / B / C |
| **E4** | `G` present and not met → victory; else defeat | 1 iff so | A if `T`, else B |
| **E5** | same logic as E2 (a duplicate function) | as E2 | A / B |
| **E6** | `Z` met → T=0, list C. `Z` not met: `Q` present and met → T=1, list A; otherwise T=0, list B | as stated | A / B / C |
| **E7** | `Z` met → T=0, B. `Z` not met and `C` present: `C` met → T=1, A, and sets status bit `0x4000`; `C` not met → T=1, list C, sets bit `0x8000`; `C` absent → T=0, B. Clears both bits first and restores the previous mask (§5) | as stated | A / B / C |

If the chosen list is `none`, the evaluation "fails" (returns false): in mode 2 (`playgamewithdebrief`) this skips the debrief screen
entirely and goes straight to Done; modes 4/6/7 have no such check and shipped scripts only reach entries with both needed lists.

### 4.2 The 41 entries ✅

The table has **41 records** (indices 0–40, `n = 1..41`) followed by an all-zero terminator (the "42" of the roadmap counts the
terminator). `key` is the **end-screen key**: `A` = success screen if `A` present and met, else the neutral screen; `T` = success
if T = 1 else failure; `Z` = failure if `Z` met else success; `z` = failure if `Z` met else neutral; `0` = neutral screen always.
Lists: numbers = literal `BKTXT` ids (a text line each), `/` = line break, `` `x` `` = a measured-value text op (§4.3).
Mission mapping is from the glue scripts (`n = 40` is used by no script; `n = 1` only as the initial index).

| n | idx | key | eval | used by | A (success) | B (failure) | C (alternate) |
|---|---|---|---|---|---|---|---|
| 1 | 0 | `0` | E1 | (none; also the index after a new game is 0) | 10000 / 10001 10002 / 10003 | 10004 / 10005 / 10006 10007 | — |
| 2 | 1 | `Z` | E0 | BPMission1 `bf003` | 10008 / 10009 / `B-lost%` `C-lost%` | 10012 / 10013 10014 / `B-lost` `C-lost` | — |
| 3 | 2 | `z` | E0 | BPMission2 `bf005` (ambush) | 10000 / 10001 10002 / 10003 | 10012 / 10017 / 10018 10019 | — |
| 4 | 3 | `z` | E0 | BPMission2 `bf006` (ambush) | 10000 / 10001 10002 / 10003 | 10012 / 10017 / 10020 10021 | — |
| 5 | 4 | `0` | E0 | BPMission2 summary | 10008 / 10022 / `D-lost%` | 10008 / 10022 / `D-lost%` | — |
| 6 | 5 | `Z` | E0 | BPMission3 `bf001` | 10008 / 10009 / 10024 | — | — |
| 7 | 6 | `0` | E1 | BPMission5 summary (`bf007`/`bf008`) | 10008 / 10022 | 10008 / 10022 | — |
| 8 | 7 | `A` | E0 | BPMission9 `bf010` | 10008 / 10025 10026 | — | — |
| 9 | 8 | `A` | E0 | BPMission10 `bf011` | 10008 / 10025 10027 / `B-lost(2)` | — | — |
| 10 | 9 | `0` | E0 | BPMission13 summary | 10008 / 10029 | 10008 / 10029 | — |
| 11 | 10 | `0` | E0 | BPMission15B summary | 10008 / 10030 10031 | 10008 / 10030 10031 | — |
| 12 | 11 | `A` | E0 | REMission1 `bf004_1` | 10008 / 10025 10032 | 10142 / 10143 10144 | — |
| 13 | 12 | `A` | E1 | REMission2 `bf004_2` | 10008 / 10025 10033 / `B-lost%` `C-lost%` | 10142 / 10143 10144 | — |
| 14 | 13 | `A` | E1 | REMission3 `bf004_3` | 10008 / 10035 / `L-left%` | 10142 / 10143 10144 | — |
| 15 | 14 | `T` | E2 | REMission4 `bf004_4` | 10008 / 10025 10027 / `B-saved%` | 10012 / 10038 | — |
| 16 | 15 | `Z` | E0 | REMission5 `bf004_5` | 10008 / 10025 10039 | 10012 / 10040 10041 10042 | — |
| 17 | 16 | `z` | E1 | BMMission1 `bf012` | — | 10012 / 10043 10044 / 10045 | — |
| 18 | 17 | `z` | E1 | BMMission2 `bf018` | — | 10012 / 10046 / 10045 | — |
| 19 | 18 | `z` | E1 | BMMission3 `bf019` | — | 10012 / 10047 10048 / 10045 | — |
| 20 | 19 | `Z` | E3 | GFMission2 `bf040` | 10008 / 10025 10049 | 10012 / 10050 10051 / 10052 10053 | 10012 / 10054 / 10055 |
| 21 | 20 | `Z` | E0 | WEMission2 `bf027` | 10008 / 10009 10056 10057 / `W-kill%` | 10012 / 10103 10104 10105 / `W-kill%` | — |
| 22 | 21 | `Z` | E0 | WEMission3 `bf028` | 10008 / 10059 / `B-lost%(2)` | 10012 / 10061 10062 `B-lost%(2)` | — |
| 23 | 22 | `T` | E4 | `[MISSION]` record `bf015` | 10008 / 10030 10031 10063 | — | — |
| 24 | 23 | `T` | E4 | `[MISSION]` record `bf017` | 10008 / 10030 10031 10063 `W-kill%` | — | — |
| 25 | 24 | `Z` | E0 | SZMission1 `bf041` | 10008 / 10065 | 10012 / 10066 / 10067 10068 | — |
| 26 | 25 | `0` | E0 | SZMission2 `bf037` | 10008 / 10069 10070 | 10012 / 10071 / 10072 10073 | — |
| 27 | 26 | `T` | E5 | `[MISSION]` record `bf036` | 10008 / 10074 / 10063 / `B-saved%(2)` | 10012 / 10075 | — |
| 28 | 27 | `0` | E0 | SZMission5 summary | 10008 / 10076 | — | — |
| 29 | 28 | `Z` | E0 | ENMission1 `bf020` (+ ambush, `debrief:`) | 10008 / 10077 10078 10079 | 10012 / 10080 10081 | — |
| 30 | 29 | `Z` | E1 | ENMission2 `bf025` | 10008 / 10082 10083 | 10012 / 10084 / 10085 10086 | — |
| 31 | 30 | `Z` | E0 | ENMission3 `bf009` | 10008 / 10087 10088 | 10012 / 10089 10090 / 10091 10092 10093 | — |
| 32 | 31 | `Z` | E1 | GMMission1 `bf033` | 10008 / 10009 / `C-lost%(2)` | 10012 / 10095 / 10096 | — |
| 33 | 32 | `Z` | E0 | GMMission2 `bf021` | 10008 / 10097 10098 / 10099 10100 `commit-wounded` 10147 10148 | 10012 / 10101 10102 | — |
| 34 | 33 | `0` | E0 | GMMission3 summary | 10008 / 10107 | — | — |
| 35 | 34 | `0` | E0 | LMission1 summary | 10008 / 10108 | — | — |
| 36 | 35 | `T` | E6 | LMission2 `bf024` | 10008 / 10109 10110 / `Q-lost%` | 10012 / 10112 10113 / `Q-lost%` | 10012 / 10114 10115 / 10116 10117 10118 |
| 37 | 36 | `Z` | E0 | LMission3 `bf032` | 10008 / 10009 / 10119 10120 | — | — |
| 38 | 37 | `Z` | E0 | LM_SubScript1 `bf034` | 10125 / 10126 / 10127 10128 10129 | — | — |
| 39 | 38 | `0` | E7 | LastMission / MissionAM1 `bf035` | 10130 / 10131 / 10132 10133 / 10134 | — | 10130 / 10131 / 10135 10136 10137 / 10134 |
| 40 | 39 | `0` | E0 | (none) | 10008 / 10025 10141 | — | — |
| 41 | 40 | `0` | E0 | SZMission5 `bf014`; BPMission15 `bf038`/`bf039` | 10145 / 10146 | 10142 / 10143 10144 | — |

Observations ✅: (1) evaluation of the same battle by several entries is intended (ambush battles use their own small entries
`n = 3, 4`, the mission summary another, `n = 5`); (2) entries with key `0` never show a failure screen (march/summary pages);
(3) `n = 7`, `10`, `11`, `34`, `35` are summary pages after ambush sequences and evaluate E0/E1 over whatever the last battle wrote
(mostly `Z`).

### 4.3 The text program ✅

A list is a zero-terminated array of dwords, `opcode << 16 | argument`. Opcode 0 ends, 1 starts a new line, 2 prints `BKTXT[argument]`,
and the following measured-value ops print a formatted `BKTXT` line from an objective record (`present` else an error line "objective
not present"):

| Op | Letter | `BKTXT` | Prints |
|---|---|---|---|
| 0x0A / 0x14 | B | 10010 / 10060 | `v2 − v4` lost and `100 − v3` % |
| 0x0B / 0x1A | C | 10011 / 10094 | `v2 − v4` and `100 − v3` % |
| 0x0C / 0x0F | B | 10015 / 10028 | `v2 − v4` (count only) |
| 0x0D | C | 10016 | `v2 − v4` |
| 0x0E | D | 10023 | `v3` wagons lost, `v3 × 100 / v2` % |
| 0x10 | L | 10036 | `v3` escaped, `v3 × 100 / v1` % |
| 0x11 / 0x19 | B | 10037 / 10106 | `v4` saved and `v3` % |
| 0x12 | W | 10058 | `v4` destroyed, `v4 × 100 / v2` % |
| 0x16 | G | 10064 | `v3` regiments safe |
| 0x1B | Q | 10111 | `v2 − v4` trees, `(v2 − v4) × 100 / v2` % |
| 0x1C | — | — | prints nothing; **side effect**: commits the roster's "returning wounded" counters (moves pending into the total) |

(The texts of ids 10000–10148 are the debrief prose, 1001/2001+letter the older per-letter failure/success lines; only the ids
are recorded here.)

### 4.4 End screen and audio ✅

The end screen after a battle uses the entry's `key` (above) to pick `GameEndScreen` (neutral), `…Success` or `…Failure`. In mode 2
the debrief music is the win tune when T = 1, else the lose tune; other modes use the tactical tune.

## 5. `testmission`, `testobjective` and the status bits ✅ (B3 closed)

- `testobjective:<L>`: status test (`notes/glue_interpreter.md` §3) of "letter present **and** met" in the loaded `debrief.dbf`
  (loaded first if not yet in memory; a missing file counts as false). Uses: `BPMission2` (`D`, wagons), `BPMission5` (`E`, kill all),
  `LastMission` (`Z`, with mask `2000`; A27).
- `testmission:`: loads `debrief.dbf` if needed (false if it cannot be loaded), evaluates the **current evaluator index** and sets the
  status bits under the mask if **T = 1**, clears them otherwise; then **autosaves** (the `break` is missing in the original; verified at
  instruction level: after the status update the code calls the autosave routine and only then jumps to the end of the switch).
  It does **not** test the campaign-over condition and does not consult the mission script's other branches.
  Only `REMission4` (slave train `bf004_4`, evaluator `n = 15` = E2): T = 1 iff `Z` not met and ≥ 1 slave survived; the script then
  runs `iftrueaddcash:200` (BRTXT 933) and `iftruegocaravan:infoREC` (recruit scene), otherwise `iffalsegocaravan:select`.
- E7 (final battle `n = 39`): status bit `0x4000` = victory with `C` met, `0x8000` = victory with `C` not met, both cleared first.
  `LastMission` then chooses the ending movie with `setgluestatusmask:4000/8000/2000` + `iftrueplaymovie:A26/A25/A27`
  (`notes/scene_scripts.md`). Because the bits are set inside the evaluator, **any** evaluation of index 38 (end screen, debrief page,
  `testmission`) refreshes them.
- The status bits (and mask) are saved in the save game; a script's earlier `setgluestatus` therefore survives into later
  `iftrue*` (e.g. `BMMission1`: `setgluestatusmask:4` then `iftruegosub`).

## 6. Payment and rewards

### 6.1 Which activity pays ✅

| Activity (glue command) | Screen mode | Money credited | Also |
|---|---|---|---|
| `playgamewithdebrief`, `encounterplaygamewithdebrief` | 2 | **yes**: `coffers += final total` in Done | armour rewards, doubled XP + promotions, army merge |
| `playgame`, `encounterplaygame` (no debrief) | 6 | **no** (the balance sheet page is still shown, with the total the player would get) | armour rewards, XP/promotions, army merge |
| `debrief:` | 4 (balance sheet only) | **yes**, once, by the screen's own completion callback | pops the context; **no** armour/XP/merge (those run only in Done of modes 2/6) |
| `debriefwithsummary:` | 7 (text + balance sheet) | **yes**, once, same callback | as above |

`DoDebriefingDone` (modes 2 and 6, both context variants) is reached through the plain or the encounter callback; its "mode 4"
clause never triggers, because `debrief:` supplies its own callback.

### 6.2 Double payment? ✅ none found

- The final total is a pure function of the mission's cash type and amounts, the objective records and the bonus counter; it is
  recomputed at each use and added to the coffers **once per activity**. No shipped script performs two paying activities for one
  battle (`playgamewithdebrief`/`encounter…withdebrief` scripts contain no `debrief*:`; summary scripts follow only mode-6 ambush
  battles).
- The **advance** is credited once at troop-selection Done (prepaid "initial payment") and is cancelled by op "Payment Already
  Received" in exactly the programs that pay it (types 1, 2, 4, 8): net effect completion + bonuses − penalties, never twice. Types
  without an "Initial" line all carry initial = 0 in the data.
- "Final" clamps the running total at 0 (sets, does not add). "Mission Total" only displays. "+1 Armour" and "2x Experience"
  lines are unconditional on victory but apply once per Done (armour is written into the debrief unit list, then merged once); a
  regiment gets the bonus only if it still has survivors. The armour lines of cash type 11 therefore also apply after a defeat.
- ⚠ **Mode 6 pays nothing.** Missions whose only battle command is `playgame`/`encounterplaygame` and that have no later `debrief*:`
  receive **no** completion payment although the balance sheet page shows one: `BMMission1–3` (cash type 5 "Arrival at Loren",
  5000), `LMission2` (type 3, 800 for `A`+`Q`), `GFMission2` and `REMission3` (amounts 0, no effect). Whether the original design meant
  this is unknown; an engine that wants to reproduce the shipped game must not credit them, and should flag the gap 🟡.

## 7. Corrections to earlier notes

- `notes/campaign.md` §5 step 6: the mode-4 payment is made by the `debrief:` callback, not by Done, and modes 6 and 7 are **not**
  paid by Done (mode 7 is paid by its callback, mode 6 never).
- `notes/campaign.md` §4.8 and §5 step 4: "NPC merging enabled" is precisely "objective `G` or `I` is defined in the battle".
- `notes/campaign.md` §5 step 3: the table has 41 records, 8 evaluator kinds (7 dedicated + the default), and `key` chooses the end
  screen as in §4.2.
- `FORMATS.md` "Mission objectives": the 26 evaluators are now read (§2.2); `Z`, `G`, `Y` are defeat flags, `S` and `T` are
  unconditional, `M` is empty, `K`/`X` are item pickups.

## 8. Open items

1. ⬜ Letters `G` (which unit `whoami` 100 is, what the cleanup pass "handles") and `N`/`O`/`J`: only BF014/BF009/BF015/BF017/BF038
   consume them; their exact trigger chains are not needed for campaign flow but are for a faithful battle.
2. 🟡 Design intent of the unpaid mode-6 missions (§6.2): confirm by Wine observation or the retail manual if ever needed.
3. 🟡 "Commander regiment has no survivors" counts wounded + routed + models; the roster field names are not fully mapped.
4. ⬜ `n = 40` (`BKTXT 10141`, "entered the Dwarven Underway") is unused by any script; likely a cut mission.
5. ⬜ Test with a real `debrief.dbf` for a lost battle and for a battle with `Z` met: only the bf003 victory file exists locally.
