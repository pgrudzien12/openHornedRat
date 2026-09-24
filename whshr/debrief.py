"""Minimal debrief completion for the `debrief:` / `debriefwithsummary:` glue commands.

There is no debrief screen yet (the full screen is a separate item). The completion handler of these
two commands does one thing (notes/activity_results.md section 5): it credits the final payment and
lets the script resume. This module applies what the engine can compute and reports the rest, so a
skipped effect is visible in the campaign log instead of silently vanishing.
"""


def complete_debrief(campaign, effect):
    """Apply the completion of a debrief request; returns ``(applied, skipped)`` lists of short strings.

    The final payment is a function of the mission's payment program and of the objective records the
    battle writes (notes/debrief_evaluation.md section 6); the engine's battles do not write objective
    records yet, so the payment is skipped rather than guessed. Armour rewards, doubled experience,
    promotions and army merges are not part of this handler at all (notes/activity_results.md section 5).
    """
    applied, skipped = [], []
    if campaign is None:
        return applied, ["final payment: no campaign state"]
    if getattr(campaign, "objective_results", None):
        skipped.append("final payment: the payment programs are not implemented")
    else:
        skipped.append("final payment: no objective results from the battle")
    pending = sorted(getattr(campaign, "pending_join", ()))
    if pending:
        skipped.append(f"pending-join units {pending}: merged when the after-mission caravan opens (not implemented)")
    return applied, skipped
