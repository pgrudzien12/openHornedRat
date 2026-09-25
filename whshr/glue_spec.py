# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Specification status of every glue script command, and a usage report over the shipped scripts.

The registry is the machine-readable index of ``notes/glue_interpreter.md``: each executable command names the section that
specifies it, whether the effect is fully specified there ("specified") or delegated to another note for the subsystem it drives
("delegated"), and any residual open question.  The report joins the registry with the commands actually used by the scripts, so
an engine (or a reviewer) sees at a glance which reachable commands are still insufficiently specified.
"""

from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from os import PathLike
from typing import Any

from .glue import GlueInstruction, GlueProgram, GlueResource

SPECIFIED = "specified"
DELEGATED = "delegated"


@dataclass(frozen=True)
class CommandSpec:
    level: str
    section: str
    summary: str
    open_question: str = ""


def _spec(level: str, section: str, summary: str, open_question: str = "") -> CommandSpec:
    return CommandSpec(level, section, summary, open_question)


_ACTIVITY_DEBRIEF = "result and completion contract: notes/activity_results.md §5; evaluator/payment rules: notes/debrief_evaluation.md §6"

COMMAND_SPEC: dict[str, CommandSpec] = {
    # control flow
    "gosub": _spec(SPECIFIED, "§4.1", "request: push current frame, run target"),
    "iftruegosub": _spec(SPECIFIED, "§4.1", "gosub when the condition holds"),
    "iffalsegosub": _spec(SPECIFIED, "§4.1", "gosub when the condition does not hold"),
    "goto": _spec(SPECIFIED, "§4.2", "request: run target after this script ends; does not stop the run"),
    "iftruegoto": _spec(SPECIFIED, "§4.2", "stops the run; the jump only happens if the script is later resumed and ends (unused)"),
    "iffalsegoto": _spec(SPECIFIED, "§4.2", "stops the run; the jump only happens if the script is later resumed and ends (unused)"),
    "return": _spec(SPECIFIED, "§4.3", "close this script, pop the script-frame stack, keep running the caller"),
    # waiting
    "waitforrelease": _spec(SPECIFIED, "§5", "park; resumed by mission release"),
    "waitforresume": _spec(SPECIFIED, "§5", "park; resumed by a control-panel button or battle completion"),
    "pause": _spec(SPECIFIED, "§5", "no effect"),
    # glue status
    "setgluestatus": _spec(SPECIFIED, "§3", "bits |= mask"),
    "clrgluestatus": _spec(SPECIFIED, "§3", "bits &= ~mask"),
    "setgluestatusmask": _spec(SPECIFIED, "§3", "mask = hexadecimal argument"),
    "setgluestatusmode": _spec(SPECIFIED, "§3", "mode = argument (unused)"),
    "testmission": _spec(DELEGATED, "§3", "status test on the debrief evaluator; also autosaves",
                         "notes/debrief_evaluation.md §5"),
    "testobjective": _spec(DELEGATED, "§3, §9", "status test on an objective letter of debrief.dbf",
                                "notes/debrief_evaluation.md §5"),
    "testforunitinarmy": _spec(DELEGATED, "§3, §9", "status test on the roster in-army flag", "notes/campaign.md §3.2"),
    "testforunitinmarch": _spec(DELEGATED, "§3, §9", "status test on the roster in-march flag", "notes/campaign.md §3.2"),
    # windows and objects
    "openwindow": _spec(SPECIFIED, "§6", "load a window resource into the next slot; never suspends"),
    "opensubwindow": _spec(SPECIFIED, "§6", "as openwindow, child of the current slot"),
    "closewindow": _spec(SPECIFIED, "§6", "close every slot with that name; shrink the count only for the last slot"),
    "setcurwindow": _spec(SPECIFIED, "§6", "set the current window name used by object commands"),
    "updatewindow": _spec(SPECIFIED, "§6", "repaint the current window slot"),
    "applyseq": _spec(SPECIFIED, "§6", "start the portrait sequence given by set:animseq"),
    "addobject": _spec(SPECIFIED, "§6", "load an object resource into the current-name window"),
    "addanimobject": _spec(SPECIFIED, "§6, §6.4", "addobject; suspends until a finite animation reaches its stop frame"),
    "removeobject": _spec(SPECIFIED, "§6", "bitmap: pop last; mission: clear the list; midi: stop and clear"),
    "addmidiobject": _spec(SPECIFIED, "§6", "start a tune bound to the current window (unused)"),
    # contexts
    "gocaravan": _spec(SPECIFIED, "§7.3", "request: push context, clean up, open the named caravan"),
    "iftruegocaravan": _spec(SPECIFIED, "§7.3", "gocaravan when the condition holds, else continue"),
    "iffalsegocaravan": _spec(SPECIFIED, "§7.3", "gocaravan when the condition does not hold, else continue"),
    "tagasmission": _spec(SPECIFIED, "§9", "no effect in the retail build"),
    "gomissionselect": _spec(DELEGATED, "§9.3", "raise a flag; the mission release step runs when the script ends",
                             "release step: notes/mission_selection.md §8.1"),
    "autosave": _spec(SPECIFIED, "§9.1", "write the working files and slot 5 with a pushed context, then drop it"),
    "endgame": _spec(SPECIFIED, "§8.5", "clean up, clear all stacks, stop music, return to the title menu"),
    # activities
    "playgame": _spec(SPECIFIED, "§8.1", "start the battle; debrief screen (mode 6) then resume", _ACTIVITY_DEBRIEF),
    "playgamewithdebrief": _spec(SPECIFIED, "§8.1", "start the battle; debrief screen (mode 2) then resume", _ACTIVITY_DEBRIEF),
    "encounterplaygame": _spec(SPECIFIED, "§8.1", "request: push context, battle, debrief screen (mode 6), pop, resume", _ACTIVITY_DEBRIEF),
    "encounterplaygamewithdebrief": _spec(SPECIFIED, "§8.1", "request: push context, battle, debrief screen (mode 2), pop, resume",
                                          _ACTIVITY_DEBRIEF),
    "playmovie": _spec(SPECIFIED, "§8.3", "save frame and windows, play the cutscene, restore, resume"),
    "playmoviewithfade": _spec(SPECIFIED, "§8.3", "playmovie with a fade-out first (unused)"),
    "iftrueplaymovie": _spec(SPECIFIED, "§8.3", "playmovie when the condition holds, else continue"),
    "iffalseplaymovie": _spec(SPECIFIED, "§8.3", "playmovie when the condition does not hold, else continue"),
    "iftrueplaymoviewithfade": _spec(SPECIFIED, "§8.3", "unused"),
    "iffalseplaymoviewithfade": _spec(SPECIFIED, "§8.3", "unused"),
    "debrief": _spec(SPECIFIED, "§8.2", "set evaluator, push context, debrief screen (mode 4), pop, resume", _ACTIVITY_DEBRIEF),
    "debriefwithsummary": _spec(SPECIFIED, "§8.2", "as debrief, mode 7", _ACTIVITY_DEBRIEF),
    "iftruedebrief": _spec(SPECIFIED, "§8.2", "unused"),
    "iffalsedebrief": _spec(SPECIFIED, "§8.2", "unused"),
    "iftruedebriefwithsummary": _spec(SPECIFIED, "§8.2", "unused"),
    "iffalsedebriefwithsummary": _spec(SPECIFIED, "§8.2", "unused"),
    "setdebrief": _spec(SPECIFIED, "§8.2", "debrief evaluator index = argument - 1"),
    "playtext": _spec(SPECIFIED, "§8.4", "load speech, append text, start dialogue, suspend"),
    "queuetoplaytext": _spec(SPECIFIED, "§8.4", "playtext; a silent append without waiting when speech is disabled"),
    "queuetext": _spec(SPECIFIED, "§8.4", "append text, no start, no wait (unused)"),
    "loadanimstringintocache": _spec(SPECIFIED, "§8.4", "string-cache warm-up; no observable effect"),
    "replacescript": _spec(SPECIFIED, "§9", "clean up windows, run the named flow script as the current script"),
    # campaign state and audio/ui (interpreter side)
    "addtroop": _spec(DELEGATED, "§9", "reinforcements[who] += n", "notes/campaign.md §2.4"),
    "addunit": _spec(DELEGATED, "§9", "roster flag pending join", "notes/campaign.md §3.2"),
    "unitjoinmission": _spec(DELEGATED, "§9", "regiment joins the mission force", "notes/campaign.md §3.2"),
    "unitleavemission": _spec(DELEGATED, "§9", "regiment leaves the mission force", "notes/campaign.md §3.2"),
    "cash": _spec(DELEGATED, "§9", "store the payment program on the current mission", "notes/campaign.md §2.5"),
    "setbattlescript": _spec(SPECIFIED, "§5, §9", "current battle file name used by panel buttons and troop selection"),
    "bonusinit": _spec(DELEGATED, "§9", "campaign bonus counters", "notes/campaign.md §2.5"),
    "bonusadd": _spec(DELEGATED, "§9", "campaign bonus counters", "notes/campaign.md §2.5"),
    "bonussubtract": _spec(DELEGATED, "§9", "campaign bonus counters", "notes/campaign.md §2.5"),
    "iftruebonusadd": _spec(DELEGATED, "§9", "campaign bonus counters", "notes/campaign.md §2.5"),
    "iffalsebonusadd": _spec(DELEGATED, "§9", "campaign bonus counters", "notes/campaign.md §2.5"),
    "addcash": _spec(DELEGATED, "§9", "coffers += n", "notes/campaign.md §2.5"),
    "iftrueaddcash": _spec(DELEGATED, "§9", "coffers += n when the condition holds", "notes/campaign.md §2.5"),
    "enablebook": _spec(DELEGATED, "§9", "set a book/encyclopedia flag", "notes/campaign.md §4.4"),
    "playmidi": _spec(DELEGATED, "§9", "remember and play a tune", "notes/briefing_dialogue.md §2"),
    "stopmidi": _spec(DELEGATED, "§9", "stop and forget the tune", "notes/briefing_dialogue.md §2"),
    "setmidivolume": _spec(SPECIFIED, "§9", "music volume (unused)"),
    "setwavvolume": _spec(SPECIFIED, "§9", "speech volume (unused)"),
    "settextalign": _spec(SPECIFIED, "§9", "left, center or right for later text"),
    "settextcolor": _spec(SPECIFIED, "§9", "colour name for later text"),
    "setdemodefault": _spec(SPECIFIED, "§9", "inert in this build"),
    "comment": _spec(SPECIFIED, "§9", "no effect"),
    # script variables written with ``set:<key>=<value>``
    "set:animseq": _spec(SPECIFIED, "§6, §9", "sequence number for the next applyseq"),
    "set:textlines": _spec(DELEGATED, "§8.4", "line count of the next text", "notes/briefing_dialogue.md"),
    "set:tentpos": _spec(DELEGATED, "§9", "caravan tent position variable", "notes/campaign_tent.md §2"),
}


def _command_key(instruction: GlueInstruction) -> str:
    if instruction.command == "set" and "=" in instruction.argument:
        return "set:" + instruction.argument.split("=", 1)[0].casefold()
    return instruction.command


def specification_report(resources: Mapping[str, GlueResource]) -> dict[str, Any]:
    """Return per-command usage joined with specification status for a resource inventory.

    ``resources`` is the mapping produced by ``parse_glue_resources``.  ``commands`` is ordered by use count; ``unspecified`` lists
    commands used by scripts that the registry does not know; ``unused`` lists specified commands no script uses.
    """
    statements: Counter[str] = Counter()
    scripts: defaultdict[str, set[str]] = defaultdict(set)
    for resource in resources.values():
        if not isinstance(resource, GlueProgram):
            continue
        for instruction in resource.instructions:
            key = _command_key(instruction)
            statements[key] += 1
            scripts[key].add(resource.name)
    rows: list[dict[str, Any]] = []
    for key in sorted(statements, key=lambda name: (-statements[name], name)):
        spec = COMMAND_SPEC.get(key)
        rows.append({
            "command": key,
            "statements": statements[key],
            "scripts": len(scripts[key]),
            "level": spec.level if spec else "unspecified",
            "section": spec.section if spec else "",
            "summary": spec.summary if spec else "",
            "open": spec.open_question if spec else "",
        })
    return {
        "commands": rows,
        "unspecified": [row["command"] for row in rows if row["level"] == "unspecified"],
        "unused": sorted(set(COMMAND_SPEC) - set(statements)),
    }


def format_report(report: Mapping[str, Any]) -> str:
    """Render ``specification_report`` output as a fixed-width table."""
    lines = [f"{'command':32} {'uses':>5} {'scripts':>7}  {'level':11} {'section':10} open question"]
    for row in report["commands"]:
        lines.append(f"{row['command']:32} {row['statements']:5d} {row['scripts']:7d}  {row['level']:11} "
                     f"{row['section']:10} {row['open']}")
    if report["unspecified"]:
        lines.append("UNSPECIFIED: " + ", ".join(report["unspecified"]))
    lines.append("not used by any shipped script: " + ", ".join(report["unused"]))
    return "\n".join(lines)


def main(installation: str | PathLike[str]) -> int:
    """Print the specification table for the installation's WND.DLL; non-zero exit if a used command is unspecified."""
    from .campaign import load_wnd_rcdata
    from .glue import parse_glue_resources
    from .paths import Installation

    game = Installation(installation)
    resources = parse_glue_resources(load_wnd_rcdata(game.file_dir("DLL", "WND.DLL")))
    report = specification_report(resources)
    print(format_report(report))
    return 1 if report["unspecified"] else 0
