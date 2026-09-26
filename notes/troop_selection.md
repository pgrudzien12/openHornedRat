# Troop selection screen (Accept -> select regiments -> marching order -> mission)

Behavioral spec of the front-end screen that opens when the player presses **Accept** on the campaign map
(`notes/mission_selection.md` §4, §9.4), and of the sibling pages that share its window (debrief pages, bankruptcy) and
the roster book it can open. It is written from the front-end code of `WHSHR.EXE` plus the string/bitmap resources,
in the clean-room style of `notes/campaign.md`: behaviour, formulas, layouts and data sources, no code structure.
Money rules are **not repeated**: see `notes/campaign.md` §2.2–2.5 (price, mission fee, retainer, bankruptcy, done).

Status marks: ✅ read from code and consistent with resources; 🟡 inferred (reasoned from code or resources, not seen
running); ⬜ unknown. All coordinates are in the native 640×480 window. `H` is the pixel height of one line of the glue
body font (glue font slot 2; the heading font is slot 4). Original UI strings are cited by id (`BKTXT n`, `BRTXT n`), not
copied, except the short button/column labels already quoted in earlier notes.

## 1. Entry, modes and exit

### 1.1 Entry from the map ✅

`Accept` on the map's Dietrich panel (`controlpanel=2`, slot 1) **or on a briefing's panel** (`controlpanel=1`, slot 1) opens the selection for the **currently highlighted mission
row**. Whenever the highlighted row changes the record is already copied into the "current mission" and the initial payment
is evaluated (prepaid, `notes/campaign.md` §2.3), so Accept does not need Brief first. Inputs:

| Input | Value |
|---|---|
| unit file | the company, `SAVE/ARMY.MRC` (all units in it are listed, hired or not) |
| mode | 0 (selection) |
| title text ids | the mission name id (`BRTXT 6xx`), used as `%s` in `BKTXT 400` / `401` / `403` |
| return window | the context that was on top of the stack when Accept pushed it (target of Abort): the map when opened by the map's Accept; when opened by a briefing's Accept, the briefing frame 🟡 (`notes/mission_selection.md` §5) |
| completion callback | none for selection: Done runs the "selection done" procedure of §5 |

If the file cannot be loaded, mode 0 skips the screen and runs Done immediately (used by scripts with no company) 🟡.

### 1.2 Open modes and internal pages ✅

One window class (`TroopWindow`, 640×480, sword cursor) shows six *pages*; the open mode picks the first page and the
callback:

| Open mode | Used by | First page | Notes |
|---|---|---|---|
| 0 | Accept on the map | P0 selection | pages P0 -> P1 |
| 1 | (P1 alone; no caller found) | P1 marching order | ⬜ probably an alternative entry |
| 2 | debrief wrapper "with debrief" | P2 debrief text -> P3 troops -> P4 balance | evaluator text shown only if the mission has one |
| 3 | debrief, troops first | P3 -> P4 | |
| 4 | glue `debrief:` (cash only) | P4 balance sheet only | |
| 5 | forced at open when the forced regiments cost more than coffers + prepaid | P5 bankruptcy | see §7 |
| 6, 7 | debrief wrappers "without debrief" / glue `debriefwithsummary:` | P2 (+P3 in 6, P4 in 7) | 6 and 7 behave as 2 for paging |

Pages: **P0** select regiments (6 per page), **P1** marching order, **P2** debrief text, **P3** debrief troop table,
**P4** balance sheet, **P5** bankruptcy. Debrief pages are cross-referenced in §6; the rest of this note is P0/P1/P5.

### 1.3 Presentation state at open ✅

- Palette: glue palette index **1** = `GLUEBOOK` + `WINDBOOK` (`notes/fonts_glue.md`; table: 0 STANDARD, 1 BOOK, 2 MAP,
  3 CAR, 4 MIND, 5 END, 6 TITL, 7 GAME, 8 OPT, 9 BK2). The roster book (§8) uses index 9 (BK2, regiment pictures). On
  leaving, index 2 (MAP) is restored.
- Music: `binary/music/tactical.mid`, **looping** (every glue and built-in tune is started with the repeat setter at 0 = forever; `notes/briefing_dialogue.md` §2.2) for every non-debrief page. Debrief mode 2
  plays `win.mid` or `lose.mid` by the mission result. This settles the `TACTICAL` track use in `notes/music.md`.
- A 250 ms timer (id 3) drives the auto-scroll of P1.

## 2. Screen composition (common to P0, P1)

| Element | Value | Status |
|---|---|---|
| Background | bitmap `TroopBook`, 640×480: a blank parchment page of an open book (green cover edge visible bottom/right, gold corner ornaments, thin double rule frame); everything else is drawn on it | ✅ (bitmap viewed) |
| Title | centred at x = 320, y = 25, black, **body font slot 2**. P0: `BKTXT 400` with the mission name; P1: `BKTXT 401`; debrief pages: `BKTXT 403` | ✅ |
| Buttons | four owner-drawn buttons 84×32 at y = 448: **Abort** (225, id 0x103, `BRTXT 307`; created only for open mode 0), **Done** (325, id 0x102, `BRTXT 304`), **Back** (425, id 0x101, `BRTXT 301`), **Next** (525, id 0x100, `BRTXT 300`) | ✅ |
| Button art | Abort = `BrownATabUp/Dn0`, Done = `GreenATabUp/Dn0`, Back = `BlueATabUp/Dn0`, Next = `RedATabUp/Dn0` (84×32 tabs: coloured leather with gold scroll trim); label centred, offset (4,3) released and (0,3) pressed; every enabled label is yellow and every disabled label light grey (192,192,192) | ✅ |
| Cursor | window default = sword; while Ctrl is held = help cursor; over P0 rows: pencil if the regiment can be toggled, "no pencil" otherwise; over P1 rows: open hand / closed hand while dragging, up/down arrows in the scroll zones | ✅ |

Cursor resource mapping ✅: the named `WHSHR.EXE` cursor groups are `SWORDCURSOR` (default),
`HELPCURSOR` (Ctrl), `PENCILCURSOR` / `NOPENCILCURSOR` (P0), `HANDOPENCURSOR` /
`HANDCLOSECURSOR` (P1), and `UPARROWCURSOR` / `DOWNARROWCURSOR` (P1 scroll zones). They are
32×32 monochrome cursor resources with their own hotspots; load them from the user's installation,
never substitute copied cursor artwork.

Colours are Win32 COLORREFs in the code (BGR); the values above are converted to RGB.

## 3. Page P0: regiment selection

### 3.1 Layout ✅

Six regiments per page, in file order; `pages = ceil(units / 6)` counting **every unit in the file** (hired or not).

```
y=25    title (centred)
y=50    column headers:  x=345 BKTXT 409 | x=425 BKTXT 410 | x=505 BKTXT 413      (fee | retainer | total)
row i   y_i = 50 + H + 4H*i   (i = 0..5), rows are 4H apart
          x=80   banner icon (§3.3)          x=45 ring mark when selected (65x45, drawn from y_i - H)
          x=65   rank icon centred at y_i+12 (SKULL0..4)
          x=105  line 1 (y_i):     "<name> <models> (<original size>)"
          x=105  line 2 (y_i + H): "<weapon>/<armour>"
          x=345 / 425 / 505 numbers, or x=345 a status text (§3.4)
below the last row on this page, y_t = 50 + 4H * rows_on_page:
          label BRTXT 303 right-aligned to x = 495, value "<n> <BKTXT 414>" at x = 505  (red if it exceeds available money)
y=400-2H  centred: BKTXT 5006 with (coffers + prepaid initial payment)
          x=45 (same y): BKTXT 613 when the selected count has reached the mission limit
y=400     centred, blue: BRTXT 314          y=400+H centred, blue: BRTXT 316
```

Each row is 4H tall for hit testing: `row = (click_y - 50) / (4H)`, valid for the first 24H (six rows).

### 3.2 Row content ✅

- **Line 1**: unit name; **models** = current models + routed models returned; **original size** in brackets (`s_orgsize`).
- **Line 2**: weapon name `BRTXT 200 + s_weponame`, a slash, armour name `BRTXT 100 + s_armr` (`notes/game_rules.md` §3.2).
- **Rank icon**: bitmap `Skull<n>` with `n = floor((s_pntval & 31) * 4 / 31)`: 0 for 0–7, 1 for 8–15, 2 for 16–23, 3 for 24–30,
  4 for 31. `s_pntval` grows by 7 per campaign promotion, so this is the promotion level. Sizes 9×10, 9×22, 21×22, 21×22, 15×18. 🟡 as to
  what the game calls it; the arithmetic is ✅.
- **Selected mark**: `RingMark` (65×45, a hand-drawn dark oval) drawn over the icons when the regiment is selected.
- **Numbers** (x = 345 / 425 / 505), each followed by the `BKTXT 414` unit: regiment price (models × price per model), retainer
  (10 % of the price), and the amount that will really be paid: the price if selected, else the retainer.

### 3.3 Icons ✅ / 🟡

The picture on the left is not a `*Pic` bitmap: those belong to the roster book (§8). The row shows the regiment's **banner
sprite**. Traced from the row-drawing code (one routine shared by P0, P1, P3 and the debrief lists), with `x` = 45 and `y` = the row
y (`y_i`, §3.1); `cy` = height of the row font:

| Element | Position (top-left unless noted) | Rule |
|---|---|---|
| Unit name line | (x + 60, y_i) | |
| Weapon / armour line | (x + 60, y_i + cy) | |
| Rank icon `Skull<n>` | centred on (x + 20, y_i + 12): left = 65 - w/2, top = y_i + 12 - h/2 | own bitmap size; `n` as in §3.2 |
| Banner sprite | (x + 35, y_i) = (80, y_i) | see below |
| `RingMark` (selected only) | (x, y_i - H) = (45, 0x32 + 4*cy*row) | `H` = height of the title line font; drawn after the row, so it lies over icon and text |
| Scroll backdrop `BookScroll<k-1>` | only when the row is drawn with a non-zero style (roster-book lists), never on P0 | |

Banner rule ✅: the unit record holds a banner sprite id (`banner:<name>` in the `.MRC`) and a frame number `n`. The front end keeps,
for each resident banner set, the header record of its **second** record (the first record's address plus one 16-byte record). That
second record supplies the size and the pixel address; frame `n` from the unit record is added only as a row offset in the sprite
atlas. All 903 `banner:` entries in the shipped `.MRC` files have `n` = 0, so the row always shows the **second frame of the
set** (the 16×24 marker, `notes/animations.md`), never the 72×104 HUD banner or the 32×32 marker. A unit whose banner id is not among
the resident sets shows no banner. The mock render was not made (no on-screen check); coordinates come from the code only, so the
visual check of the whole row is still open.

### 3.4 Status text and colours ✅

A row shows one status text at x = 345 **instead of** the three numbers when:

| Condition (checked in this order) | Text | Colour |
|---|---|---|
| not hired (`hired` = 0) | `BKTXT 415` | grey (127,127,127) |
| excluded by the mission (`excludeunits` list, up to 8) | `BKTXT 416`; `418` for whoami 29 and 31; `420` for whoami 13, 36, 37 | grey |
| destroyed (0 models, or artillery with fewer than 2) | `BKTXT 417` | red (255,0,0) |

Otherwise numbers in black. The unit name is grey if not hired, black if hired, red if destroyed. Forced regiments show
normally (they become hired at open, §4.1).

### 3.5 Bottom lines ✅

`BKTXT 5006` ("current coffers hold %d gold crowns") always; the total-cost value turns red when the total exceeds
`coffers + prepaid`. `BKTXT 613` ("Roster Full") appears at x = 45 once the selected count reaches the limit.
`BRTXT 314` / `316` are the two hint lines (select by click; Ctrl+click for details).

## 4. P0 interactions

### 4.1 Initial state ✅

At open, for every unit in the file: **forced** regiments (whoami 2 always, plus the mission's forced list, up to 8) become
`hired`, and `selected` unless destroyed; all others start `selected = 0` (their `hired` is unchanged). Prices are computed
for the current model counts. The selection list keeps selection order (§5), forced regiments first (file order).
If `coffers + prepaid` is less than the price of the forced-selected regiments the window opens on **P5** (§7).

### 4.2 Click on a row (no Ctrl) ✅

The row's regiment toggles if and only if it is: hired, **not forced**, **not excluded**, **not destroyed**. Then:

- currently unselected: if `count < limit` it is selected and appended to the selection list; otherwise the **refusal sound**
  (`glue/speech/B9.WAV`, 8-bit 11 kHz, 0.02–0.3 s) plays and nothing changes (`BKTXT 613` is already showing);
- currently selected: it is deselected and removed from the list (later entries shift up).

Any other row (not hired, excluded, destroyed, forced) ignores the click. The pencil cursor is shown over rows that are hired and not
destroyed, so forced and excluded rows show it although the click does nothing 🟡. After a toggle the page repaints and the
buttons re-enable (§4.4).

**Limit**: the mission limit is `maxselect` clamped to 8..38, default 13 (`notes/campaign.md` §2.1). The list holds at most 38.

### 4.3 Ctrl+click on a row ✅

Ctrl held (checked at click time) routes the click to the roster book instead of the toggle of §4.2: on P0 the row index (row height `4*cy`, first row at y = 0x32) picks the regiment among the rows actually shown; on P1 the list entry. The click does nothing if the row index is beyond the shown rows. The book opens in *hire/fire enabled, no coffers change* mode (mode flag 1 on P0/P1, 0 on P3) and the selection window is repainted when it closes. Pages P3 (debrief troops): read-only.

**Hire/fire button inside the book** (P0/P1 mode, "hire" flag toggles) ✅ traced:

- hire (`hired` 0 -> 1): the regiment is selected **immediately** through the same routine the plain click uses: if `count < limit` then `selected = 1` and it is **appended to the end of the selection list**; if the list is already full nothing is selected (regiment stays hired but unselected) and **no sound plays**.
- fire (`hired` 1 -> 0): `selected = 0` and it is removed from the list (later entries shift up), whether or not it was selected.
- The roster-full refusal sound (`B9.WAV`) is played only by the plain-click path (§4.2); the book path never plays it, and shows no message.
- The coffers are not touched on P0 (the campaign-money variant of the same button, used in the army-records window on the map, pays/refunds; not this path).
- ✅ Enabling rules (traced, refreshed after every page change and every toggle):

| Condition | Hire/Fire button |
|---|---|
| Label | shows Hire (`BRTXT 319`) when `hired` = 0, Fire (`BRTXT 320`) when `hired` = 1; always follows the current flag |
| Regiment type `forHire` = 0 (RMYI, `notes/campaign.md` §4.5) | disabled (all modes) |
| `forHire` = 1, selection variant (no coffers change) | **enabled**, whatever the regiment's state |
| Forced by the mission, excluded by the mission, destroyed | **not tested**: button stays enabled if `forHire` = 1 (forced regiments of whoami 2 etc. are `forHire` = 0 anyway; a mission-forced ordinary regiment can be fired in the book) |
| Selection list full | **not tested**: enabled; hiring then leaves the regiment hired but unselected (above) |
| Unaffordable | not tested in the selection variant (no coffers involved) |
| Hire-only (caravan) variant, hired when the book opened | disabled (cannot be fired) |
| Hire-only, not hired at open, currently not hired | enabled only if coffers >= the price (else disabled) |
| Hire-only, not hired at open, hired this visit | enabled (un-hire for a refund) |

Abort exists only in the variants with the Hire/Fire button. Only `forHire` is read from the roster type; the mission-record forced/excluded lists are not consulted by the book at all.

### 4.4 Button rules ✅

| Page | Next | Back | Done | Abort |
|---|---|---|---|---|
| P0 | enabled if `page < pages-1` | enabled if `page > 0` | enabled if `selected count > 0`; the action also needs total cost <= coffers + prepaid, else it does nothing | always (open mode 0 only) |
| P1 | disabled | enabled (back to the last P0 page) | always | always (mode 0 only) |
| P5 | disabled | disabled | enabled | not created |

- **Next/Back on P0** change page only.
- **Done on P0** -> P1 when allowed. **Done on P1** -> selection done (§5).
- **Abort**: if anything is selected, a Yes/No confirmation box (`BRTXT 308`, question icon, title "Warhammer") must be accepted;
  with nothing selected there is no confirmation. Yes discards the in-memory selection and reopens the return window (the map).
  Nothing is charged; hires done in the roster book were already written to `ARMY.MRC` (§8).
- No keyboard shortcuts on this window except Ctrl (a click modifier: Ctrl+click opens the roster book, §4.3). The global key handling is the hidden cheat-code detector and the application accelerator table only (`notes/mission_selection.md` §4.3); Enter, Esc and Space do nothing. ✅

## 5. Page P1: marching order and Done

### 5.1 Layout ✅

The selected regiments appear in a vertical list, 7 visible at a time, in **selection order**; this order is the marching order.

```
title BKTXT 401
list rectangle x = 95..565; row k (0..6):  y_k = H + 50 + 4H*k
   row strip: bitmap BookScroll0 (408x42 parchment strip) at (145, y_k - 10)
   order number: bitmap BookScroll2 (56x42 square scroll) at (83, y_k - 10) with the 1-based index centred in it
   contents as P0 line 1 / line 2 / icons, with the row's x = 157 (text from x = 217), first text line at y_k
hints: BRTXT 315 (centred, blue, y = 400) and BRTXT 316 (y = 400 + H)
```

The first visible entry is clamped so the last page of the list is full when there are more than 7 entries.

### 5.2 Reorder and scroll ✅

- **Drag**: pressing on a row picks that regiment up; the strip (`BookScroll0`) with its contents follows the cursor while the
  original row is hidden; the row under the cursor is drawn on `BookScroll1` (drop target highlight). **A second click drops it**
  at the row under the cursor; the list is reordered by moving the regiment and shifting the entries between. (`BRTXT 315`:
  click to pick up, click again to drop.) Cursor: open hand idle, closed hand while carrying.
- **Scroll**: when the list has more than 7 entries, holding the mouse in the top zone (y < 51) scrolls up and in the bottom
  zone (y 420–440) down, one entry per 250 ms timer tick, including while dragging.
- Two sounds named `MarchOrderMove` and `MarchOrderMoveDone` sit next to this code; their use was not found ⬜ (probably drag
  and drop cues).

### 5.3 Selection done ✅

Done on P1 performs, in this order (money formulas in `notes/campaign.md` §2.3):

1. coffers += prepaid initial payment; coffers -= total cost (selected fees + retainers of hired-but-unselected);
2. mark the current mission **taken** (`notes/campaign.md` §7.1);
3. write `SAVE/MARCH.MRC` with the selected units **in list order** (🟡 after putting routed models back into ranks and resetting the counters);
4. roster flags: `inArmy` for every unit in the file, `inMarch` for the selected ones (`RMYI`, `notes/campaign.md` §3);
5. write `ARMY.MRC` and `PLAY.MRC`; drop non-hired regiments from the company and clear unused reinforcements;
6. close the window and run the mission's `setmissionscript`, which autosaves and starts the battle (`notes/campaign.md` §5). A record **without** a mission script but with a battle (7 of the 64 shipped records: `MissionSZWindow` #3, `MissionWE45Window` x2, `MissionMSWindow`, `MissionEctsWindow` x3) starts that battle directly; when its debrief is done, control goes to the after-mission caravan (`gocaravan:select` behaviour) instead of resuming a script. ✅ (code; the same rule as panels 6/7/10, `notes/mission_selection.md` §4.2)

Deployment `dir`/`x`/`y` in `MARCH.MRC` is not set here: the battle's deployment step places units (`notes/game_rules.md`, section "Missions and objectives", `DeployTroops`).
🟡 whether the list order affects initial placement.

## 6. Debrief pages (same window) ✅ (layout) / see `notes/campaign.md` §5 for effects

| Page | Content |
|---|---|
| P2 | title `BKTXT 403`; the first evaluator line in the heading font, centred at y = 8H + 50; then the evaluator's lines and up to two more result lines, centred, one per H |
| P3 | headers `BKTXT 404` (x = 345), `405` (405), `406` (465), `412` (530); six units per page with the P0 row layout, then kills (`s_kills`), dead, wounded and experience gained (from `debrief.dbf`, casualties split by the 65/35 rule); `BKTXT 611` if the wounded could not be recovered |
| P4 | `BKTXT 5005` heading, then the cash program's lines (`notes/campaign.md` §2.5) with label at x = 45 and amount right-aligned to x = 390 (`BKTXT 419`, suffix), then `BKTXT 5007` / `5008` current coffers |

Navigation follows §1.2; Done runs the debrief-done procedure.

## 7. P5: bankruptcy ✅

Triggered at open (mode 0) when `coffers + prepaid < price(forced regiments still alive)`. No background rows: the TroopBook
page shows `BKTXT 601` in the heading font (y = 8H + 50, centred), `BKTXT 602` with the coffers, `BKTXT 603` with the
required amount. Only Done exists; it clears the background and returns to the front end, ending the campaign (🟡 destination).

## 8. Roster book ("Army Records" window) opened by Ctrl+click

Same code serves the caravan books (`ArmyBook`, `HireOnlyArmyBook` hotspots). It is a **separate screen**; only the
parts the selection screen depends on are specified here. Background `ArmyBook` (640×480), palette 9 (BK2), one regiment
per page in file order.

| Element | Behaviour |
|---|---|
| Buttons (84×32, y = 448) | **Stat/Info** (x = 14, id 0x105, `BRTXT 321` / `322`), **Hire/Fire** (x = 104, id 0x106, `BRTXT 319` / `320`), **Abort** (x = 194, id 0x107, `BRTXT 307`), **Done** (x = 350, id 0x102, `BRTXT 304`), **Back** (x = 440, `BRTXT 301`), **Next** (x = 530, `BRTXT 300`). Hire/Fire and Abort exist only in the "may hire" variant, which is what selection uses |
| Keys | PageUp/PageDown = previous/next regiment, Home/End = first/last |
| Left page | name, cost line (`BKTXT 501` "cost / retainer", or `509` for the fee of a not-yet-hired regiment in hire-only mode), experience (`BKTXT 500`), regiment picture (`*Pic` bitmap chosen by whoami from a 38-entry table; `ForHireStamp` 98×61 on regiments not hired), `BKTXT 502` active/wounded counts |
| Right page | "Statistics" (`BKTXT 503`: M, WS, BS, S, T, W, I, A, Ld with `BRTXT 700–717` labels and the nine stat bytes; leader block at the same layout) or "Information" (`BKTXT 504`: armour/weapon lines and a description text from `BKTXT.DLL` RCDATA keyed by whoami); a banner/leader-portrait box 72×104 |
| Hire/Fire enabled | rule table in §4.3 (only when the regiment's roster `forHire` flag is set; label is Hire when not hired, Fire when hired. In *hire-only* (caravan) mode: a regiment already hired when the book opened cannot be fired, one hired during this visit can be un-hired for a refund, and hiring needs enough coffers; in the selection variant no coffers change) |
| Effect of Hire/Fire | toggles `hired`. Firing also deselects the regiment; hiring also **selects** it (subject to the limit). In the hire-only variant the price is charged or refunded |
| Done | if anything changed, writes `ARMY.MRC`; in hire-only mode also rewrites `MARCH.MRC` from the selection list; closes |
| Abort | restores the `hired` flags from the snapshot taken at open; closes |
| Reinforcements | if a regiment has reinforcements (`BKTXT 505`, `507` available, `508` take, `REINFARROW*`, `REINFBUTTON*`, `REINFSCROLL`) a small sub-window lets the player take some; rules in `notes/campaign.md` §2.4 |

### 8.1 Per-whoami name tables (WHSHR.EXE)

Two 38-entry pointer arrays of resource names, indexed by whoami: picture bitmap (`BITMAP.DLL`, `RT_BITMAP`) at VA 0x5B9550 and description text (`BKTXT.DLL`, `RT_RCDATA`) at VA 0x5B9230. Every name resolves to a resource (`scripts/roster_book_check.py`). Whoami 32 has no picture (null pointer) and uses the `NullText` entry.

| whoami | Pic bitmap | Text RCDATA |
|---|---|---|
| 0 | `VanheimPic` | `VanheimText` |
| 1 | `RagnarsWolvesPic` | `RagnarsWolvesText` |
| 2 | `Grudgebringers1Pic` | `GrudgebringersText` |
| 3 | `Grudgebringers2Pic` | `GrudgebringersText` |
| 4 | `BlackAvengersPic` | `BlackAvengersText` |
| 5 | `GreatswordsPic` | `GreatswordsText` |
| 6 | `ReiksguardPic` | `ReiksguardText` |
| 7 | `LeitdorfPic` | `LeitdorfText` |
| 8 | `WoodElfArchersPic` | `WoodElfArchersText` |
| 9 | `DwarvenSlayersPic` | `DwarvenSlayersText` |
| 10 | `DwarvenHammerersPic` | `DwarvenHammerersText` |
| 11 | `IronBreakersPic` | `IronBreakersText` |
| 12 | `IronBreakersPic` | `IronBreakersText` |
| 13 | `GyrocopterSquadronPic` | `GyrocopterSquadronText` |
| 14 | `CannonCrewPic` | `ImperialCannonCrewText` |
| 15 | `CannonCrewPic` | `CannonCrewText` |
| 16 | `MortarCrewPic` | `MortarCrewText` |
| 17 | `MortarCrewPic` | `MortarCrewText` |
| 18 | `CelestialWizardPic` | `CelestialWizardText` |
| 19 | `BrightWizardPic` | `BrightWizardText` |
| 20 | `AmberWizardPic` | `AmberWizardText` |
| 21 | `CarlssonPic` | `CarlssonText` |
| 22 | `CarlssonPic` | `CarlssonText` |
| 23 | `DwarfWarriorsPic` | `DwarfWarriorsText` |
| 24 | `DwarfWarriorsPic` | `DwarfWarriorsText` |
| 25 | `VolleyGunPic` | `VolleyGunText` |
| 26 | `NulnHalberdiersPic` | `NulnHalberdiersText` |
| 27 | `MercCrossbowmenPic` | `MercCrossbowmenText` |
| 28 | `LongbowsPic` | `LongbowsText` |
| 29 | `CeridanPic` | `CeridanText` |
| 30 | `DwarfCrossbowPic` | `DwarfCrossbowText` |
| 31 | `DwarfEnvoyPic` | `DwarfEnvoyText` |
| 32 | `(none)` | `NullText` |
| 33 | `DwarfWarriorsPic` | `DwarfWarriorsText` |
| 34 | `TreemanPic` | `TreemanText` |
| 35 | `CarlssonPic` | `CarlssonText` |
| 36 | `GyrocopterSquadronPic` | `GyrocopterSquadronText` |
| 37 | `GyrocopterSquadronPic` | `GyrocopterSquadronText` |

## 9. Data versus front-end constants

Legend: **DATA** = comes from resources/files; **TABLE** = front-end constant that must be one documented table (per
`notes/data_driven_audit.md`); **DERIVED** = computed from a font or bitmap size, not a literal.

| Item | Class | Source |
|---|---|---|
| Unit list, names, models, sizes, stats, weapon/armour ids, banner id/frame, `s_pntval`, `s_size`, `s_routed`, `whoami` | DATA | `SAVE/ARMY.MRC` (+ `PLAY.MRC` for flags) |
| Price per model, `forHire`, artillery, reinforcements | DATA | roster flags (`RMYI`) and stats |
| forced list (8), excluded list (8), `cash` line | DATA | mission record |
| `maxselect` | TABLE | process command-line option; default 13, clamp 8..38 (`notes/campaign.md` §2.1). The WND.DLL mission record does not carry it. |
| Mission name | DATA | `BRTXT 6xx` via the record's `res` |
| All labels and messages | DATA | `BKTXT` ids in §§2–8, `BRTXT` ids for buttons/hints/weapon/armour names |
| Background and widget bitmaps: `TroopBook`, `RingMark`, `Skull0..4`, `BookScroll0..2`, `Red/Blue/Green/BrownATab{Up,Dn0}`, `ArmyBook`, `ForHireStamp`, `Reinf*` | DATA (named bitmaps in `BITMAP.DLL`) | the *name* per widget is a TABLE |
| Regiment `*Pic` and description text per whoami | DATA + TABLE ✅ | 38-entry name tables in the executable (§8.1: pictures VA 0x5B9550, texts VA 0x5B9230); bitmaps in `BITMAP.DLL`, texts in `BKTXT.DLL` |
| Button positions, sizes, ids, enable rules per page | TABLE | §2, §4.4 |
| Row layout (x = 45/65/80/105/345/425/505, y = 25/50/400, 6 rows, 4H pitch, 7 visible in P1, list rect) | TABLE | §3.1, §5.1; H is DERIVED from the body font |
| Skull index formula, status precedence, colour rules | TABLE | §3.2, §3.4 |
| Palette index 1 = BOOK pair; music `tactical` / `win` / `lose` | TABLE | §1.3 |
| Refusal sound `B9` | TABLE | §4.2 |
| Ring mark position, order-badge position, drag behaviour | TABLE | §3.1, §5 |
| Font slot 2 (body) / 4 (heading) -> `.FON` file | TABLE 🟡 | mapping of slot to font file not written down (`notes/fonts_glue.md`) |

Nothing on this screen is placed by `WND.DLL` scripts (the window is built in code); the scripts only provide the Accept
target and the mission record. This is a *front-end-owned screen*, so its constants are one module, not per-mission data.

## 10. Suggested engine design

Follows `docs/testing.md` (BDD, public behaviour only) and the existing `SceneMachine` style.

**Model (pure, stdlib, no pygame)** `TroopSelection`, built from: the company units, the mission record's forced/excluded lists,
`maxselect`, `cash` (via the existing economy code), coffers, strings. It owns:

- `rows(page)` -> row view data: name line, weapon/armour line, models, orig size, rank (skull index), banner ref, price, retainer,
  total, status (`available`, `not_hired`, `excluded(text_id)`, `destroyed`), `selected`, `toggleable`;
- `selected` in order, `limit`, `roster_full`, `total_cost`, `affordable`, `bankrupt`;
- commands: `toggle(unit)`, `next_page`, `prev_page`, `done()` (P0 -> P1 if allowed), `move(list_index, new_index)`, `scroll`, `confirm()`;
- result: an immutable `Deployment` (ordered units, money delta, mission taken) consumed by `CampaignState`.

**Scene** `TroopSelectionScene(campaign, mission_ref)` with phases `SELECT`, `MARCH_ORDER`, `BANKRUPT`:

| Event string | Effect |
|---|---|
| `page:next` / `page:back` | P0 paging; from P1 `page:back` returns to P0 last page |
| `toggle:<unit>` | §4.2 (returns a refusal event `refused` for the sound when the limit is reached) |
| `inspect:<unit>` | push `RosterBookScene` (Ctrl+click), returns here on close |
| `done` | SELECT -> MARCH_ORDER (if allowed); MARCH_ORDER -> commit and `Transition` to the mission-script runner / battle briefing |
| `pickup:<row>` / `drop:<row>` / `scroll:up|down` | §5.2 |
| `abort` / `abort_confirmed` / `abort_cancelled` | confirmation, then `Transition` back to `MissionMapScene` |

Frontend: `TroopSelectionView` reads the layout table of §9 (constants in one module, `H` from the loaded font) and draws only; it
sends the events above. Bitmaps via the `pe-bitmap` loader (`notes/data_driven_audit.md` §3.1), strings via `BKTXT`/`BRTXT`.

Suggested scenarios: forced regiments start selected and cannot be toggled; a not-hired regiment cannot be selected and shows the
"for hire" status; selecting beyond the limit is refused and reports it; deselecting shifts the list; Done is disabled with nothing
selected and does nothing when unaffordable; total = fees + retainers and matches `notes/campaign.md` §2.3; bankruptcy opens the
bankrupt phase; marching-order drag moves an entry and keeps the others' relative order; committing writes the ordered list, the
money delta and marks the mission taken; abort with something selected requires confirmation and changes nothing. Run them on
**several mission records** (e.g. one with forced units, one with exclusions) to avoid hardcoding the first mission.

## 11. Open questions
> **Tracked on GitHub**: these open items are tracked as issue #26 (`topic:campaign-glue`). Kept here for
> reference; a follow-up pass (issue #45) will verify nothing was lost in the move.


- ✅ Banner frame on the row: second record of the set (§3.3). Placement offsets of RingMark / rank icon / banner are read from the draw code (§3.3); 🟡 only an on-screen comparison is missing.
- ✅ Ctrl+click hire appends to the selection list when room, no roster-full sound (§4.3). ✅ book button enabling: only `forHire` (plus hire-only rules); forced/excluded/destroyed/full list/coffers are not checked in the selection variant (§4.3). 🟡 only an in-game confirmation is missing.
- ⬜ Font slot -> `.FON` file mapping; how the WinG palette mapping treats bitmaps whose embedded colours match `GLUEREND` while
  the screen runs on the BOOK palette (`notes/fonts_glue.md`).
- ⬜ Use of the `MarchOrderMove` / `MarchOrderMoveDone` names. (Resolved: `tactical.mid` loops, §1.3.)
- ⬜ Open mode 1 (P1 alone) and the destination after Done on P5.
- ⬜ Whether list order affects initial deployment positions in the battle.
- ✅ Layout of the reinforcements sub-window: `notes/builtin_widgets.md` §2.4 (implemented, `notes/glue_engine_integration.md` GEI7g).
- ✅ Panels 6, 7, 10 (Accept starts the mission script, or the battle, without this screen) are **never opened by any shipped script**; details in `notes/mission_selection.md` §4.2 / §9.4. Nothing to implement for the campaign.
