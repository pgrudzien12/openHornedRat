# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Minimal debrief completion for the `debrief:` / `debriefwithsummary:` glue commands.

There is no debrief screen yet (the full screen is a separate item). The completion handler of these
two commands does one thing (notes/activity_results.md section 5): it credits the final payment and
lets the script resume. This module applies what the engine can compute and reports the rest, so a
skipped effect is visible in the campaign log instead of silently vanishing.
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from . import payments
from .payments import settle

if TYPE_CHECKING:
    from .campaign_log import CampaignLogger
    from .campaign_state import CampaignState
    from .glue_runtime import StartDebrief


def complete_debrief(campaign: "CampaignState | None", effect: "StartDebrief", log: "CampaignLogger | None" = None,
                     flawless: bool = False) -> tuple[list[str], list[str]]:
    """Apply the completion of a debrief request; returns ``(applied, skipped)`` lists of short strings.

    With ``flawless`` (no-battle mode) a mission without any battle result counts as a flawless win.
    The final payment is the mission's balance sheet (whshr.payments, notes/campaign.md section 2.5) over the
    objective records of the latest battle: the initial payment was already credited at troop selection, so the
    payment credited here is the sheet's Total Final Payment. A battle that wrote no objective records (a played
    battle: the engine does not evaluate objectives yet) skips the payment instead of guessing it. When ``log`` is
    given a ``payment`` row records the amount and the line items applied and skipped. Armour rewards, doubled
    experience, promotions and army merges are not part of this handler (notes/activity_results.md section 5).
    """
    applied: list[str] = []
    skipped: list[str] = []
    if campaign is None:
        return applied, ["final payment: no campaign state"]
    terms = getattr(campaign, "mission_cash", None)
    if terms is None:
        skipped.append("final payment: the mission has no payment terms")
    elif campaign.mission_paid:
        skipped.append("final payment: already credited for this mission")
    else:
        if flawless and not campaign.objective_results and not campaign.flawless_result:
            # no-battle mode, and the mission fought no battle (a march or summary page): still a perfect win
            payments.store_flawless(campaign)
        if not campaign.objective_results and not campaign.flawless_result:
            skipped.append("final payment: no objective results from the battle")
        else:
            settlement = settle(terms, campaign.objective_results, campaign.bonus_counter)
            campaign.mission_paid = True
            campaign.add_cash(settlement.final)
            applied.append(f"final payment: {settlement.final} crowns")
            applied.extend(f"{label}: {amount}" for label, amount in settlement.lines if label != "final")
            skipped.extend(f"final payment line {text}" for text in settlement.skipped)
            if log is not None:
                _log_payment(log, "final", settlement.final, campaign, settlement.lines, settlement.skipped)
    if terms is not None and not applied and log is not None:
        _log_payment(log, "final", 0, campaign, [], skipped)
    pending = sorted(getattr(campaign, "pending_join", ()))
    if pending:
        skipped.append(f"pending-join units {pending}: merged when the after-mission caravan opens (not implemented)")
    return applied, skipped


def _log_payment(log: "CampaignLogger", kind: str, amount: int, campaign: "CampaignState",
                 lines: Sequence[Sequence[Any]], skipped: Sequence[str]) -> None:
    try:
        log.write("payment", kind=kind, amount=amount, coffers=campaign.coffers,
                  lines=[list(line) for line in lines], skipped=list(skipped))
    except Exception:
        pass
