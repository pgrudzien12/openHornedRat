# What a Doomwheel bolt looks like

Public implementation report (behaviour only) for issue #277, part of the spell-visuals epic #259. Gameplay is
public already: the volley and the aim are in `spell_blades_flock_items.md` §5 and `script_behaviours.md` §1.10, the
flight, heights and impact in `spell_effects.md` §2–3.3, and the sound in `spell_sounds.md` (`SFX_Cast_Thunder`). This
report covers only **what is drawn, where and when**.

**Main result:** a Doomwheel bolt **is** an innate Warp Lightning (effect 22). Every one of its frames is the Warp
Lightning beam of `spell_visuals.md` §2.2: `WLIGHT1–4` meshes for the head and the beam segments, and the flash
SPELLS **522–525** (colour bank +16). SPELLS **562–590 are not Doomwheel art.** They belong to the **Warpfire
Thrower's flames** (effect 26; §5). The issue's frame list came from the catalogue sheets and is wrong for the
Doomwheel.

## 1. Result tables

| part | art | placement | timing |
|---|---|---|---|
| head | mesh `WLIGHT1+k` (effect records 20–23), k = 0,1,2,3,0… one step per tick from the launch tick | the bolt's position and height (`spell_effects.md` §2.1: from the Doomwheel's **unit position** at launch height 0, to the scattered destination at aim height ≥ 4); turned to the bearing from start to aim; level | every flight tick up to the tick before arrival. On the arrival or stop tick it is not shown |
| beam segments | the same `WLIGHT1–4` meshes, each looping from `WLIGHT1` at its birth, one step per tick | fixed, at the head's previous position and height. A segment is left on the launch tick and then whenever that position is **more than 32** from the newest segment. Turned to the bolt's bearing | until the effect is removed (§4) |
| last segment | `WLIGHT` loop as above | at the scattered destination, at its aim height, turned back along the beam (bearing + 256) | from the arrival tick (normal arrival only) |
| flash | SPELLS **522 → 525**, one frame per tick, not looping | at the **scattered destination**, at the absolute aim height (ground there + aim height) | 4 ticks, from the arrival tick (or from the tick after an early stop) |

| frames | size | anchor (x, y) | FOL map | bank added | effective map |
|---|---|---|---|---|---|
| 522–525 (flash) | 32 × 32 | 16, 32 (bottom centre) | 15 | +16 | 31 |
| `WLIGHT1–4` (meshes) | — | mesh origin | — | — | mesh texture |

The flash is not directional: frame = 522 + phase. The meshes have no frame direction. They are turned by yaw only.

## 2. Placement

- **Start:** the Doomwheel's **unit position** (not a figure offset), launch height 0. On flat ground the bolt runs
  from height 0 to 4 (`spell_effects.md` §2.1). Against a flying unit the aim height is half its height plus its
  elevation, with a floor of 4.
- **Destination:** the aim point of `spell_blades_flock_items.md` §5 (the unit position of the found unit, or the
  fallback point 96 ahead ±40), scattered with the Doomwheel's BS at range 576 (`spell_effects.md` §2.2).
- **Three bolts per volley:** the bolts aimed ahead, right and left are three separate effects. They are launched in
  the **same tick**, one after another, from the same start point. Each has its own flight length
  `N = 1 + trunc(d / 20)`, its own segments and its own flash. They do not interact visually. Because each bolt aims
  at the unit nearest to its search point (of any side), a "right" or "left" bolt can end anywhere, even behind the
  Doomwheel. Its beam simply runs straight from the Doomwheel to its own destination.
- Nothing is placed on the Doomwheel figure itself (no muzzle sprite). Its animation has no fire step
  (`machine_figure_animation.md` §2.5).

## 3. Animation and stages (one bolt)

The bolt's first update runs on the launch tick T (`spell_effects.md` §1.6–1.7). At tick T+i the head is at the
flight position with r = N − i. Each segment and the flash are drawn first and then advance (draw-then-advance), so a
new segment shows `WLIGHT1` on its birth tick.

Example: Doomwheel at (0,0), destination (0,400) with no scatter, flat ground, so N = 21 and y(r) = 400 − trunc(400 r / 21).

| tick | head (record) at y | segments existing after the tick (birth position) | flash |
|---|---|---|---|
| T | `WLIGHT1` at 0 | 1 (0) | – |
| T+1 | `WLIGHT2` at 20 | 1 (previous 0, distance 0 ≤ 32: none added) | – |
| T+2 | `WLIGHT3` at 39 | 1 (20 − 0 = 20 ≤ 32) | – |
| T+3 | `WLIGHT4` at 58 | 2 (+39: 39 > 32) | – |
| T+5, T+7 … T+17 | … | +77, +115, +153, +191, +229, +267, +305 | – |
| T+19 (y = 362, 38 < 40 from the destination: arrival) | none (removed this tick) | +343, then **last segment at 400** facing back: 11 | **522** at (0,400), aim height |
| T+20 | – | 11 | 523 |
| T+21 | – | 11 | 524 |
| T+22 | – | 11 | 525 |
| T+23 | – | **all removed** | removed |

- Segments are born about every second tick (≈ 39 units apart at 20 units per tick).
- On the arrival tick the existing segments advance **twice**, so their loop phase skips one frame on that tick. It is
  cosmetic and an engine may ignore it.
- **Long bolts:** at most **30 segments** are ever on screen for one bolt. After that no new segment is added, and on
  arrival no last segment is added either. The flash still plays. With ≈ 39 units per segment, only the first
  ≈ 1,130 units of the beam are drawn as segments. Beyond that the head flies on alone. Cast Warp Lightning
  (range 576) never reaches this cap, but a Doomwheel bolt can: its search distance goes up to 2,592 and its target
  can be up to twice that away. 🟡 Whether to reproduce this is a presentation decision for the engine (see §7).

## 4. Removal

| end | what is seen |
|---|---|
| **normal arrival** (within 40 of the destination) | head gone that tick, last segment and flash 522 at the destination. Flash 523–525 on the next three ticks. On the 4th tick after arrival **every segment and the flash disappear together**, with no tail. The bolt's sound is stopped then (`spell_sounds.md`) |
| **stopped in flight** (hits a unit, building or solid object, `spell_effects.md` §2.3) on tick H, ≥ 40 from the destination | H: head gone, segments stay (and a segment may still be added on H). H+1: one more segment may be added at the stop point (if > 32 from the newest). The **flash starts at H+1 at the scattered destination**, not at the stop point. It plays 522…525 over H+1…H+4. Everything is removed at H+5. No last segment |
| stopped on the same tick it comes within 40 | treated as a normal arrival on that tick (flash at the destination on H) |
| **below the ground** (ridge between Doomwheel and target) | as "stopped in flight": flash at the destination one tick later, even though the bolt never got there |
| **failed bolt** (the 1-in-6 roll, also the global effect limit of `spell_effects.md` §1.2) | **nothing at all**: no head, segment, flash or sound. Only `GMTXT 2021` for a player-army Doomwheel. The other bolts are unaffected |
| **Doomwheel destroyed or removed** during the flight | **nothing changes.** Innate effects are never cancelled (`spell_effects.md` §1.4), so the bolt flies, strikes and flashes normally |
| **target unit removed** | nothing changes. The bolt aims at a point, not at a unit |
| dispel, Ctrl+click, recast | do not apply: innate bolts are never dispelled or cancelled. A new volley adds three new bolts beside any still in flight |

## 5. Ownership of frames 562–590 (and the neighbours)

| frames | owner | selected? |
|---|---|---|
| 490–521 | Warp Lightning's **Shift developer variant**: a directional sprite head, `490 + 8 × phase + direction`, phase 0–3, bank +16 (`spell_effects.md` §3.9). Shift is read from the keyboard at the moment of **any** Warp Lightning launch, Doomwheel bolts included, so holding Shift when a Doomwheel fires switches that bolt to it (18-tick flight, no segments, then the normal 522–525 flash) | only with Shift held. An engine may ignore it |
| 522–525 | Warp Lightning flash (spell and Doomwheel) | yes |
| 526–528 | the same crackle continuing to fade (art only) | **never**. The flash is a fixed 4-frame run |
| 562–581 | **Warpfire Thrower flame (effect 26)**: head cycling 562–565, and trail puffs that each play 562 → 581 once | yes, by the warpfire, **never by the Doomwheel** |
| 582–590 | **Warpfire flame end burst** (green ball, then expanding rings), 9 frames, bank +32. It is chosen by an explicit start frame in the warpfire's end step, on the ground at the flame's last position | yes, by the warpfire, **never by the Doomwheel** |

For 562–590 the FOL map is 7 for 562–581 and 8 for 582–590. With bank +32 the effective maps are 39 and 40. The
warpfire visuals are only identified here. Their full playback (jitter, timing, removal) needs their own research
item.

## 6. Test vectors

| before | action | after |
|---|---|---|
| Doomwheel at (0,0), reloaded, three bolts aimed; bolt 2's failure roll is a 6 | volley at tick T | bolts 1 and 3: head `WLIGHT1` and one segment at (0,0) on T. Bolt 2: nothing drawn. `GMTXT 2021` only if it is the player's |
| bolt to (0,400), N = 21, nothing in the way | T+18 / T+19 / T+22 / T+23 | head `WLIGHT3` at y 343 / no head, last segment at (0,400), flash 522 / flash 525 / all gone |
| same, a unit stops the bolt at y = 191 (tick T+10) | T+10 / T+11 / T+14 / T+15 | head gone, segments 0…153 stay / segment added at 191 (191 − 153 > 32) and flash **522 at (0,400)** (not at 191) / 525 / all gone |
| the Doomwheel is destroyed at T+5 | T+5 … T+23 | the bolt continues unchanged, as in row 2 |
| bolt to a point 2,000 away (N = 101) | ticks T…T+100 | segments stop being added after the 30th (≈ 1,130 units out). The head flies on alone. On arrival there is no last segment, but flash 522–525 still plays at the destination |
| flying target (aim height h ≥ 4) | arrival | flash drawn with its bottom at ground + h |

## 7. Differences from the current public text and engine

- The issue's "562–581 bolts / 582–590 end flash, bank +32" is **wrong for the Doomwheel**. That is the warpfire's
  art. The Doomwheel uses the Warp Lightning art exactly. The engine already draws Doomwheel bolts as Warp Lightning,
  which is correct.
- `spell_visuals.md` §2.2, step 4 🟡 is resolved: segments stay **exactly as long as the flash**. Both are removed
  together on the tick after the last flash frame (arrival + 4).
- `spell_visuals.md` §2.2, step 5 🟡 is resolved: a beam stopped early (or that went below the ground) **does** show
  its flash, **one tick later, at the scattered destination**, not where it stopped. The current engine puts the flash
  at the stop point on the stop tick. That is wrong for all Lightning-family beams (Lightning, Banner of Wrath, Storm
  bolts, Gaze of Mork after terrain, Warp Lightning, Doomwheel).
- The flash is drawn at the **aim height** (ground + 4 on flat ground, or a flier's height), not on the ground. The
  current engine draws it at height 0.
- The 30-segment visible limit (§3) is not in the current text or engine. It is visible only for Doomwheel bolts
  longer than ≈ 1,130 units. 🟡 The owner should decide whether to keep it (original look) or draw the whole beam.
- The double loop step of the segments on the arrival tick is not modelled. It is cosmetic.
- How the Doomwheel differs from cast Warp Lightning (visually):
  1. it starts at the unit position;
  2. three bolts start on the same tick;
  3. a failed bolt draws nothing;
  4. the bolt is never cut short by the Doomwheel's removal (a Wizard caster's removal cancels its bolts);
  5. its bolts can be far longer than 576, so the segment limit can show.

  Everything else (meshes, spacing, flash frames, bank, timing) is identical.

🟡 Open (no original screen capture was made):
- The look of the head and segments as rendered in the original (yaw quantisation as in `spell_visuals.md` §0) was
  not observed in game.
- The full warpfire flame playback (562–590) still needs its own research item.
