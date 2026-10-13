# ExcludeFromArmy: objective bookkeeping without battlefield removal

Public behavioural hand-off. This report supersedes the shorthand “remove from battle without death” in
`interpreter_implementation_status.md` and corrects the mortar write-back conclusion in
[bf017_merged_mortars.md](bf017_merged_mortars.md). Related rules:
[battle_end_objectives.md](battle_end_objectives.md), [unit_removal_broadcast.md](unit_removal_broadcast.md),
[casualty_bookkeeping.md](casualty_bookkeeping.md).

## 1. Independent states

Keep **active in battle**, **listed for removal accounting**, **counted by objectives**, and **kept for return**
independent. Actual removal normally makes a unit inactive and lists it for removal accounting. Exclusion only
lists it. An excluded unit can therefore be active and listed simultaneously.

| Instruction | Operands / length | Immediate effect | Condition / timing |
|---|---|---|---|
| `ExcludeFromArmy` (0xDA) | none; 1 word | list the executing unit for removal accounting, once | condition unchanged; advances normally, no yield |
| `RemoveFromBattle` (0x8C) | none; 1 word | remove the executing unit's models alive and perform quiet battlefield removal | separate operation; ordinary script execution |

“Army” in this instruction's name does **not** mean delete the company regiment or disable its battlefield unit.

## 2. What exclusion changes and preserves

- **Battle roster:** remains active; active-unit count unchanged. Removal-accounting membership changes immediately.
- **Models and credits:** model count, wounds, casualties, escaped models, kills and experience unchanged.
  Existing per-model credit remains pending; exclusion neither settles nor clears it.
- **Combat and targeting:** no change to melee participation, grid, footprint, collisions, targets, threat, side,
  reload or ability to shoot. Ordinary searches still see the active unit, subject to their usual filters.
- **Scripts:** current script, handler, behaviour, stack, events and waits remain intact. The next instruction can
  run in the same script update. No removal/departure broadcast, no cancellation of spells or effects.
- **Rendering:** no visibility, model, mesh or minimap change caused by exclusion. Existing hidden/off-field/leaving
  states still apply.
- **Campaign:** no immediate company-roster change. The final objective cleanup and result writer consume the
  two independent memberships; exclusion alone is not a universal “omit from campaign results” switch (§5).

Repeating exclusion while already listed changes nothing: no duplicate entry, counter decrement or credit award.
Actual removal later also retains just one removal-accounting entry.

## 3. Objective effects

Exclusion does not change the permanent **counted** state or the load-time model/regiment totals. It changes what
later evaluations see in their removal-accounting pass. These passes do **not** require the listed unit to be
inactive.

- A/F/N treat a listed, counted, currently enemy-side unit as gone. For N the player must still reach its target
  node; exclusion does not satisfy that second condition.
- Z uses the same membership with its player/allied/kept-for-return rules documented in
  `battle_end_objectives.md` §4.4. Excluding a counted player can therefore contribute to loss while it still fights.
- E reads existing casualties minus escaped models from listed counted enemies. Exclusion does not manufacture
  kills. Other letters retain their own active-roster, class, side and final-pass rules; do not globally hide an
  excluded unit from every objective.
- A listed active unit that is also broken and unable to rally can enter both A/Z's active out-of-action adjustment
  and removal-accounting pass. Preserve those independent rules rather than assuming the populations are disjoint.
  🟡 This artificial overlap has not been checked in an original battle session.

Membership takes effect during the instruction. Segment objectives see it at the next eligible boundary, before
that boundary's unit updates (up to 19 running ticks later). Already-met objectives and decided outcomes stay latched.

## 4. BF014 dragon and BF017 mortars

**Dragon:** BF014 script 0 excludes the dragon before `WaitForBattleStart`, then continues its sound and breath
loop. It remains present, rendered under normal visibility rules, targetable and able to produce breath damage.
Exclusion removes the requirement to kill it for N's enemy-elimination component; the other counted enemies and
player arrival at node 26 still matter. It does not reduce N/A's stored initial totals.

**Mortars:** these are the RollingStock placeholders of `bf017_merged_mortars.md`, not Artillery-class crews.
At the exit, script 0 sets `SetUnitFlags2 0x1000` (**kept for return**), then executes exclusion and removal
consecutively without an intervening wait. Exclusion alone would leave them active. Removal takes them off the
field quietly, leaves their single accounting membership, and preserves their pre-removal model count, casualties
and escaped-model counters because they are kept for return. Model removal can still settle stored attacker credits;
restoring the victim's counters does not undo those awards.

G's final cleanup removes kept-for-return RollingStock from removal accounting and does not reactivate them.
Consequently these exited mortar placeholders are in neither result section. Their two-model battle-file profile
is **not** written back over company regiments 16/17. This corrects the previous mortar report's §6.

## 5. Campaign-return boundaries and missing units

The generic result writer reads active units for **Surviving Units** and listed units for **Dead or Routed Units**,
with the side/whoami eligibility rules in `allied_npc_merge.md` §5. Exclusion does not itself suppress either pass.
Without an intervening cleanup, an eligible active excluded unit can appear in both sections. Enemy-side dragon
records are ineligible for company write-back. D/G/L final cleanup can consume listed kept-for-return units;
G treats RollingStock specially as described above. Exclusion does not itself set kept for return.

The opcode acts on the **executing unit**, with no unit-id operand and no target lookup. A missing current target
is irrelevant. A previously removed unit whose record remains listed gains no second entry when excluded again.
Removed units ordinarily do not get further regular script updates.

🟡 A genuinely missing executing-unit record is outside the established script contract; there is no supported
missing-id/no-target branch here. Do not claim the original guarantees a safe no-op for a nonexistent executor.
A host engine may define that defensive behaviour separately.

## 6. Requested test vectors

| Before | Action | After |
|---|---|---|
| BF014 dragon active and counted | exclude | active and listed once; visible under normal rules, breath scripts continue, no credits/casualties; next N check treats it as gone but still needs other enemies gone and player in node 26 |
| ordinary counted enemy active, able to rally | exclude twice | still active, combat/targeting/rendering unchanged; one accounting entry; load totals unchanged; A/F count it gone at next check; no credit awards |
| same enemy, subsequently killed or removed | actual removal | normal model/credit and removal cleanup; still one accounting entry |
| BF017 mortar active at exit, kept for return | exclude only | still active with 2 models if undamaged; listed once; scripts/footprint unchanged; eligible siege Z accounting changes at next check |
| same mortar, now excluded | remove | inactive, footprint/models removed, quiet cleanup; victim's size/casualties/escaped counters restored; any stored attacker credits settled |
| exited mortar | tent / G final cleanup | accounting entry discarded, not reactivated, neither result section; no placeholder write-back to company mortar regiment |
| executing unit exists, current target missing | exclude | executing unit listed normally; target is not used |
| executing unit already removed and listed | exclude again, if explicitly invoked | no additional membership, credits or counter changes |
| executing unit record nonexistent | exclude | 🟡 unsupported executor case; no established safe-no-op guarantee |

## 7. Required change to the stated engine model

Do not call `remove_from_play`, set `fled`, disable combat/rendering, or settle model credits for exclusion.
Keep the existing counted set, and add independent removal-accounting membership which exclusion and actual
removal both enter idempotently. Objective tests read that membership; actual battlefield removal alone performs
model/footprint/effect cleanup and its credit accounting. No engine code is changed by this report.
