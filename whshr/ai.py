"""Simple, deterministic, rule-based enemy AI, stdlib-only (no frontend import).

Called once per tick from `whshr.engine.Battle.tick`, before movement. Every enemy (non-player)
regiment holds its deployment position until a player regiment comes within `ENGAGE_DISTANCE`
(a documented placeholder: no such trigger distance is described in notes/game_rules.md, which
covers the original's scripted mission bytecode instead of a from-scratch AI); then it either
shoots, if it carries a missile weapon and a target is in range, or charges the nearest player
regiment. A regiment already routing or in melee is left alone (`whshr.combat` and
`whshr.engine.Battle` drive those states instead). This does not implement the original's
behaviour bytecode interpreter (`whshr.behaviour`) or mission scripts, as the task calls for.
"""
import math

ENGAGE_DISTANCE = 400.0  # world units (~16.7"): documented placeholder trigger distance


def _alive_player_regiments(battle):
    return [regiment for regiment in battle.regiments.values() if regiment.player and regiment.active]


def decide_orders(battle):
    """Give each idle enemy regiment an order for this tick: hold, shoot, or charge."""
    targets = _alive_player_regiments(battle)
    if not targets:
        return
    for regiment in battle.regiments.values():
        if regiment.player or not regiment.active or regiment.routing or regiment.in_melee:
            continue
        nearest = min(targets, key=lambda t: math.hypot(t.x - regiment.x, t.y - regiment.y))
        distance = math.hypot(nearest.x - regiment.x, nearest.y - regiment.y)
        if regiment.missile_range and distance <= regiment.missile_range:
            # In range: hold and let whshr.combat.resolve_shooting fire, instead of charging.
            regiment.attack_target = None
            continue
        if distance <= ENGAGE_DISTANCE:
            regiment.attack_target = nearest.identifier
