# Unit-script control: condition word, script stack, repeat loops, events, script jumps

Public implementation report (batch 2 of the interpreter requests, GitHub #3). Companion to
`skip_if_true.md` and to "Unit behaviour scripts and events" in `game_rules.md`. Behaviour only; script listings
are produced by `python3 -m whshr scripts <installation>` from the user's own installation. "Word" = one 32-bit
script word; `pc` = word index of the opcode being executed.

## 1. Per-unit interpreter state

| State | Shape | Notes |
|---|---|---|
| condition word | 16 bits, persistent per unit | **bit 2 (value 4) is the condition** read by `If`/`IfNot`/`LoopIfTrue`/`LoopIfFalse`/`YieldIfTrue`/`SkipIfTrue`/`IfGotoScript`. Other known bits: 8 = a deferred script switch is pending (set by the `SwitchScript` family, cleared by `ClearCondFlags 8`), 0x20 = switches are refused, 0x10 = a script-level flag (`SetCondFlags 16`/`TestCondFlags 16`), 1 = set by the `SetCondFlags 0x8001` init sequence (🟡 meaning), 0x8000 = cleared by `ClearCondFlags 0x8000` (🟡 meaning). |
| script stack | 64 words, grows downwards, per unit | shared by `PushPC`/`Loop*`, `RepeatStart`/`RepeatNext` and `GosubScript`/`ReturnGosub` |
| event queue | count + list of event records (code, argument, ...) | **LIFO**: a new event is put at the head, `GetEvent` takes the head (most recent first) |
| current event | one record or none | set by `GetEvent`, read by `CaseEvent` and by opcodes that use the event's argument |

**There is one condition word, not two.** `SetCondFlags`/`ClearCondFlags`/`TestCondFlags` operate on the very word
whose bit 2 is the result that `Test*`/`Find*`/`Attack*`/`Flee*` write and `If`/`Loop*` read. An engine with
separate `cond_flags` (result) and `cond_bits` (word) should merge them: `cond == bool(word & 4)`.

**The condition does not survive a tick boundary.** At the start of every tick, before any script word runs, the
interpreter checks for a pending player order: the condition is set to "an order was applied this tick" (false on
almost every tick) and, if true, the unit restarts at its restart point. So the first instruction executed in a
tick always sees the condition **false**, except right after an applied order. The rest of the word (bits 8, 0x10,
...) does persist. Shipped scripts always test the condition in the same tick that set it (for example
`PushPC; Yield; ...; TestUnitFlags2 4; LoopIfTrue`).

## 2. `SetCondFlags` 0x2E / `ClearCondFlags` 0x2F / `TestCondFlags` 0x30

(a) Two words each; operand = 16-bit mask.
(b)/(c)
- `SetCondFlags m`: if `m` has bit 15, **replace** the word with `m & 0x7FFF`, otherwise `word |= m`.
  So `SetCondFlags 4` = "condition true", and `SetCondFlags 0x8001` resets the word to 1 (condition false, no
  pending switch).
- `ClearCondFlags m`: `word &= ~m` (bit 15 is not special here: `ClearCondFlags 0x8000` clears bit 15).
- `TestCondFlags m`: condition := `(word & m) != 0` (**any** bit), computed on the word before the update; only bit 2
  changes.

(f)

| Before (word) | Instruction | After (word) |
|---|---|---|
| 0x0018 | `SetCondFlags 4` | 0x001C |
| 0x001C | `SetCondFlags 0x8001` | 0x0001 |
| 0x001C | `ClearCondFlags 8` | 0x0014 |
| 0x0010 | `TestCondFlags 16` | 0x0014 (true) |
| 0x0004 | `TestCondFlags 16` | 0x0000 (false) |

## 3. `RepeatStart` 0x0A / `RepeatNext` 0x0B

(a) `RepeatStart N`: two words, `N` = iteration count. `RepeatNext`: one word.
(b) Neither reads or writes the condition.
(c)
- `RepeatStart N`: push `pc + 2` (the body start), then push `N`; continue at `pc + 2`.
- `RepeatNext`: pop the count and subtract 1 (16-bit). If the result is non-zero, push it back and jump to the body
  start (the word below it on the stack, which stays there). If it is zero, pop the body start and continue at
  `pc + 1`.
- So the body runs exactly `N` times for `N >= 1`. Nesting works because everything is on the stack (an inner
  pair pushes and pops above the outer one), and it can enclose or sit inside a balanced `PushPC`/`Loop` pair.

Worked example, library script 105 (identical in every mission DLL):

```
14  PushPC                 stack: [14]
15  RepeatStart 2          stack: [14, 17, 2]
17  SetWait 10
19  IfTargetInChargeReach
20  IfGotoScript 160
22  Wait
23  TestUnitFlags 16
25  If
26    Restart
27  EndIf
28  RepeatNext             1st: pop 2 -> 1, push 1, jump 17.  2nd: pop 1 -> 0, pop 17, go to 29
29  RefreshRouteToTarget   stack: [14]
30  Loop                   pop 14 -> PushPC pushes it again
```

`PushPC` pushes **its own** word index, so `Loop` returns to the `PushPC`, which pushes again.

(d)
- `N = 0` wraps to 65535 on the first `RepeatNext`, so the body runs 65536 times. Shipped operands are only
  2 (134 uses), 10 (81), 20 (27), 3 (5) and 5 (1).
- Leaving the body by a jump (`IfGotoScript`, `GotoScript`, ...) leaves the two repeat words (and any `PushPC`
  word) on the stack. They stay until `ResetStack` (0x02), `Restart` (0x03, restores the depth saved at the restart
  point) or unit init. Script 105 does this on every charge, and script 160 does not clear the stack, but 105
  begins with `ResetStack` each time it is re-entered.
- Stack full (64 words): the push is dropped (a debug message only). Popping an empty stack is not guarded. Neither
  happens in shipped data; treat both as errors.

(f)

| Before | Instruction | After |
|---|---|---|
| pc 15, stack [] | `RepeatStart 2` | pc 17, stack [17, 2] |
| pc 28, stack [17, 2] | `RepeatNext` | pc 17, stack [17, 1] |
| pc 28, stack [17, 1] | `RepeatNext` | pc 29, stack [] |

## 4. `DrainEvents` 0xE2

(a) One word, no operand.
(b) It writes the condition (true after a non-empty drain, otherwise unchanged).
(c) While the queue is not empty: consume the current event (as `ConsumeEvent`: release it and set the condition to
"queue not empty"), then take the next event from the queue into the current slot (as `GetEvent`). Net result:
- every queued event is discarded **without being handled**;
- the **last event taken stays as the current event, not yet consumed** (with LIFO order this is the oldest
  queued one);
- the queue is empty, and the condition is true if the loop ran at least once.

If the queue is empty on entry, nothing happens: the current event and the condition are unchanged.

Worked example: library event handler 101 (player units):

```
 2  PushPC
 3  GetEvent
...
47  CaseEvent 4            "attack this target"
49    TakeEventTarget
50    IfSwitchScriptHigh 105
52    DrainEvents          drop everything else queued this tick
53    Break -> L69
69  L69:
70  ConsumeEvent           releases the last drained event; condition := queue not empty = false
71  LoopIfTrue             not taken
72  ReturnInterrupt
```

So once a unit accepts an attack order, every other pending event is thrown away and the handler ends.

(d) The original assumes that a current event exists when the queue is non-empty, because it always runs inside a
handler after `GetEvent`. An engine should treat "no current event" as nothing to release. 186 uses, all as
`...; DrainEvents; Break` inside `CaseEvent` arms of event handlers.

(e) `GetEvent` 0x68, `ConsumeEvent` 0x69, `CaseEvent` 0x6A, `ClearEvent` 0xE5.

(f)

| Before | After `DrainEvents` |
|---|---|
| current A, queue [] , cond false | unchanged (current A, cond false) |
| current A, queue [B] (head first) | A released; current B (unreleased), queue [], cond true |
| current A, queue [C, B] | A, C released; current B, queue [], cond true |

## 5. `ClearEvent` 0xE5

(a) One word, no operand.
(b) It neither reads nor writes the condition.
(c) It forgets the **current event only**: the current slot becomes "none". The queue is untouched, and the event is
**not released** (unlike `ConsumeEvent`). There is no other remembered-event slot.
Its purpose is visible from the following opcode: `FireAtTarget` (0x84) and `CastPending` (0x93) take an extra
argument from the current event when there is one; with no current event they use "none". Library helpers 115, 117
(shooting) and 142 (casting) do `ClearEvent; FireAtTarget` and `ClearEvent; CastPending`, so they always fire or
cast without an event-supplied argument (🟡 what that argument selects in the fire/cast routines).

(d)
- Pool side effect: event records come from a shared pool of 126 records. A record forgotten by `ClearEvent`
  stays allocated until its unit restarts (`Restart` releases every record addressed to the unit and empties its
  queue). When the pool is full, new events are silently dropped. This is minor; an engine with per-unit Python
  lists can ignore it.
- `CaseEvent`/`ConsumeEvent` after `ClearEvent` with no `GetEvent` in between would fault in the original. No
  shipped script does this: the three helpers return with `ReturnGosub` straight after.

(f)

| Before | After `ClearEvent` |
|---|---|
| current A, queue [B] | current none, queue [B] |
| current none | current none |

## 6. `IfGotoScript` 0x43 (`IfNotGotoScript` 0x44, unused)

(a) Two words; operand = script id (a mission script 0..N-1 or a library id 100–170, looked up in the unit's
mission DLL).
(b) It reads the condition and does not change it.
(c) If the condition is true (0x44: false), switch **immediately**: the unit's current script := operand,
execution continues **in the same tick** at word 0 of the new script. If not taken, continue at `pc + 2`.
**Untouched:** the script stack (no push, no reset, so pending `PushPC`/repeat words stay; see §3 (d)), the restart
point, the wait timer, the interrupt (event-handler) script and the rest of the condition word.
It behaves exactly like the unconditional `GotoScript` 0x0C. Contrast this with the `SwitchScript` family
0x0D–0x10, which only **record** a pending switch (bit 8 of the word, refused while bit 0x20 is set; 0x0E also
needs the condition) that is applied at the end of the tick or at `ReturnInterrupt`.

Worked example: script 105 above, word 20. If `IfTargetInChargeReach` set the condition, the unit jumps to library
script 160 (`ChargeTarget; If ... ; GotoScript 163`) in the same tick, with the stack still `[14, 17, count]`.
Otherwise it continues at word 22 (`Wait`).

(d) An id the DLL does not have yields no script in the original (a fault); treat it as an error. 138 uses, all of
the form `IfTargetInChargeReach; IfGotoScript 160` (library 105, 158, 159 and some mission scripts).

(f)

| Before | Instruction | After |
|---|---|---|
| script 105, pc 20, cond true, stack [14,17,2] | `IfGotoScript 160` | script 160, pc 0, cond true, stack [14,17,2], same tick |
| script 105, pc 20, cond false | `IfGotoScript 160` | script 105, pc 22 |

## 7. Unit-flag opcodes 0x22–0x2B (batch 1 confirmations)

`unit_flags` and `unit_flags2` are two independent 32-bit words of the unit. Every opcode is two words with a 32-bit
mask operand, and every test is **any bit** (`(flags & mask) != 0`), never "all bits".

| Opcode | Effect |
|---|---|
| `WaitWhileUnitFlags` 0x22 / `WaitWhileUnitFlags2` 0x27 | if any mask bit is set: stop for this tick **without advancing** (the same word runs again next tick), otherwise continue at `pc + 2` |
| `WaitUntilUnitFlags` 0x23 / `WaitUntilUnitFlags2` 0x28 | if no mask bit is set: stop without advancing, otherwise continue |
| `TestUnitFlags` 0x24 / `TestUnitFlags2` 0x29 | condition := any bit set (same bit 2 as everything else) |
| `SetUnitFlags` 0x25 / `SetUnitFlags2` 0x2A | `flags \|= mask` |
| `ClearUnitFlags` 0x26 / `ClearUnitFlags2` 0x2B | `flags &= ~mask` |

The wait opcodes do not touch the condition. `WaitWhileUnitFlags 0x4008` (135 uses) waits while **either** 8 or
0x4000 is set. `TestUnitFlags2 0x1800` and `TestUnitFlags2 9` are likewise true if either bit is set. 0x27/0x28 are
not used by any shipped script.

| Before | Instruction | After |
|---|---|---|
| unit_flags 0x0008 | `WaitWhileUnitFlags 0x4008` | stays at the same pc, tick ends |
| unit_flags 0x0000 | `WaitWhileUnitFlags 0x4008` | pc + 2, continue |
| unit_flags2 0x0001 | `TestUnitFlags2 9` | condition true |
| unit_flags2 0x0002 | `TestUnitFlags2 9` | condition false |
