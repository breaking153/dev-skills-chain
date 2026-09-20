"""Validate prompt copies and generated examples; does not modify Espanso or prompts."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "/shuli": "knowledge/shuli.md",
    "/wanshan": "knowledge/wanshan.md",
    "/canvas": "knowledge/canvas.md",
    "/uil": "frontend/Frontend-L1-Functional.md",
    "/uim": "frontend/Frontend-L2-Product.md",
    "/uih": "frontend/Frontend-L3-Maximum.md",
    "/cdl": "Backend/Backend-L1-Functional.md",
    "/cdm": "Backend/Backend-L2-Production.md",
    "/cdh": "Backend/Backend-L3-Maximum.md",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def headings(markdown: str) -> list[tuple[int, str]]:
    """Ignore fenced code, including shell comments and embedded prompt examples."""
    result = []
    fence = None
    for line in markdown.splitlines():
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})(.*)$", line)
        if marker:
            chars, suffix = marker.groups()
            if fence is None:
                fence = chars
            elif chars[0] == fence[0] and len(chars) >= len(fence) and not suffix.strip():
                fence = None
            continue
        if fence is None:
            match = re.match(r"^(#{1,6})\s+(.+)$", line)
            if match:
                result.append((len(match[1]), match[2]))
    require(fence is None, "Unclosed code fence")
    return result


def validate_note(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    require(not text.lstrip().startswith("```"), f"Whole-note fence: {path.name}")
    outline = headings(text)
    require(outline and outline[0] == (1, "概念"), f"Wrong entry chapter: {path.name}")
    top = [title for depth, title in outline if depth == 1]
    require(len(top) >= 3, f"Flat or incomplete outline: {path.name}")
    previous = 0
    for depth, title in outline:
        require(depth <= previous + 1, f"Skipped heading level in {path.name}: {title}")
        require(not re.match(r"\d+[.、]\s*", title), f"Numbered heading: {title}")
        previous = depth
    require("**概念总结" not in text and "**Demo" not in text, "Repeated card labels")
    require(not re.search(r"(?m)^\s*(?:#{1,6}\s+)?(?:问题[一二三四五六七八九十\d]+|问\s*[:：]|答\s*[:：]|Q\d*\s*[:：]|A\d*\s*[:：])", text), "Question-and-answer packaging")
    require("TODO" not in text and "<!-- STRUCTURE_CONTRACT -->" not in text, "Unexpanded content")
    require(":chatgpt-content-reference{" not in text, f"Unresolved source placeholder: {path.name}")
    return top


def codefirst_metrics(path: Path) -> dict:
    """Describe the current trials; these counts do not prove code correctness."""
    text = path.read_text(encoding="utf-8")
    blocks = []
    prose = []
    fence = None
    language = ""
    body = []
    for line in text.splitlines():
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})(.*)$", line)
        if marker:
            chars, suffix = marker.groups()
            if fence is None:
                fence, language, body = chars, suffix.strip().lower(), []
                continue
            if chars[0] == fence[0] and len(chars) >= len(fence) and not suffix.strip():
                blocks.append((language, "\n".join(body)))
                fence = None
                continue
        (body if fence else prose).append(line)
    require(fence is None, f"Unclosed trial code: {path.name}")
    require(all(lang not in {"pseudo", "pseudocode"} for lang, _ in blocks),
            f"Pseudocode fence in current trial: {path.name}")
    implementations = [(lang, code) for lang, code in blocks if lang in {"c", "javascript", "js"}]
    require(implementations, f"Missing real implementation example: {path.name}")
    for _, code in implementations:
        require(not re.search(r"(?m)^\s*(?:\.\.\.|…|TODO)\s*;?\s*$", code),
                f"Unimplemented code placeholder: {path.name}")
    return {
        "fences": {lang: sum(other == lang for other, _ in blocks) for lang, _ in blocks},
        "implementation_lines": [len(code.splitlines()) for _, code in implementations],
        "prose_cjk": len(re.findall(r"[\u4e00-\u9fff]", "\n".join(prose))),
        "scope": "Presentation metrics and obvious-placeholder checks; not compilation or semantic proof.",
    }


def overlaps(a: dict, b: dict) -> bool:
    return (a["x"] < b["x"] + b["width"] and b["x"] < a["x"] + a["width"]
            and a["y"] < b["y"] + b["height"] and b["y"] < a["y"] + a["height"])


def validate_canvas(path: Path) -> dict:
    canvas = json.loads(path.read_text(encoding="utf-8"))
    require(set(canvas) == {"nodes", "edges"}, "Canvas top-level fields")
    require(isinstance(canvas["nodes"], list) and isinstance(canvas["edges"], list), "Canvas arrays")
    seen = set()
    nodes = canvas["nodes"]
    groups, texts = [], []
    for node in nodes:
        require(node["id"] not in seen, "Duplicate node ID")
        seen.add(node["id"])
        common = {"id", "type", "x", "y", "width", "height"}
        require(node["type"] in {"text", "group"}, "Node type")
        required = common | ({"text"} if node["type"] == "text" else {"label"})
        require(required <= set(node) <= required | {"color"}, "Node fields")
        require(all(type(node[k]) in (int, float) for k in ("x", "y", "width", "height")), "Geometry types")
        require(node["width"] > 0 and node["height"] > 0, "Nonpositive dimensions")
        require("color" not in node or node["color"] in list("123456"), "Node color")
        (texts if node["type"] == "text" else groups).append(node)
    outside = []
    for node in texts:
        owners = [g for g in groups if g["x"] + 24 <= node["x"]
                  and g["y"] + 60 <= node["y"]
                  and node["x"] + node["width"] <= g["x"] + g["width"] - 24
                  and node["y"] + node["height"] <= g["y"] + g["height"] - 24]
        require(len(owners) <= 1, "Multiple owner groups")
        if not owners:
            outside.append(node)
    require(len(outside) == 1, "Expected one ungrouped entry node")
    require(all(outside[0]["y"] + outside[0]["height"] <= g["y"] for g in groups), "Entry is not above groups")
    for peers in (groups, texts):
        for i, node in enumerate(peers):
            require(all(not overlaps(node, other) for other in peers[i + 1:]), "Overlapping peer nodes")
    node_ids = set(seen)
    for edge in canvas["edges"]:
        require({"id", "fromNode", "toNode"} <= set(edge) <= {"id", "fromNode", "toNode", "fromSide", "toSide", "color"}, "Edge fields")
        require(edge["id"] not in seen, "Duplicate edge ID")
        seen.add(edge["id"])
        require(edge["fromNode"] in node_ids and edge["toNode"] in node_ids, "Missing edge endpoint")
        for side in ("fromSide", "toSide"):
            require(side not in edge or edge[side] in {"top", "right", "bottom", "left"}, "Edge side")
        require("color" not in edge or edge["color"] in list("123456"), "Edge color")
    return {"nodes": len(nodes), "groups": len(groups), "edges": len(canvas["edges"])}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--installed", type=Path, default=Path(os.environ.get("APPDATA", "")) / "espanso/match/base.yml")
    parser.add_argument("--espanso", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    results = {}
    repo_path = ROOT / "base.yml"
    config = yaml.safe_load(repo_path.read_text(encoding="utf-8-sig"))
    matches = config["matches"]
    triggers = [m["trigger"] for m in matches]
    require(len(triggers) == len(set(triggers)) == 10, "Missing/duplicate triggers")
    require(set(triggers) == set(SOURCES) | {"/date"}, "Unexpected trigger set")
    require(repo_path.read_bytes() == args.installed.read_bytes(), "Repository/installed YAML differ")
    for trigger, relative in SOURCES.items():
        source = (ROOT / relative).read_text(encoding="utf-8").strip()
        expanded = next(m["replace"] for m in matches if m["trigger"] == trigger)
        require(source == expanded, f"Stale Espanso replacement: {trigger}")
        require(not source.startswith("```"), f"Whole-prompt fence: {trigger}")
        require("历史提问" in source, f"Missing knowledge synthesis rule: {trigger}")
        headings(source)
    results["prompt_sync"] = "9 sources match both YAML files; 10 unique triggers"
    for name in ("ai-game-development.md", "ai-game-completed.md", "ai-game-backend-prompt.md", "ai-game-history-synthesis.md"):
        results[name] = validate_note(ROOT / "tests/outputs" / name)
    history_input = (ROOT / "tests/inputs/followup-history.md").read_text(encoding="utf-8")
    synthesized = (ROOT / "tests/outputs/ai-game-history-synthesis.md").read_text(encoding="utf-8")
    questions = [line[2:] for line in history_input.splitlines() if line.startswith("- ")]
    require(all(question not in synthesized for question in questions), "History questions were copied into the note")
    results["history_synthesis"] = f"{len(questions)} source questions are not repeated; no Q/A packaging"
    completed = (ROOT / "tests/outputs/ai-game-completed.md").read_text(encoding="utf-8")
    require("[[NPC交互设计]]" in completed, "WikiLink was lost")
    original_headings = headings((ROOT / "tests/inputs/incomplete-note.md").read_text(encoding="utf-8"))
    completed_headings = headings(completed)
    indexes = [completed_headings.index(item) for item in original_headings]
    require(indexes == sorted(indexes), "Original heading order changed")
    results["completion_preservation"] = "Original headings, order and WikiLink retained"
    results["canvas"] = validate_canvas(ROOT / "tests/outputs/ai-game-development.canvas")
    edr_path = ROOT / "tests/outputs/edr-driver-knowledge.md"
    results[edr_path.name] = validate_note(edr_path)
    edr = edr_path.read_text(encoding="utf-8")
    original_edr = (ROOT / "tests/inputs/edr-draft.md").read_text(encoding="utf-8")
    core_terms = ("CreationStatus", "DesiredAccess", "OB_PREOP_SUCCESS", "STATUS_CALLBACK_BYPASS",
                  "FltRegisterFilter", "FltStartFiltering", "FLT_PREOP_COMPLETE", "FWPS_RIGHT_ACTION_WRITE")
    require(all(term in edr for term in core_terms), "EDR refinement dropped a core control mechanism")
    require(len(edr) < len(original_edr), "EDR refinement did not reduce source length")
    results["edr_expression"] = {
        "source_characters": len(original_edr), "result_characters": len(edr),
        "source_cjk": len(re.findall(r"[\u4e00-\u9fff]", original_edr)),
        "result_cjk": len(re.findall(r"[\u4e00-\u9fff]", edr)),
        "core_control_terms_retained": len(core_terms),
        "scope": "Presence and structure checks; semantic correctness requires review.",
    }
    results["v7_codefirst_trials"] = {
        name: codefirst_metrics(ROOT / "tests/outputs" / name)
        for name in ("edr-driver-knowledge.md", "ai-game-development.md")
    }
    if args.espanso:
        listed = subprocess.run([str(args.espanso), "match", "list", "--json"], capture_output=True, text=True, encoding="utf-8", timeout=20, check=True)
        runtime = json.loads(listed.stdout)
        require(isinstance(runtime, list), "Espanso match list is not an array")
        for trigger, relative in SOURCES.items():
            found = [item for item in runtime if trigger in item.get("triggers", [])]
            require(len(found) == 1, f"Missing/duplicate CLI trigger: {trigger}")
            require(found[0]["replace"] == (ROOT / relative).read_text(encoding="utf-8").strip(), f"Stale CLI body: {trigger}")
        results["espanso_cli"] = {"exit_code": listed.returncode, "matched_prompt_bodies": len(SOURCES)}
        status = subprocess.run([str(args.espanso), "service", "status"], capture_output=True, text=True, encoding="utf-8", timeout=20, check=True)
        require("espanso is running" in status.stdout, "Espanso daemon is not running")
        results["espanso_service"] = status.stdout.strip()
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "passed": True, "checks": results,
              "limits": "Structural checks only; semantic review is in validation-report.md. No target-app typing or Obsidian visual check."}
    if args.report:
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
