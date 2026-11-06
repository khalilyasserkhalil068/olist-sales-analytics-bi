"""Validate the curated local delivery without SQL writes or Power BI refresh.

Checks asset fingerprints, Markdown links, notebook validity, PBIX ZIP integrity,
and native report/model structure. This does not execute DAX or click the UI.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote
import zipfile

import nbformat

ROOT = Path(__file__).resolve().parents[1]
NAME = "OlistSalesDW_Final_5_Dashboards"
FINAL = ROOT / "power_bi/final"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate(source_only=False):
    checks = []

    def check(name, ok, details=None):
        checks.append({"name": name, "status": "PASS" if ok else "FAIL", "details": details})

    manifest = json.loads((ROOT / "reports/project_integrity.json").read_text(encoding="utf-8"))
    assets = [item for item in manifest["files"] if not (source_only and item.get("local_only", False))]
    changed = [item["path"] for item in assets
               if not (ROOT / item["path"]).is_file()
               or digest(ROOT / item["path"]) != item["sha256"]]
    check("Curated project assets match recorded fingerprints", not changed, changed)

    links, broken = 0, []
    documents = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]
    for document in documents:
        content = document.read_text(encoding="utf-8")
        content = re.sub(r"```.*?```", "", content, flags=re.S)
        for target in re.findall(r"\]\(([^)]+)\)", content):
            target = target.strip().strip("<>")
            if re.match(r"(?:https?://|mailto:|#)", target):
                continue
            path = unquote(target.split("#", 1)[0])
            links += 1
            if not (document.parent / path).exists():
                broken.append({"document": document.relative_to(ROOT).as_posix(), "target": target})
    check("Local Markdown references resolve", not broken, {"checked": links, "broken": broken})

    if not source_only:
        pbix = FINAL / f"{NAME}.pbix"
        with zipfile.ZipFile(pbix) as package:
            corrupt = package.testzip()
            # This accepted report uses native PBIR definitions inside the package.
            required = {"DataModel", "Version", "Report/definition/report.json",
                        "Report/definition/pages/pages.json"}
            missing = sorted(required - set(package.namelist()))
            saved_pages = json.loads(package.read("Report/definition/pages/pages.json"))["pageOrder"]
        check("Final PBIX package is intact", corrupt is None and not missing,
              {"corruptMember": corrupt, "missingMembers": missing, "savedPages": len(saved_pages)})
        check("Saved native PBIX contains five unique pages", len(saved_pages) == len(set(saved_pages)) == 5)

    report = FINAL / f"{NAME}.Report/definition"
    model = FINAL / f"{NAME}.SemanticModel/definition"
    meta = json.loads((report / "pages/pages.json").read_text(encoding="utf-8-sig"))
    tables = {}
    for path in (model / "tables").glob("*.tmdl"):
        text = path.read_text(encoding="utf-8-sig")
        tables[path.stem] = {
            "Column": {a or b for a, b in re.findall(r"^\tcolumn (?:'([^']+)'|([^\s=]+))", text, re.M)},
            "Measure": {a or b for a, b in re.findall(r"^\tmeasure (?:'([^']+)'|([^\s=]+)) =", text, re.M)},
        }
    counts = Counter()
    errors = []

    def fields(value):
        if isinstance(value, dict):
            for kind, field in value.items():
                if kind in ("Column", "Measure") and isinstance(field, dict):
                    table = field.get("Expression", {}).get("SourceRef", {}).get("Entity")
                    name = field.get("Property")
                    if table and (table not in tables or name not in tables[table][kind]):
                        errors.append(f"Unresolved {kind}: {table}[{name}]")
                fields(field)
        elif isinstance(value, list):
            for field in value:
                fields(field)

    for pid in meta["pageOrder"]:
        page = json.loads((report / "pages" / pid / "page.json").read_text(encoding="utf-8-sig"))
        visuals = [json.loads(p.read_text(encoding="utf-8-sig"))
                   for p in (report / "pages" / pid / "visuals").glob("*/visual.json")]
        ids = [v["name"] for v in visuals]
        if len(ids) != len(set(ids)):
            errors.append(f"Duplicate visual IDs: {pid}")
        if (page["width"], page["height"]) != (1600, 900):
            errors.append(f"Unexpected page size: {pid}")
        for visual in visuals:
            counts[visual["visual"]["visualType"]] += 1
            fields(visual)
            p = visual["position"]
            if p["x"] < 0 or p["y"] < 0 or p["x"] + p["width"] > 1600.01 or p["y"] + p["height"] > 900.01:
                errors.append(f"Visual outside canvas: {visual['name']}")
        for interaction in page.get("visualInteractions", []):
            if interaction["source"] not in ids or interaction["target"] not in ids:
                errors.append(f"Broken interaction reference: {pid}")
    charts = sum(n for t, n in counts.items() if t not in {"card", "slicer", "textbox", "pageNavigator"})
    check("Five native pages and expected visual inventory",
          len(set(meta["pageOrder"])) == len(meta["pageOrder"]) == 5
          and counts["card"] == 30 and counts["slicer"] == 19
          and counts["pageNavigator"] == 5 and charts == 29, dict(counts))
    check("Native field, layout and interaction references", not errors, errors)
    check("31 semantic tables and 58 measure declarations",
          len(tables) == 31 and sum(len(v["Measure"]) for v in tables.values()) == 58)

    relation_text = (model / "relationships.tmdl").read_text(encoding="utf-8-sig")
    blocks = re.split(r"(?m)^relationship ", relation_text)[1:]
    graph = defaultdict(list)
    relationship_errors = []
    for block in blocks:
        endpoints = {}
        for role in ("from", "to"):
            match = re.search(rf"(?m)^\s*{role}Column: ([^\n]+)", block)
            if match:
                endpoints[role] = match[1].strip().split(".")[0].strip("'")
        if len(endpoints) != 2:
            relationship_errors.append("Missing relationship endpoint")
            continue
        if "crossFilteringBehavior: bothDirections" in block:
            relationship_errors.append("Bidirectional relationship")
        if endpoints["from"].startswith("Fact") and endpoints["to"].startswith("Fact"):
            relationship_errors.append("Direct fact-to-fact relationship")
        if not re.search(r"isActive:\s*false", block):
            graph[endpoints["to"]].append(endpoints["from"])
    for origin in tables:
        reached = Counter()

        def walk(node, trail):
            for child in graph[node]:
                if child in trail:
                    relationship_errors.append(f"Cycle from {origin}")
                    continue
                reached[child] += 1
                walk(child, trail | {child})

        walk(origin, {origin})
        relationship_errors.extend(f"Multiple filter paths: {origin} to {target}"
                                   for target, n in reached.items() if n > 1)
    check("37 relationships with no cycles, ambiguous paths or fact-to-fact filters",
          len(blocks) == 37 and not relationship_errors, relationship_errors)

    notebooks = sorted((ROOT / "notebooks").glob("*.ipynb"))
    notebook_errors = []
    for path in notebooks:
        notebook = nbformat.read(path, as_version=4)
        nbformat.validate(notebook)
        cells = [c for c in notebook.cells if c.cell_type == "code"]
        if not cells or any(c.execution_count is None for c in cells):
            notebook_errors.append(f"Unexecuted code: {path.name}")
        if any(o.output_type == "error" for c in cells for o in c.outputs):
            notebook_errors.append(f"Saved error: {path.name}")
    check("Five valid executed notebooks without saved errors",
          len(notebooks) == 5 and not notebook_errors, notebook_errors)
    return {"scope": "Published source only" if source_only else "Full local delivery",
            "limitations": "No DAX execution or UI automation; source-only mode excludes private inputs, PBIX and caches",
            "excluded_local_assets": len(manifest["files"]) - len(assets),
            "passed": sum(c["status"] == "PASS" for c in checks),
            "failed": sum(c["status"] == "FAIL" for c in checks), "checks": checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-only", action="store_true",
                        help="Validate a GitHub checkout without local input CSVs, PBIX or caches")
    parser.add_argument("--output", type=Path, help="Optionally save the current verification result")
    args = parser.parse_args()
    result = validate(source_only=args.source_only)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    raise SystemExit(bool(result["failed"]))


if __name__ == "__main__":
    main()
