# Allied NPC regiments: merge at battle start and write-back (answers to `allied_npc_merge_questions.md`)

Public behavioural handoff for #123 (debrief work). It answers Q1–Q8 of `allied_npc_merge_questions.md`. Static
research plus the installed battle files; the original was not run. It corrects `campaign.md` §3.1 ("if not found it
is kept" is wrong; see §3). Terms: **NPC** = a battle-script unit with side code `0x40` (allied/neutral);
**player regiment** = a unit of the player's marching army in the battle (side code 0); **company** = `ARMY.MRC`;
**roster** = the 38 regiments, whoami 0–37.

## 1. Summary

- Two different objective letters act on NPCs **at battle start**, and only when their first value `a` is non-zero:
  - **G** (`a ≠ 0`): the **army merge**. Each NPC with whoami < 50 is either deleted (its regiment marches with the
    player, or is not in the company) or rebuilt from the company's copy of its regiment.
  - **I** (`a ≠ 0`): the **artillery swap**. Each NPC with whoami < 50 either takes over the deployment spot of the
    player's own marching regiment with the same whoami (which is removed), or is deleted.
- The **write-back** to `debrief.dbf` includes NPCs with whoami < 50 whenever **G or I is defined** at all (any `a`).
- Both start actions run in the objectives' initialisation, after the battle file and the marching army are
  loaded and **before any unit's figures are created**. A merged NPC is therefore built with the company regiment's
  **current model count**.
- Shipped data: G (`a` = 1) only in BF015 and BF017 (the siege of Zhufbar); I (`a` = 1) in BF026, BF029, BF030, BF031
  and BF042. Every NPC in these battles has an explicit `whoami`.

## 2. Q1: affected battles (data)

Roster names are those of `MAXARMY.MRC` (whoami: strength org/now in a new campaign). "≥ 50" = never merged, never
written.

**BF015 and BF017** (`G:1,4`; identical NPC lists, all `hidden:` at the start):

| NPC unit (script) | whoami | script size | roster regiment |
|---|---|---|---|
| `NPC_Grudgebringer<Cavalry` | 2 | 12 | Grudgebringer Cavalry (12) |
| `NPC_Grudgebringer<Infantry` | 3 | 16 | Grudgebringer Infantry (16) |
| `NPC_Ragnar's_Wolves` | 1 | 16 | Ragnar's Wolves (16) |
| `NPC_Black_Avengers` | 4 | 28 | Black Avengers (28) |
| `NPC_Leitdorf_9th<Crossbows` | 7 | 16 | Leitdorf 9th Crossbows (16) |
| `NPC_1st_Mortar_Crew` | 16 | 2 | 1st Mortar Crew (4) |
| `NPC_2nd_Mortar_Crew` | 17 | 2 | 2nd Mortar Crew (4) |
| `NPC_Amber_Wizard` | 20 | 1 | Amber Wizard (1) |
| `NPC_Dwarf_Warriors` | 24 | 20 | Dwarf Warriors (20) |
| `NPC_Mercenary<Crossbows` | 27 | 10 | Mercenary Crossbows (12) |
| `NPC_Ceridan` | 29 | 1 | Ceridan (1) |
| `NPC_Dietrichs<Caravan`, `NPC_Horse<and_cart` ×2 | 100, 101, 102 | 2 each | ≥ 50: untouched |

**BF026** (`I:1,2`): `NPC_1st_Mortar` 16, `NPC_2nd_Mortar` 17 (2 models each).
**BF029** (`I:1,4`): `NPC_Cannon` 15, `NPC_1st_Mortar` 16, `NPC_2nd_Mortar` 17, `NPC_Imperial<Great_Cannon` 14 (2 each);
`NPC_Bright_Wizard` 119 (≥ 50: untouched).
**BF030, BF031, BF042** (`I:1,4`): `NPC_Cannon` 15, `NPC_1st_Mortar` 16, `NPC_2nd_Mortar` 17,
`NPC_Imperial<Great_Cannon` 14, `NPC_Hellblaster` 25 (2 each).

No other shipped battle defines G or I.

## 3. The two start actions (Q2, Q4, Q5)

**Q2.** Neither runs in every battle. The army merge runs only when G is defined with `a ≠ 0`, the artillery swap
only when I is defined with `a ≠ 0`. In other battles NPCs keep their script values and are never written.

### 3.1 G: army merge

For every live NPC with whoami < 50, in unit order:

| Case | Result |
|---|---|
| a player regiment **in this battle** has the same whoami (it marches) | the NPC is **deleted** (removed with 0 models; not written, no counters) |
| otherwise, the **company** has that regiment | the NPC is **merged** (below) and counted in G's second value |
| otherwise (not in the company) | the NPC is **deleted** as well. **Correction**: `campaign.md` §3.1 said it is kept |

A wagon-type NPC (rolling stock) found in the company is counted but not changed.

**Merged fields (Q4)**:

| Field group | Source |
|---|---|
| name | company regiment |
| original and **current model count**, ranks and frontage, M WS BS S T W I A Ld, mount, armour, weapons, race and class, points value, missile weapon, banner and the rest of the stat line | company regiment. The figures are created afterwards from this count, so the NPC fights at the regiment's **current** strength (after earlier casualties and healing), not the script's |
| leader profile | company regiment |
| psychology | company regiment |
| experience (`s_Exp`) | company regiment (career value) |
| spells and magic items | company regiment |
| side | stays **NPC** (allied); the company's type bits are kept with it |
| whoami, `hired`, troop/leader sprites, position, facing, deployment, behaviour script, hidden state | **script** |
| `s_calualties`, `s_routed`, `s_kills` | script (0 in shipped data) |

**Q5.** A regiment in the company but not marching is the merged case: it fights as an allied NPC under the
mission's script, at its company strength. A marching regiment fights only as the player's own unit, because its NPC
copy is deleted. A company regiment at **0 models** is merged with 0 models. With no figures to create it is removed
at once, like any empty unit, and is not written back. 🟡 Whether a regiment waiting for its wounded counts as "in
the company" depends only on its entry in `ARMY.MRC`, which keeps disbanded-but-kept regiments (`casualty_bookkeeping.md` B4).

### 3.2 I: artillery swap

For every live NPC with whoami < 50, in unit order:

| Case | Result |
|---|---|
| a player regiment in this battle has the same whoami | the NPC takes that regiment's **position and facing**. The **player's regiment is removed** (not written). The NPC fights with its **script** values: name, strength (2 models in shipped data), profile, experience |
| no such player regiment | the NPC is **deleted** |

So in BF026/029/030/031/042, only the artillery pieces the player brought take part, and they appear as allied NPCs
with the script's crew at the player's deployment spot. Nothing is copied from the company.

## 4. Q3: whoami 0 and missing whoami lines

- A unit without a `set:whoami` line has whoami 0. Roster entry 0 is a real regiment (**Vannheim's 75th**, 18
  models). The tests are "side code `0x40` and whoami < 50", so in a G or I battle such an NPC would be treated as
  regiment 0: merged with Vannheim's 75th if it is in the company, deleted otherwise, and written back as
  regiment 0.
- No shipped G/I battle has such an NPC: all their NPCs carry an explicit whoami (§2). In every other battle, NPCs
  are neither merged nor written, whatever their whoami.
- Engine advice: reproduce the rule for shipped data. Treating a missing line as "no regiment" is a safe deviation,
  because it changes nothing in shipped battles.

## 5. Q6: result accounting

- **Written** (G or I defined): every surviving NPC with whoami < 50 goes to `debrief.dbf` **Surviving Units** with its
  live `s_size` and raw `s_calualties`/`s_routed`/`s_kills`/`s_Exp`. Every removed one goes to **Dead or Routed
  Units** with `s_calualties` set to 0 (`casualty_bookkeeping.md` §2.5). NPCs deleted at the start (§3) are not
  written.
- **Campaign side**: the written NPC is handled by whoami exactly like a player regiment (`casualty_bookkeeping.md`
  B5): wounded, merge into `PLAY.MRC`, merge and healing in `ARMY.MRC` if the regiment is in the company. Routed models
  return as for player units, through the same `s_size + s_routed` rule.
- **Start values for "gained"**: a G-merged NPC starts from the company's career `s_Exp` and 0 kills, so its gain is
  final minus that career value, like a marching regiment. An I-swapped NPC starts from the **script's** experience.
  Its write-back then carries the script-based values into the roster for that regiment 🟡 (consequence of §3.2,
  not observed in play).
- The roster's experience baseline used by the troop page comes from the roster entry, not from the unit, so it
  is the same as for a marching regiment (`casualty_bookkeeping.md` B6).

## 6. Q7, Q8 (lower priority)

- **Q7** 🟡: the writer emits units in unit order within each section, so written NPCs appear where they sit in the
  battle's unit order (the battle file's sections), interleaved with player units, not after them. Their `hired`
  value is the script's (the merge does not copy it). The P3 colouring then follows that value. Not checked on
  screen.
- **Q8** 🟡: the merge reads the side at battle start, the writer reads it at the end. A unit whose side a script
  changes to `0x40` during the battle (library 152's `SetSide 64` on event 54) is written if whoami < 50 and G/I is
  defined. No shipped G/I battle relies on this.

## 7. Test vectors

| Before | Event | After |
|---|---|---|
| BF015, company: Cavalry (2) 9/12 models, Black Avengers (4) 20/28; marching: Cavalry | battle start (G a=1) | `NPC_Grudgebringer<Cavalry` deleted (Cavalry marches); `NPC_Black_Avengers` merged: name, stats, psychology, items, spells, `s_Exp` from the company, **20 models**; position, script, hidden state from the battle file |
| BF015, Mercenary Crossbows (27) not in the company | battle start | `NPC_Mercenary<Crossbows` deleted |
| BF015, Black Avengers merged, ends the battle with 15 models, 3 routed, `s_Exp` +40 | tent | written under Surviving Units, 15 models, raw counters; debrief: wounded from (5 − 3) lost, merged back into the company like a player regiment |
| BF015, merged NPC wiped out | tent | written under Dead or Routed, `s_size` 0, `s_calualties` 0 |
| BF029 (I a=1), player marches Cannon Crew (15, 4 models) at (300, 200) facing 0 | battle start | player Cannon Crew removed; `NPC_Cannon` (2 models, script stats) placed at (300, 200), facing 0, allied |
| BF029, player did not march the Great Cannon (14) | battle start | `NPC_Imperial<Great_Cannon` deleted |
| BF029, `NPC_Bright_Wizard` (119) | any | untouched, never written |
| battle without G or I, NPC with whoami 3 | start and end | kept as scripted; not written |
