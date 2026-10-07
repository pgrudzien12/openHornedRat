# Leader Ballistic Skill and shooting

The original game's ordinary bow, crossbow and artillery projectiles use the **regiment's Ballistic Skill (BS)** to scatter their destination. Selecting a particular firing figure supplies the projectile's starting position, but does not substitute that figure's BS. The leader's separate BS does not add a second accuracy bonus, even when the leader or war machine is the firing figure.

For each horizontal axis, the scatter multiplier is a random integer from `0` through `10 - min(regiment BS, 10)`, with an independently chosen sign. The result is also scaled by the weapon's spread and the distance to the intended point. Higher regiment BS narrows the possible miss; BS 10 eliminates this scatter. A projectile can still hit an intervening object or miss a moving target after launch.

| Before | Action | After |
|---|---|---|
| Archer regiment BS 3; leader BS 7; leader alive | Ordinary volley, with one launch posted by the leader | The shot starts at the leader's position. Its per-axis scatter multiplier is `0..7`, as for regiment BS 3; leader BS 7 would have yielded `0..3` but is not used. |
| Same regiment; another archer posts the launch | Ordinary volley | The shot starts at that archer's position and also uses regiment BS 3 (`0..7`). |
| Archer regiment BS promoted from 3 to 4; leader remains BS 7 | Next ordinary volley | Every launch uses the improved regiment BS 4 (`0..6`), regardless of which figure posts it. |
| Artillery crew/regiment BS 3; machine/leader BS 7 | Fire the war machine | The shot starts at the machine/leader, uses its missile weapon, and scatters using crew/regiment BS 3 (`0..7`). |

These examples isolate the BS choice; actual displacement also depends on range, weapon spread, obstruction and random signs. The original campaign promotions do not raise BS, so a regiment/leader mismatch in the table is a useful hypothetical or mod-rule case, not an ordinary promotion outcome. See [campaign promotions](campaign.md) and [ranged combat](ranged_combat_handoff.md).

This conclusion concerns projectile accuracy. The leader can affect shooting in other ways: the machine/leader supplies an artillery weapon and launch position. Effective Leadership is a separate rule described in [game rules](game_rules.md).
