"""Parser and flow graph builder for the campaign glue scripts in WND.DLL."""

import json
import os
from pathlib import Path
from .legacy import module
from .paths import Installation


def load_wnd_rcdata(wnd_dll_path):
    """Load all RT_RCDATA text resources from WND.DLL."""
    pe_cls = module("pe_resources").PE
    pe = pe_cls(str(wnd_dll_path))
    return {str(r.name).upper(): pe.data(r).decode("latin-1") for r in pe.resources() if r.type == 10}


def parse_glue_lines(text):
    """Yield non-comment (command, argument) pairs from a glue script."""
    for raw in text.splitlines():
        line = raw.split("//")[0].strip()
        if not line or line.startswith(";") or line[0] in "\x1a\x1b":
            continue
        if line.startswith("["):
            yield line.split("]")[0] + "]", ""
            continue
        key, _, val = line.partition(":")
        yield key.strip().lower(), val.split(";")[0].strip()


def parse_cash_field(cash_str):
    """Parse cash:type,initial,completion,per_unit,penalty,letters..."""
    if not cash_str:
        return None
    parts = [p.strip() for p in cash_str.split(",")]
    if len(parts) < 5:
        return {"raw": cash_str}
    try:
        ctype = int(parts[0])
        initial = int(parts[1])
        completion = int(parts[2])
        per_unit = int(parts[3])
        penalty = int(parts[4]) if len(parts) > 4 else 0
        letters = [p for p in parts[5:] if p]
        return {
            "type": ctype,
            "initial": initial,
            "completion": completion,
            "per_unit": per_unit,
            "penalty": penalty,
            "objective_letters": letters,
            "march_only": "M" in letters,
        }
    except ValueError:
        return {"raw": cash_str}


def parse_mission_windows(wnd, brtxt=None):
    """Parse all [MISSION] blocks grouped by mission window resource name."""
    brtxt = brtxt or {}
    windows = {}
    for name, text in sorted(wnd.items()):
        if not ("MISSION" in name and "WINDOW" in name) and not name.startswith("MISSION"):
            continue
        cur_mission = None
        missions = []
        for cmd, arg in parse_glue_lines(text):
            if cmd == "[MISSION]":
                cur_mission = {}
            elif cmd == "[END]" and cur_mission is not None:
                if cur_mission:
                    missions.append(cur_mission)
                cur_mission = None
            elif cur_mission is not None:
                if cmd == "set" and arg.startswith("res="):
                    res_id = int(arg[4:])
                    cur_mission["name_id"] = res_id
                    cur_mission["name"] = brtxt.get(res_id, f"MISSION_{res_id}")
                elif cmd == "res":
                    cur_mission["brief_script"] = arg
                elif cmd == "script":
                    cur_mission["brief_file"] = arg
                elif cmd == "setbattlescript":
                    cur_mission["battle"] = arg.upper()
                elif cmd == "setmissionscript":
                    cur_mission["mission_script"] = arg.upper()
                elif cmd == "cash":
                    cur_mission["cash_raw"] = arg
                    cur_mission["cash"] = parse_cash_field(arg)
                elif cmd == "set" and arg.startswith("depend="):
                    cur_mission["depend"] = int(arg[7:])
                elif cmd == "set" and arg.startswith("releaseflag="):
                    cur_mission["releaseflag"] = int(arg[12:])
                elif cmd == "set" and arg.startswith("inactivedepend="):
                    cur_mission["inactivedepend"] = int(arg[15:])
                elif cmd == "replacescript":
                    cur_mission["replacescript"] = arg.upper()
        if missions:
            windows[name] = missions
    return windows


def parse_window_hotspots(wnd, name, seen=()):
    """Return a window's hotspots, expanding its original ``[INCLUDE]`` blocks.

    ``set:res=<number>`` is the BRTXT hover-hint resource.  A later ``res:``
    command is an action target and deliberately does not replace that hint.
    """
    fields = ("x", "y", "vx", "vy", "res")
    return [{key: hotspot[key] for key in fields if key in hotspot}
            for hotspot in parse_window_ui(wnd, name, seen)["hotspots"]
            if {"x", "y", "vx", "vy"} <= hotspot.keys()]


def parse_window_ui(wnd, name, seen=()):
    """Parse one glue window into presentation data, expanding ``[INCLUDE]`` blocks.

    This deliberately preserves targets as glue-resource names. Mapping those
    names to engine events belongs to the view/controller, not the parser.
    """
    name = name.upper()
    if name in seen:
        raise ValueError(f"cyclic window include: {' -> '.join((*seen, name))}")
    try:
        text = wnd[name]
    except KeyError:
        raise ValueError(f"window resource not found: {name}") from None

    result = {"window": name, "position": {}, "bitmaps": [], "hotspots": [], "anims": [], "texts": []}
    section, current = None, None
    for command, argument in parse_glue_lines(text):
        if command.startswith("["):
            if command == "[POSITION]":
                section, current = command, result["position"]
            elif command == "[BITMAP]":
                section, current = command, {}
            elif command == "[HOTSPOT]":
                section, current = command, {}
            elif command == "[ANIM]":
                section, current = command, {}
            elif command == "[TEXT]":
                section, current = command, {}
            elif command == "[INCLUDE]":
                section, current = command, None
            elif command == "[END]":
                if section == "[BITMAP]" and current:
                    result["bitmaps"].append(current)
                elif section == "[HOTSPOT]" and current:
                    result["hotspots"].append(current)
                elif section == "[ANIM]" and current:
                    result["anims"].append(current)
                elif section == "[TEXT]" and current:
                    result["texts"].append(current)
                section, current = None, None
            continue
        if section == "[INCLUDE]" and command == "script":
            included = parse_window_ui(wnd, argument, (*seen, name))
            result["bitmaps"].extend(included["bitmaps"])
            result["hotspots"].extend(included["hotspots"])
            result["anims"].extend(included["anims"])
            result["texts"].extend(included["texts"])
            continue
        if current is None:
            continue
        if command == "set" and "=" in argument:
            key, value = argument.split("=", 1)
            try:
                current[key] = int(value)
            except ValueError:
                current[key] = value
        elif section == "[BITMAP]" and command in ("setbitmap", "setmask"):
            current[command.removeprefix("set")] = argument
        elif section == "[HOTSPOT]" and command in ("res", "script"):
            current["target"] = argument
            current["target_kind"] = command
        elif section == "[ANIM]" and command == "settextcolor":
            current["text_color"] = argument.lower()
        elif section == "[ANIM]" and command == "name":
            current["name"] = argument
        elif section == "[TEXT]" and command in ("font", "format", "settextcolor"):
            current["color" if command == "settextcolor" else command] = argument.lower()
    return result


def parse_window_portrait(wnd, name):
    """Parse a window's data-defined position and speaker portrait settings."""
    ui = parse_window_ui(wnd, name)
    if not ui["position"] or not ui["anims"]:
        return None
    portrait = ui["anims"][0].copy()
    if "name" in portrait:
        portrait["speaker"] = portrait.pop("name")
    return {"window": ui["window"], "position": ui["position"], **portrait}


def parse_mission_script(text, bktxt=None):
    """Analyze actions inside a mission runner script (e.g. BPMISSION1)."""
    bktxt = bktxt or {}
    actions = []
    summary = {
        "battles": [],
        "movies": [],
        "reinforcements": [],
        "unit_joins": [],
        "unit_leaves": [],
        "book_entries": [],
        "debriefs": [],
        "subscripts": [],
        "objectives_tested": [],
        "caravan_entries": [],
        "ends_game": False,
    }
    for cmd, arg in parse_glue_lines(text):
        if cmd in ("playgame", "playgamewithdebrief", "encounterplaygame", "encounterplaygamewithdebrief", "setbattlescript"):
            parts = [p.strip() for p in arg.split(",") if p.strip()]
            battle_name = parts[0].upper() if parts else ""
            debrief_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
            summary["battles"].append({"cmd": cmd, "battle": battle_name, "debrief": debrief_id})
            actions.append({"action": "battle", "cmd": cmd, "battle": battle_name, "debrief": debrief_id})
        elif cmd in ("playmovie", "iftrueplaymovie", "iffalseplaymovie"):
            summary["movies"].append({"cmd": cmd, "movie": arg})
            actions.append({"action": "movie", "cmd": cmd, "movie": arg})
        elif cmd == "addtroop":
            # format: reg_idx=count
            if "=" in arg:
                reg_idx_s, cnt_s = arg.split("=", 1)
                try:
                    reg_idx, cnt = int(reg_idx_s), int(cnt_s)
                    reg_name = bktxt.get(300 + reg_idx, f"Regiment {reg_idx}")
                    summary["reinforcements"].append({"regiment_id": reg_idx, "regiment": reg_name, "count": cnt})
                    actions.append({"action": "addtroop", "regiment_id": reg_idx, "regiment": reg_name, "count": cnt})
                except ValueError:
                    pass
        elif cmd == "unitjoinmission":
            try:
                reg_idx = int(arg.rstrip(":"))
                reg_name = bktxt.get(300 + reg_idx, f"Regiment {reg_idx}")
                summary["unit_joins"].append({"regiment_id": reg_idx, "regiment": reg_name})
                actions.append({"action": "unit_join", "regiment_id": reg_idx, "regiment": reg_name})
            except ValueError:
                pass
        elif cmd == "unitleavemission":
            try:
                reg_idx = int(arg.rstrip(":"))
                reg_name = bktxt.get(300 + reg_idx, f"Regiment {reg_idx}")
                summary["unit_leaves"].append({"regiment_id": reg_idx, "regiment": reg_name})
                actions.append({"action": "unit_leave", "regiment_id": reg_idx, "regiment": reg_name})
            except ValueError:
                pass
        elif cmd == "enablebook":
            summary["book_entries"].append(arg)
            actions.append({"action": "enablebook", "entry": arg})
        elif cmd in ("setdebrief", "debrief", "debriefwithsummary"):
            summary["debriefs"].append({"cmd": cmd, "arg": arg})
            actions.append({"action": "debrief", "cmd": cmd, "arg": arg})
        elif cmd in ("gosub", "iftruegosub", "iffalsegosub", "goto"):
            summary["subscripts"].append({"cmd": cmd, "target": arg.upper()})
            actions.append({"action": "branch", "cmd": cmd, "target": arg.upper()})
        elif cmd == "testobjective":
            summary["objectives_tested"].append(arg.upper())
            actions.append({"action": "testobjective", "letter": arg.upper()})
        elif cmd in ("gocaravan", "iftruegocaravan", "iffalsegocaravan"):
            entry = {"mode": arg.lower()}
            if cmd != "gocaravan":
                entry["condition"] = "true" if cmd == "iftruegocaravan" else "false"
            summary["caravan_entries"].append(entry)
            actions.append({"action": "caravan", **entry})
        elif cmd == "endgame":
            summary["ends_game"] = True
            actions.append({"action": "endgame"})
    return {"actions": actions, "summary": summary}


def build_campaign_graph(installation_path):
    """Build the complete campaign transition graph from WND.DLL and associated string tables."""
    game = Installation(installation_path)
    wnd_dll = game.file_dir("DLL", "WND.DLL")
    brtxt_dll = game.file_dir("DLL", "BRTXT.DLL")
    bktxt_dll = game.file_dir("DLL", "BKTXT.DLL")
    gmtxt_dll = game.file_dir("DLL", "GMTXT.DLL")

    pe_missions = module("pe_missions")
    wnd = load_wnd_rcdata(wnd_dll)
    brtxt = pe_missions.load_strings(str(brtxt_dll))
    bktxt = pe_missions.load_strings(str(bktxt_dll))
    gmtxt = pe_missions.load_strings(str(gmtxt_dll))

    windows = parse_mission_windows(wnd, brtxt)
    # Battle script names are not unique: placeholder BF003 alone occurs in
    # many mission records. Preserve the record identity used by UI assets
    # and briefing lookup instead of treating ``battle`` as a key.
    for window_name, missions in windows.items():
        for index, mission in enumerate(missions):
            mission["briefing_key"] = f"{window_name.casefold()}.{index}"
    portrait_windows = {name: result for name in wnd if (result := parse_window_portrait(wnd, name)) is not None}

    # Parse flow scripts
    flow_scripts = {}
    for name, text in sorted(wnd.items()):
        if not name.startswith("FLOWSCRIPT"):
            continue
        steps = []
        for cmd, arg in parse_glue_lines(text):
            if cmd == "addobject" and "res=" in arg.lower():
                obj_res = arg.split("=", 1)[1].strip().upper()
                steps.append({"action": "add_window", "window": obj_res})
            elif cmd == "opensubwindow" and "res=" in arg.lower():
                steps.append({"action": "open_subwindow", "window": arg.split("=", 1)[1].strip().upper()})
            elif cmd == "set" and arg.startswith("tentpos="):
                steps.append({"action": "set_tentpos", "pos": int(arg[8:])})
            elif cmd == "waitforrelease":
                steps.append({"action": "wait_player_choice"})
            elif cmd in ("gosub", "goto"):
                steps.append({"action": "jump", "target": arg.upper()})
        flow_scripts[name] = steps

    # Parse all execution mission scripts
    mission_scripts = {}
    for name, text in sorted(wnd.items()):
        if "MISSION" in name and not ("WINDOW" in name) and not name.startswith("FLOW"):
            mission_scripts[name] = parse_mission_script(text, bktxt)

    # Resolve links and branches
    nodes = {}
    edges = []

    # Each mission window is a state node offering choices
    for wname, mlist in windows.items():
        nodes[wname] = {
            "type": "mission_window",
            "id": wname,
            "missions": mlist,
        }

    for fname, steps in flow_scripts.items():
        nodes[fname] = {
            "type": "flow_script",
            "id": fname,
            "steps": steps,
        }
        # Chain flow steps
        prev_w = None
        for s in steps:
            if s["action"] == "add_window":
                w = s["window"]
                edges.append({
                    "from": fname,
                    "to": w,
                    "type": "flow_presents_window",
                })
                if prev_w:
                    edges.append({
                        "from": prev_w,
                        "to": w,
                        "type": "sequential_window_in_flow",
                        "flow": fname,
                    })
                prev_w = w

    # Window -> Mission choices -> next flow / replace script
    for wname, mlist in windows.items():
        for m in mlist:
            target_flow = m.get("replacescript")
            mscript_name = m.get("mission_script")
            m_id = m.get("name_id")
            m_name = m.get("name")
            battle = m.get("battle")
            edge = {
                "from": wname,
                "to": target_flow or "NEXT_FLOW_STEP",
                "type": "mission_choice",
                "mission_id": m_id,
                "mission_name": m_name,
                "mission_script": mscript_name,
                "battle": battle,
                "cash": m.get("cash"),
                "replacescript": target_flow,
            }
            edges.append(edge)

    return {
        "flow_scripts": flow_scripts,
        "mission_windows": windows,
        "mission_scripts": mission_scripts,
        "portrait_windows": portrait_windows,
        "graph": {
            "nodes": nodes,
            "edges": edges,
        },
    }


def export_graph_dot(campaign_data):
    """Generate Graphviz DOT representation of the campaign flow."""
    lines = [
        "digraph CampaignFlow {",
        '    rankdir=LR;',
        '    node [fontname="Helvetica", fontsize=10, shape=box, style=filled];',
        '    edge [fontname="Helvetica", fontsize=9];',
        "",
    ]

    windows = campaign_data.get("mission_windows", {})
    for wname, mlist in sorted(windows.items()):
        lbl_parts = [f"<b>{wname}</b>", "---"]
        for m in mlist:
            b_info = f" ({m.get('battle')})" if m.get("battle") else ""
            lbl_parts.append(f"[{m.get('name_id')}] {m.get('name')}{b_info}")
        label = "<" + "<br/>".join(lbl_parts) + ">"
        lines.append(f'    "{wname}" [label={label}, fillcolor="#e1f5fe", color="#0288d1"];')

    flows = campaign_data.get("flow_scripts", {})
    for fname in sorted(flows):
        lines.append(f'    "{fname}" [label="{fname}", fillcolor="#fff3e0", color="#f57c00", shape=ellipse];')

    lines.append("")
    for edge in campaign_data.get("graph", {}).get("edges", []):
        src = edge["from"]
        dst = edge["to"]
        etype = edge.get("type")
        if etype == "mission_choice":
            m_name = edge.get("mission_name", "")
            b = edge.get("battle", "")
            lbl = f"{m_name} ({b})" if b else m_name
            color = "#2e7d32"
            if dst != "NEXT_FLOW_STEP":
                lines.append(f'    "{src}" -> "{dst}" [label="{lbl}", color="{color}", fontcolor="{color}"];')
        elif etype == "flow_presents_window":
            lines.append(f'    "{src}" -> "{dst}" [style=dashed, color="#f57c00"];')

    lines.append("}")
    return "\n".join(lines)


def export_campaign_markdown(campaign_data):
    """Generate a readable Markdown summary of the campaign missions and branches."""
    lines = [
        "# Campaign Flow and Mission Branching Graph",
        "",
        "Extracted from `WND.DLL` glue scripts, `BRTXT.DLL` strings, and `BKTXT.DLL` roster names.",
        "",
        "## Main Campaign Flow Paths",
        "",
        "1. **Border Princes (Chapter 1)**: `FLOWSCRIPTBP01`",
        "   - `MISSIONBP01WINDOW`: Protect Schnappleburg (`BF003`, A2) -> `MISSIONBP23WINDOW`",
        "   - Choice: Escort to Holst (`BF005/BF006`) vs Sven Carlsson (`BF001`, A3)",
        "   - Branching into Patrol (`BF007/BF008`), Rescue Ilmarin (`BF010`, A6), Orc Pursuit (`BF011`)",
        "   - Mission Choice Window `MISSIONBP131415WINDOW`: Revenge (`FLOWSCRIPTRE`), Escort to Loren (`FLOWSCRIPTBPBM`), March to Zhufbar (`FLOWSCRIPTGF`)",
        "",
        "2. **Revenge (Chapter 2)**: `FLOWSCRIPTRE`",
        "   - Vanberg (`BF004_1`) -> Against the Grain (`BF004_2`) -> Bridge over River Weiss (`BF004_3`)",
        "   - Choice Window `MISSIONRE4568WINDOW`: Slave Train (`BF004_4`), Shattered Pass (`BF004_5`), March to Zhufbar, To Loren",
        "",
        "3. **Black Mountains (Chapter 3)**: `FLOWSCRIPTBPBM` / `FLOWSCRIPTREBM`",
        "   - Surprise Attack (`BF012`), Valley of the Trolls (`BF018`), Vermin Burrows (`BF019`), March to Zhufbar",
        "",
        "4. **Worlds Edge Mountains (Chapter 4)**: `FLOWSCRIPTWE`",
        "   - Counter Attack (`BF027`), Squatter's Rights (`BF028`), Grumm's Gate (`BF015`), The Listening Gate (`BF017`)",
        "",
        "5. **Siege of Zhufbar -> Nuln -> Grey Mountains -> Loren -> Finale**: `FLOWSCRIPTSZENGML`",
        "   - **Siege of Zhufbar**: Rat Trap (`BF041`), Slave Assault (`BF037`), Iron Fort (`BF036`), Escort Engrol (`BF014/BF029`)",
        "   - **Envoy to Nuln**: Decoy (`BF020`), Bandit's Hideout (`BF025`), Capture Guy Gourard (`BF009`), To Loren (`BF042`)",
        "   - **Grey Mountains**: Extermination (`BF033`), Bugman's Brewery (`BF021`), To Loren (`BF030/BF031`)",
        "   - **Loren Forest**: Patrol Loren (`BF022/BF023`), Poisoned Wind (`BF024`), Rescue (`BF032`)",
        "   - **Finale**: The Final Battle (`BF034`, `BF035`, A22..A27)",
        "",
        "## Mission Details Table",
        "",
        "| ID | Window | Mission Name | Battle | Script | Replaces / Leads To | Cash (Initial / Complete / Per-Head) |",
        "|---|---|---|---|---|---|---|",
    ]

    windows = campaign_data.get("mission_windows", {})
    for wname, mlist in sorted(windows.items()):
        for m in mlist:
            cid = m.get("name_id", "")
            cname = m.get("name", "")
            battle = m.get("battle", "-")
            mscript = m.get("mission_script", "-")
            rep = m.get("replacescript") or "-"
            cash = m.get("cash") or {}
            if cash.get("march_only"):
                cash_str = "March only"
            elif cash.get("initial") is not None:
                cash_str = f"{cash.get('initial')} / {cash.get('completion')} / {cash.get('per_unit')}"
            else:
                cash_str = m.get("cash_raw") or "-"
            lines.append(f"| {cid} | `{wname}` | {cname} | `{battle}` | `{mscript}` | `{rep}` | {cash_str} |")

    return "\n".join(lines)


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Extract and parse campaign flow scripts and mission graphs.")
    parser.add_argument("installation", type=Path, help="WARFB installation directory")
    parser.add_argument("--json", type=Path, help="export full campaign graph as JSON")
    parser.add_argument("--dot", type=Path, help="export campaign graph as Graphviz DOT")
    parser.add_argument("--markdown", type=Path, help="export campaign summary as Markdown")
    args = parser.parse_args(argv)

    data = build_campaign_graph(args.installation)
    windows = data.get("mission_windows", {})
    flows = data.get("flow_scripts", {})
    print(f"Parsed {len(flows)} flow scripts and {len(windows)} mission windows.")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"Wrote JSON to {args.json}")

    if args.dot:
        args.dot.parent.mkdir(parents=True, exist_ok=True)
        with open(args.dot, "w", encoding="utf-8") as f:
            f.write(export_graph_dot(data))
        print(f"Wrote DOT to {args.dot}")

    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        with open(args.markdown, "w", encoding="utf-8") as f:
            f.write(export_campaign_markdown(data))
        print(f"Wrote Markdown to {args.markdown}")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
