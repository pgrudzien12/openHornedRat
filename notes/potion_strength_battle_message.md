# Potion of Strength and the original battle message window

## Finding

Drinking a Potion of Strength does **not** add a potion-specific line to the original
game's on-screen battle message window. The item name remains visible in the Items list
while that list is open, but that label is not a new battle message. Existing or
unrelated messages may remain visible in the message window.

The click immediately spends the potion and refreshes its item row. For a bearer that
is not held, it also activates the +3 Strength bonus for the regiment's leader figure
for the rest of the battle, as documented in
[battlefield_items.md](battlefield_items.md#potion-of-strength-and-grudgebringer-in-melee).
The current engine also spends a held bearer's potion but does not grant the bonus;
this message-window finding does not establish the original game's held-bearer effect.
The item use has no target-selection step and does not request a battle message,
reaction, portrait pop-up, or scripted item event. The message-window route is used
by other battle events; the potion activation does not take that route.

This is a static behavioural finding. 🟡 A direct screen observation of the original
game at the moment of drinking is still outstanding.

## Before / action / after examples

| Before | Action | After |
|---|---|---|
| A selected, unheld regiment has a living leader and an unused Potion of Strength; the battle message window is empty. | Open Items and click the Potion row. | The Potion row becomes spent and active, the leader gains +3 Strength, and the battle message window stays empty. |
| A prior, unrelated message is visible; an unheld bearer's Potion is unused. | Click the Potion row. | The Potion activates; the prior message is not replaced by potion text. Its normal lifetime or later unrelated messages can still change the window. |
| The bearer is held and the Potion is unused. | Click the Potion row. | In the current engine, the row becomes spent without granting Strength; no potion message is added. The original game's held-bearer effect remains unconfirmed. |
| The Potion has already been used. | Try to click its disabled row. | No second activation or potion message occurs. |

This finding adds the message-window outcome to the existing item report; it does not
change the previously documented Strength or single-use rules.
