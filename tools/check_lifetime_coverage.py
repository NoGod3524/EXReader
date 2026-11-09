#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Audit Debug allocation coverage for every public opaque SDK handle.

This source audit checks EXR_NEW sites, the runtime counter inventory, and raw
malloc/calloc/realloc expressions naming a handle type or sizeof(*handle).
It does not count embedded/stack values as heap constructors. API/dependency
behavior is checked separately by test_lifetime.c.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import re

from check_ownership import ROOT, public_symbols


def clean(text):
    # Preserve offsets and line numbers, including string literals with braces.
    return re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
                  lambda match: "".join("\n" if c == "\n" else " " for c in match[0]),
                  text, flags=re.S)


def call_end(text, opening):
    depth = 1
    for pos in range(opening + 1, len(text)):
        if text[pos] == "(":
            depth += 1
        elif text[pos] == ")":
            depth -= 1
            if not depth:
                return pos + 1
    raise ValueError("Unbalanced allocation expression")


def record_fields(sources):
    """Map each concrete C struct to its pointer member types."""
    fields = defaultdict(dict)
    for text in sources.values():
        for match in re.finditer(r"\b(typedef\s+)?struct(?:\s+(\w+))?\s*\{", text):
            depth, end = 1, match.end()
            while depth and end < len(text):
                if text[end] == "{":
                    depth += 1
                elif text[end] == "}":
                    depth -= 1
                end += 1
            suffix = re.match(r"\s*(\w+)\s*;", text[end:]) if match[1] else None
            name = suffix[1] if suffix else match[2]
            if not name:
                continue
            for statement in text[match.end():end - 1].split(";"):
                member = re.search(r"\b(\w+)\s*\*\s*(\w+)\b", statement)
                if member:
                    fields[name][member[2]] = member[1]
                    for extra in re.findall(r",\s*\*\s*(\w+)", statement[member.end():]):
                        fields[name][extra] = member[1]
    return fields


def raw_allocations(text, opaque, fields):
    """Find handle allocations which bypass EXR_NEW, without requiring a compiler."""
    findings = []
    # The enclosing top-level compound includes function parameters/local types.
    blocks, stack = [], []
    for pos, char in enumerate(text):
        if char == "{":
            stack.append(pos)
        elif char == "}" and stack:
            opening = stack.pop()
            if not stack:
                blocks.append((opening, pos))
    for match in re.finditer(r"\b(malloc|calloc|realloc)\s*\(", text):
        end = call_end(text, match.end() - 1)
        expression = text[match.start():end]
        before = text[max(0, match.start() - 100):match.start()]
        detected = {name for name in opaque if re.search(r"\b" + name + r"\b", expression)}
        detected.update(re.findall(r"\(\s*(exr_\w+)\s*\*\s*\)\s*$", before))
        for operand in re.findall(r"sizeof\s*\(\s*\*\s*([\w.>\-]+)\s*\)", expression):
            start = next((a for a, b in blocks if a <= match.start() < b), 0)
            # Include the signature, but not an earlier function body.
            start = max(text.rfind("}", 0, start), text.rfind(";", 0, start)) + 1
            scope = text[start:match.start()]
            parts = re.split(r"->|\.", operand)
            declarations = list(re.finditer(r"\b([A-Za-z_]\w*)\s*\*\s*" + re.escape(parts[0]) + r"\b", scope))
            if declarations:
                kind = declarations[-1][1]
                for field in parts[1:]:
                    kind = fields.get(kind, {}).get(field)
                if kind:
                    detected.add(kind)
        detected &= opaque
        if detected:
            findings.append({"line": text.count("\n", 0, match.start()) + 1,
                             "types": sorted(detected), "expression": " ".join(expression.split())})
    return findings


def audit(root=ROOT):
    types, _ = public_symbols(root)
    opaque = {name for name, info in types.items()
              if re.fullmatch(r"struct\s+" + name + r"\s+" + name, info["declaration"])}
    # This forward declaration has a public body and caller-owned storage.
    opaque.discard("exr_bitmap")
    sources = {path: clean(path.read_text(encoding="utf-8"))
               for path in (root / "src").glob("*.[ch]")}
    fields = record_fields(sources)
    sites = defaultdict(list)
    raw = []
    for path, text in sources.items():
        if path.suffix != ".c" or path.name.startswith("lifetime_api_"):
            continue
        relative = path.relative_to(root).as_posix()
        for match in re.finditer(r"\bEXR_NEW\s*\(\s*(exr_\w+)\s*\)", text):
            sites[match[1]].append(f"{relative}:{text.count(chr(10), 0, match.start()) + 1}")
        for finding in raw_allocations(text, opaque, fields):
            raw.append({"file": relative, **finding})
    runtime = sources[root / "src/lifetime.c"]
    counted = set(re.findall(r"\bCOUNT\(\s*((?:exr_\w+)|sdk_buffer)\s*\)", runtime))
    result = {
        "opaque_types": len(opaque),
        "covered_types": len(opaque & set(sites)),
        "constructor_sites": sum(len(value) for value in sites.values()),
        "runtime_counter_rows": len(counted),
        "sdk_buffer_counter": "sdk_buffer" in counted,
        "missing_constructors": sorted(opaque - set(sites)),
        "unrecognized_constructors": sorted(set(sites) - opaque),
        "missing_counters": sorted(opaque - counted),
        "unrecognized_counters": sorted(counted - opaque - {"sdk_buffer"}),
        "raw_handle_allocations": raw,
        "types": {name: {"constructors": len(sites[name]), "sites": sites[name]}
                  for name in sorted(opaque)},
    }
    result["passed"] = result["sdk_buffer_counter"] and not any(result[name] for name in (
        "missing_constructors", "unrecognized_constructors", "missing_counters",
        "unrecognized_counters", "raw_handle_allocations"))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = audit()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"opaque types: {report['covered_types']}/{report['opaque_types']}")
        print(f"EXR_NEW constructor sites: {report['constructor_sites']}")
        print(f"Runtime counter rows: {report['runtime_counter_rows']} (sdk_buffer={report['sdk_buffer_counter']})")
        for key in ("missing_constructors", "unrecognized_constructors", "missing_counters",
                    "unrecognized_counters", "raw_handle_allocations"):
            if report[key]:
                print(f"{key}: {report[key]}")
        print("Lifetime allocation coverage: " + ("PASS" if report["passed"] else "FAIL"))
    raise SystemExit(0 if report["passed"] else 1)
