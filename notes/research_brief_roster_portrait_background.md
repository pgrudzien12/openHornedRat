# Research brief: roster-book leader portrait background

Brief for one **research agent**. Use the "Common brief for every agent" in `notes/research_plan.md` (project context,
installation path, decompiled resources, Ghidra setup, rules). This brief only adds the question and the deliverable.
The agent's report is a raw research artefact; a separate step turns it into a behavioural spec in `notes/`.

## Why

Army Records (`notes/builtin_widgets.md` §2) draws a regiment's leader portrait in a 72×104 box (Information page:
x=470 next to the banner, or x=350 for a single-model regiment; `whshr/frontend/army_records_view.py`). The original
draws that portrait over a **background**, which we do not have. `notes/builtin_widgets.md` §2.3 lists this as an
open research item and forbids substituting an arbitrary `BACKALL` frame. The lead is
`notes/glue_portraits.md` §1: each of the 37 resident portrait records carries **two extra integers "used by the
roster book"**, meaning unknown.

## Questions (answer every one; mark each ✅ established / 🟡 hypothesis / ⬜ unresolved)

1. **Meaning of the two extra integers** in each resident-portrait record (37 records, terminated by -1): what does the
   roster-book code do with each of them (offset, frame number, size, palette index, background selector, other)?
   Give the full 37-row table: record position, sprite-table index, sprite set name, integer 1, integer 2.
2. **Portrait lookup:** how does the roster book go from a regiment's leader portrait resource (the `*Pic` name in the MRC
   leader block, resolved through the sprite-name table, `notes/sprite_names.md`) to a resident-list record? What
   happens when there is no match (no background? fallback record?).
3. **Background source:** which bitmap or sprite (logical name and, via the sprite/resource mapping, file; frame index)
   is drawn behind the portrait, and how is the frame chosen (fixed, from the integers, from the leader record)?
   Is it a `BACKALL` frame, part of the `ArmyBook` bitmap, a sprite frame of the portrait set itself, or a fill?
   **"No separate background is drawn at all" is a valid answer** (e.g. the portrait's own pixels or the page bitmap
   already supply it); state it explicitly if the code and rendered data support it.
4. **Geometry:** source and destination rectangle of the background and of the portrait relative to the page origin
   (the 72×104 box, any border/frame drawn around it, scaling or clipping). Are the two integers pixel offsets applied
   to the portrait or the background? Does the same geometry apply for the x=470 and x=350 placements?
5. **Palette:** which palette is active while it is drawn (Army Records uses BK2 palette 9), and whether the background
   needs a different palette or colour map (compare `notes/palette_selection.md`, `notes/glue_portraits.md` §2.1 on
   `BACKALL` frames 16/17).
6. **Draw order and conditions:** order relative to the banner, the portrait and the name; when it is skipped (no leader,
   `models == 1` case, missing resource); whether the background is drawn on the Statistics page as well.
7. **Other users:** does any other roster-book path (debrief view, Magic/Encyclopedia books, reinforcement window) use
   the same background code, and would the answer change for them?

## Suggested approach

- Start from the roster-book page drawing code in `WHSHR.EXE` and `GAMEF.DLL` (search `$R/extracted/decompiled/*_all.c`
  for the `ArmyBook`, `BACKALL` and portrait-list references; `tools/ghidra/DumpStringRefs.java` finds them).
- Locate the 37-record table in the executable (`notes/glue_portraits.md` §1 has its shape) and dump the integers with
  `whshr/rules.py` `PeImage`; cross-check them against the sprite frame sizes (frame 0 is 120×152, overlays follow).
- Verify claims against the installation data: render candidate background frames and the portrait together **only in
  scratch under `extracted/`**, and describe what you saw. A claim that rests on code alone stays 🟡 unless data agrees.
- If the answer needs a running original (Wine) to settle, say exactly which observation the user should make
  (state to load, what to look at) instead of guessing.

## Deliverable

- Report `$R/extracted/agent_reports/roster_portrait_background.md`, written incrementally, with the per-question
  status, the 37-row table and code locations (addresses and what is read; **addresses stay in the report**).
- No tracked files are modified; nothing is committed.
- Final message: a compact per-question summary, the report path, and the remaining ⬜ items.

## After the agent

The implementer (a separate step) writes the behavioural spec into `notes/builtin_widgets.md` §2.3 and
`notes/glue_portraits.md` §1 **without** decompiler names or addresses, then implements from those notes only
(`CLAUDE.md` clean-room policy). Spec must give: source, frame mapping, palette, dimensions, positions, conditions.
