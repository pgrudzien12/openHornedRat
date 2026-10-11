# Deployment-zone flags

Public behavioural report for the implementer's question about the waving white flags that mark the deployment zone.
Companions: `deployment.md` (deployment phase, Start flag), `movement_boundaries_route_finding.md` (boundary roles),
`spell_visuals.md` §0 (sprite anchors, colour maps), `FORMATS.md`.

**Correction to an earlier lead:** the flags are **GENBATT frames 106–109**. (An earlier reading of the GENBATT sheet
put the flags at 114–117; those are arrow bundles.)

## 1. Art

| Frames (GENBATT) | Size | Anchor X/Y | Bank | Effective map | Look |
|---|---|---|---|---|---|
| 106, 107, 108, 109 | 32 × 32 | 16, 32 (bottom centre of the frame) | 0 | 8 (the frame's own) | a white pennant on a brown pole, four waving phases |

Not directional: the same frame is drawn from any camera angle. Each flag is one sprite, drawn like the other battle
sprites (same pipeline, `spell_visuals.md` §0; the anchor includes the transparent padding).

## 2. Playback (per flag)

- One frame per battle tick, cycling **106 → 107 → 108 → 109 → 106 …** (4-tick loop).
- **Each flag starts at a random one of the four frames** (one random draw at its first update), so neighbouring
  flags are **out of phase**. After the start, the cycle is a plain loop, not ping-pong.
- **While the game is in the deployment phase** (and not in its "pause/confirm" state), each flag finishes every
  4-frame cycle by looping back to 106.
- **When the battle starts** (the Start flag), each flag **finishes the 4-frame pass it is in** (at most 3 more
  ticks), then **sinks into the ground at 2 world units per tick**, still waving 106–109 for **12 more ticks**, and is
  then removed. Total from Start to disappearance: 12 + up to 4 ticks. They do not fade; the sprite just goes down
  (its height above the terrain falls 2, 4, …, 24 units).

## 3. Placement

- The flags are laid out **once**, on the first update after the battle loads (before the player sees the field).
- Boundaries used: every boundary that is **active and has the deployment role** (`bnd_DEPLOYMENT`; both flags set).
  Nothing else (no inverted variant, no start-node outline).
- **Spacing is one thirty-second of the total length** of all those boundaries' segments: `s = Σ segment lengths / 32`.
  So every battle gets about **32 flags in all**, however large the zone.
- Walk the boundaries in file order, and within each boundary its segments in file order, with a running remainder
  that **carries over from segment to segment and from boundary to boundary**:
  1. the first flag is at the **start of the first segment** (offset 0);
  2. in a segment of length L with starting offset o (the carry), flags stand at distances `o, o + s, o + 2s, …` along
     the segment while the distance is **strictly less than L**;
  3. the carry into the next segment is `(last distance + s) − L`; a segment shorter than the carry places no flag.
- Each flag stands at its (x, y) on the **terrain** (its height above the terrain is 0), so on slopes flags follow the
  ground. A flag placed on a boundary outside the camera view is still animated; it is just not drawn.

## 4. Test vectors

Rectangular deployment boundary, four segments of 100 units (Σ = 400, s = 12.5), one boundary:

| Segment | Flag distances along it |
|---|---|
| 1 (0 → 100) | 0, 12.5, 25, …, 87.5 (carry out 0) |
| 2 | 0, 12.5, …, 87.5 |
| 3 | 0, 12.5, …, 87.5 |
| 4 | 0, 12.5, …, 87.5 (the flag that would stand exactly at the end of segment 4 is not placed, 400 is not < 400) |

32 flags. Two boundaries of lengths 30 and 50 (Σ = 80, s = 2.5): 12 flags on the first (0 … 27.5), carry `(27.5 + 2.5) − 30 = 0`,
then 20 on the second.

| Before | Action | After |
|---|---|---|
| battle just loaded | first update | flags exist along the zone, each with a random frame in 106–109 |
| flag showing frame 107 (deployment) | 4 ticks | 108, 109, 106, 107 … |
| deployment, flag showing 108 | the player presses Start | 109, then at the end of the pass: height above ground 0 → −2 per tick, frames 106–109 ×3, gone |

## 🟡 Open

- Whether the flags are depth-sorted and hidden behind scenery exactly like unit figures (they go through the same
  sprite path; no special case was found).
- The state of the flags during a pause/confirmation in deployment (a pause appears to start the sinking; not checked).
- No running original-game capture was made.
