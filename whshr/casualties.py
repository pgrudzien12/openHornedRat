"""Post-battle casualty bookkeeping: wounded men, healing and disbanding between a battle and the next mission
(notes/casualty_bookkeeping.md section 3).

The engine keeps its own representation (CLAUDE.md, "saves are the engine's own"): the company is the army and the
marching regiments are its members, the master roster is the campaign's every-regiment record, and each regiment
counts its *present* models (``s_size + s_routed``), so routed models are back in the ranks once Done has run.
Two per-regiment roster counters carry the wounded: ``wounded_last`` (wounded of the latest battle the regiment
fought) and ``returning`` (wounded that rejoin at the current debrief's Done).

Deviations, all invisible in prices, "destroyed" and the disband test because those read the present count:
- the original returns routed models to a mode-2 army only when the next troop selection is confirmed; here they
  rejoin at Done, so between Done and troop selection the reinforcement window does not reserve room for them;
- allied story regiments fighting as NPCs are not written into the battle outcome, so their wounded and
  experience are not merged back (report 2.5, 3.8 B5).
"""

from dataclasses import replace
from typing import TYPE_CHECKING

from . import roster
from .debrief_screen import DEFAULT_DEAD_PERCENT, UnitOutcome

if TYPE_CHECKING:
    from .campaign_state import CampaignState

COMMANDER = 2  # whoami of the commander's regiment, which is never disbanded (notes/casualty_bookkeeping.md 3.5)
DISBAND_PERCENT = 20  # a regiment below this share of its original size is disbanded (3.5 D5)


def wounded_of(outcome: UnitOutcome, wounded_percent: int = DEFAULT_DEAD_PERCENT) -> int:
    """Lost models (killed, not routed) times the wounded share, truncated (report 3.1)."""
    return max(0, outcome.casualties - outcome.routed) * wounded_percent // 100


def campaign_over_movie(campaign: "CampaignState") -> str | None:
    """The campaign-over test that precedes everything after a played battle (notes/debrief_evaluation.md 3.1): the
    name of the death movie when the campaign ends, else ``None``. A commander regiment with nobody left (models,
    routed and this battle's wounded all zero) ends the campaign only when objective ``Z`` was met (``death01``);
    otherwise objective ``G`` or ``Y`` met ends it (``death02``)."""
    outcome = campaign.battle_outcome.get(COMMANDER)
    if outcome is None:
        return None

    def met(letter: str) -> bool:
        record = campaign.objective_results.get(letter)
        return record is not None and bool(record[0])

    if outcome.models + outcome.routed + wounded_of(outcome) == 0:
        return "death01" if met("Z") else None
    return "death02" if met("G") or met("Y") else None


def _destroyed(present: int, artillery: bool) -> bool:
    return present < 2 if artillery else present <= 0


def after_battle(campaign: "CampaignState") -> None:
    """The steps that run right after a played battle, before the debrief screen (report 3.3 P2-P6).

    P2 shifts every regiment's previous wounded into ``returning``; P3 records this battle's wounded; P4 gives the
    commander's wiped-out regiment one wounded model back, and a never-disbanded (``keep``) regiment with nobody
    left one model; P5 merges the result into the master roster; P6 drops this battle's wounded when objective
    ``Z`` was met."""
    campaign.returning = {whoami: count for whoami, count in campaign.wounded_last.items() if count}
    campaign.wounded_last = {}
    company = {regiment.whoami: regiment for regiment in campaign.company}
    outcomes = dict(campaign.battle_outcome)
    for whoami, outcome in outcomes.items():
        regiment = company.get(whoami)
        wounded = wounded_of(outcome)
        campaign.wounded_last[whoami] = wounded
        present = outcome.models + outcome.routed
        artillery = regiment is not None and regiment.row.artillery
        if whoami == COMMANDER:
            if _destroyed(present, artillery) and wounded > 0:
                outcomes[whoami] = replace(outcome, routed=outcome.routed + 1)
                campaign.wounded_last[whoami] = wounded - 1
        elif regiment is not None and regiment.row.keep and present + wounded == 0:
            outcomes[whoami] = replace(outcome, routed=outcome.routed + 1)
    campaign.battle_outcome = outcomes
    _merge_into_master(campaign, outcomes)
    z = campaign.objective("Z")
    if z is not None and z[0]:
        campaign.wounded_last = {}


def _merge_into_master(campaign: "CampaignState", outcomes: dict[int, UnitOutcome]) -> None:
    """P5: the master roster takes each fought regiment as it left the battle, routed models back in the ranks and
    this battle's experience not yet doubled; a regiment that later rejoins from it comes back that way
    (report 3.9, first quirk)."""
    company = {regiment.whoami: regiment for regiment in campaign.company}
    updated: list[roster.Regiment] = []
    for record in campaign.master:
        outcome = outcomes.get(record.whoami)
        source = company.get(record.whoami)
        if outcome is not None and source is not None:
            record = roster.with_models(source, outcome.models + outcome.routed)
            record = roster.with_experience(record, source.experience + outcome.experience_gained)
        updated.append(record)
    campaign.master = tuple(updated)


def commit_wounded(campaign: "CampaignState") -> None:
    """The text-page step of one success list (report 3.4): this battle's wounded join ``returning`` at once, so
    Done heals them; a second call changes nothing."""
    for whoami, count in campaign.wounded_last.items():
        if count:
            campaign.returning[whoami] = campaign.returning.get(whoami, 0) + count
    campaign.wounded_last = {}


def heal_and_disband(campaign: "CampaignState") -> tuple[list[str], list[str]]:
    """Done's merge, heal and disband over every army regiment, marching or not (report 3.5 D4-D7); returns what
    happened as ``(healed, disbanded)`` notes.

    A regiment that fought takes its battle result (models on the field plus routed ones); the returning wounded
    are added, but past the original size the regiment is set to full strength and the excess, routed models
    included, is lost.  A regiment then below ``max(1, 20 % of its original size)`` is disbanded unless it is the
    commander's or a ``keep`` regiment.  ``returning`` is cleared for everyone at the end."""
    healed: list[str] = []
    disbanded: list[str] = []
    updated: list[roster.Regiment] = []
    for regiment in campaign.company:
        if not regiment.hired:
            updated.append(regiment)  # in the recruit book, not the army
            continue
        outcome = campaign.battle_outcome.get(regiment.whoami)
        size, routed = (outcome.models, outcome.routed) if outcome is not None else (regiment.models, 0)
        returning = campaign.returning.get(regiment.whoami, 0)
        if size + returning > regiment.orgsize:
            size, routed = regiment.orgsize, 0
        else:
            size += returning
        if returning:
            healed.append(f"{regiment.name}: {returning} wounded return")
        present = size + routed
        if (present < max(1, regiment.orgsize * DISBAND_PERCENT // 100) and regiment.whoami != COMMANDER
                and not regiment.row.keep):
            disbanded.append(regiment.name)
            campaign.march_units.discard(regiment.whoami)
            continue
        updated.append(roster.with_models(regiment, present) if present != regiment.models else regiment)
    campaign.company = tuple(updated)
    campaign.army_units = {regiment.whoami for regiment in campaign.company if regiment.hired}
    campaign.returning = {}
    return healed, disbanded
