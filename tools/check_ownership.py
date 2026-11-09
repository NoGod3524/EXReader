#!/usr/bin/env python3
"""Check that OWNERSHIP.md has an explicit row for every public SDK symbol."""
import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def public_symbols(root=ROOT):
    """Read public declarations, including structs with member semicolons."""
    types, functions = {}, {}
    headers = sorted((root / "include" / "exr").glob("*.h"))
    headers.append(root / "include" / "exreader.h")
    for path in headers:
        text = re.sub(r"/\*.*?\*/|//[^\n]*", "", path.read_text(encoding="utf-8"), flags=re.S)
        text = re.sub(r"^\s*#.*$", "", text, flags=re.M)
        header = path.relative_to(root).as_posix()
        for start in re.finditer(r"\btypedef\b", text):
            depth, end = 0, start.end()
            while end < len(text):
                char = text[end]
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                elif char == ";" and depth == 0:
                    break
                end += 1
            declaration = " ".join(text[start.end():end].split())
            name = re.search(r"\(\s*\*\s*(exr_\w+)\s*\)", declaration) if "{" not in declaration else None
            if name is None:
                name = re.search(r"\b(exr_\w+)\s*$", declaration)
            if name:
                types[name.group(1)] = {"header": header, "declaration": declaration}
        for match in re.finditer(r"\bEXR_API\s+([^;]+);", text):
            declaration = " ".join(match.group(1).split())
            name = re.search(r"\b(exr_\w+)\s*\(", declaration)
            if name is None:
                raise ValueError(f"Unrecognized public function: {header}: {declaration}")
            functions[name.group(1)] = {"header": header, "declaration": declaration}
    return types, functions


def check(root=ROOT):
    types, functions = public_symbols(root)
    document = (root / "docs" / "OWNERSHIP.md").read_text(encoding="utf-8")
    sections = document.split("<!-- FUNCTION CONTRACTS -->")
    if len(sections) != 2:
        raise ValueError("Missing unique FUNCTION CONTRACTS section marker")
    # Only table cells in the first column count, never incidental mentions.
    def rows(section):
        return set(re.findall(r"^\| `(?:type:|function:)?(exr_\w+)` \|", section, flags=re.M))
    type_rows, function_rows = map(rows, sections)
    result = {
        "types": {"covered": len(set(types) & type_rows), "total": len(types),
                  "missing": sorted(set(types) - type_rows), "stale": sorted(type_rows - set(types))},
        "functions": {"covered": len(set(functions) & function_rows), "total": len(functions),
                      "missing": sorted(set(functions) - function_rows), "stale": sorted(function_rows - set(functions))},
    }
    result["passed"] = all(not group["missing"] and not group["stale"] for key, group in result.items() if key != "passed")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = check()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for kind in ("types", "functions"):
            group = report[kind]
            print(f"{kind}: {group['covered']}/{group['total']}")
            for problem in ("missing", "stale"):
                if group[problem]:
                    print(f"  {problem}: {', '.join(group[problem])}")
        print("OWNERSHIP coverage: " + ("PASS" if report["passed"] else "FAIL"))
    raise SystemExit(0 if report["passed"] else 1)
