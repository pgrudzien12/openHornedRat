# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Debrief completion: what Done applies once the debrief screen (whshr.debrief_screen) has been seen or skipped.

Modes 4 and 7 (`debrief:` / `debriefwithsummary:`) only credit the final payment (notes/activity_results.md
section 5); modes 2 and 6 (a battle with and without debrief) also apply armour rewards, experience and promotions
(notes/native-windows.md 9.9.1), and only mode 2 pays.  Whatever the engine cannot apply is reported, so a skipped
effect is visible in the campaign log instead of silently vanishing.
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from . import payments
from .debrief_rewards import apply_rewards
from .debrief_screen import DebriefReport, DebriefUnit
from .payments import settle

if TYPE_CHECKING:
    from .campaign_log import CampaignLogger
    from .campaign_state import CampaignState
    from .glue_runtime import StartDebrief


def report_for(campaign: "CampaignState") -> DebriefReport:
    """The battle result the debrief shows: the objective records and every marching regiment with its outcome
    (unharmed and gaining nothing when no battle was played)."""
    company = {regiment.whoami: regiment for regiment in campaign.company}
    units: list[DebriefUnit] = []
    for whoami in campaign.ordered_march_units:
        regiment = company.get(whoami)
        if regiment is None:
            continue
        outcome = campaign.battle_outcome.get(whoami)
        models, routed, casualties, kills, gained = ((regiment.models, 0, 0, 0, 0) if outcome is None else
                                                     (outcome.models, outcome.routed, outcome.casualties,
                                                      outcome.kills, outcome.experience_gained))
        units.append(DebriefUnit(whoami, regiment.name, models, routed, casualties, kills,
                                 regiment.experience + gained, regiment.experience, regiment.orgsize,
                                 regiment.weapon_name, regiment.armour, regiment.points, regiment.banner,
                                 regiment.hired, regiment.row.artillery))
    return DebriefReport(dict(campaign.objective_results), tuple(units))


def complete_debrief(campaign: "CampaignState | None", effect: "StartDebrief", log: "CampaignLogger | None" = None,
                     flawless: bool = False) -> tuple[list[str], list[str]]:
    """Apply the completion of a debrief request; returns ``(applied, skipped)`` lists of short strings.

    With ``flawless`` (no-battle mode) a mission without any battle result counts as a flawless win.
    The final payment is the mission's balance sheet (whshr.payments, notes/campaign.md section 2.5) over the
    objective records of the latest battle: the initial payment was already credited at troop selection, so the
    payment credited here is the sheet's Total Final Payment. A battle that wrote no objective records (a played
    battle: the engine does not evaluate objectives yet) skips the payment instead of guessing it. When ``log`` is
    given a ``payment`` row records the amount and the line items applied and skipped.  Modes 2 and 6 go on to
    apply armour rewards, experience and promotions; mode 6 (a battle without debrief) pays nothing.  Casualties
    and the army merge are not applied: the engine does not model wounded men returning (skipped, reported).
    """
    applied: list[str] = []
    skipped: list[str] = []
    if campaign is None:
        return applied, [] if effect.mode == 6 else ["final payment: no campaign state"]
    terms = getattr(campaign, "mission_cash", None)
    if effect.mode == 6:
        pass  # a battle without debrief is never paid (notes/debrief_evaluation.md 6.2)
    elif terms is None:
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
    if terms is not None and not applied and effect.mode != 6 and log is not None:
        _log_payment(log, "final", 0, campaign, [], skipped)
    if effect.mode in (2, 6):
        _apply_company_rewards(campaign, terms, applied, skipped)
    pending = sorted(getattr(campaign, "pending_join", ()))
    if pending and effect.mode != 6:
        skipped.append(f"pending-join units {pending}: merged into the company when the next caravan opens")
    return applied, skipped


def _apply_company_rewards(campaign: "CampaignState", terms: "payments.CashTerms | None", applied: list[str],
                           skipped: list[str]) -> None:
    report = report_for(campaign)
    steps = settle(terms, report.results, campaign.bonus_counter).steps if terms is not None else []
    multiplier = 2 if any(op == "experience" for op, _ in steps) else 1
    company, done, left = apply_rewards(campaign.company, report.units, multiplier,
                                        armour_rewards=any(op == "armour" for op, _ in steps))
    if done:
        campaign.company = company
    applied.extend(done)
    skipped.extend(left)
    if any(unit.casualties for unit in report.units):
        skipped.append("casualties: wounded men returning are not modelled; the company keeps its strength")


def _log_payment(log: "CampaignLogger", kind: str, amount: int, campaign: "CampaignState",
                 lines: Sequence[Sequence[Any]], skipped: Sequence[str]) -> None:
    try:
        log.write("payment", kind=kind, amount=amount, coffers=campaign.coffers,
                  lines=[list(line) for line in lines], skipped=list(skipped))
    except Exception:
        pass
