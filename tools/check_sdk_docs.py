#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check public API coverage, exact signatures, example copies and documentation links."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def declarations():
    result = {}
    headers = sorted((ROOT / "include").rglob("*.h"))
    for header in headers:
        source = header.read_text(encoding="utf-8")
        source = re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.S)
        for match in re.finditer(r"^EXR_API\s+([^;]+;)", source, re.M):
            signature = " ".join(match[1].split())
            name = re.search(r"\b(exr_\w+)\s*\(", signature)[1]
            result[name] = (signature, header.relative_to(ROOT).as_posix())
    return headers, result


def check(binary=None):
    headers, public = declarations()
    api = (ROOT / "docs/API.md").read_text(encoding="utf-8")
    contract = set(json.loads((ROOT / "tools/abi/contract.json").read_text(encoding="utf-8"))["symbols"])
    entries = list(re.finditer(r"^### `(exr_\w+)`\s*\n(.*?)(?=^### |^## |\Z)", api, re.M | re.S))
    names = [entry[1] for entry in entries]
    errors = []
    missing, extra = set(public) - set(names), set(names) - set(public)
    if missing: errors.append(f"undocumented functions: {sorted(missing)}")
    if extra: errors.append(f"nonpublic API entries: {sorted(extra)}")
    duplicates = [name for name, count in Counter(names).items() if count != 1]
    if duplicates: errors.append(f"duplicate entries: {duplicates}")
    abi = Counter()
    for entry in entries:
        name, body = entry[1], entry[2]
        for label in ("签名", "ABI", "参数", "返回与失败", "线程", "所有权"):
            if not re.search(rf"\*\*{label}\*\*\s*\S", body):
                errors.append(f"{name}: missing {label}")
        signature = re.search(r"\*\*签名\*\*\s*`([^`]+)`", body)
        if name in public and (not signature or re.sub(r"\s", "", signature[1]) != re.sub(r"\s", "", public[name][0])):
            errors.append(f"{name}: signature differs from header")
        classification = re.search(r"\*\*ABI\*\*\s*(稳定|实验|内部)", body)
        if classification:
            abi[classification[1]] += 1
            expected = "稳定" if name in contract else "实验"
            if classification[1] != expected:
                errors.append(f"{name}: expected {expected} per frozen contract")
        else:
            errors.append(f"{name}: invalid ABI classification")
    modules = []
    examples = []
    for section in re.split(r"(?=^## )", api, flags=re.M):
        if not re.search(r"^### `exr_", section, re.M): continue
        title = section.splitlines()[0].removeprefix("## ")
        modules.append(title)
        snippets = re.findall(r"<!-- example: (docs/examples/\w+\.c) -->\s*```c\n(.*?)\n```", section, re.S)
        if len(snippets) != 1:
            errors.append(f"{title}: expected one complete, extracted C example")
        for path, code in snippets:
            examples.append(path)
            if code.strip() != (ROOT / path).read_text(encoding="utf-8").strip():
                errors.append(f"{path}: embedded example differs from compiled source")
    sources = {path.relative_to(ROOT).as_posix() for path in (ROOT / "docs/examples").glob("*.c")}
    if set(examples) != sources or len(examples) != len(sources):
        errors.append("module examples and docs/examples/*.c do not match one-to-one")
    if len(modules) < 8: errors.append("fewer than 8 API modules")
    integration = (ROOT / "docs/INTEGRATION.md").read_text(encoding="utf-8")
    for term in ("生命周期", "事件循环", "渲染目标", "字体管理器", "标注", "```text"):
        if term not in integration: errors.append(f"integration guide missing {term}")
    matrix = (ROOT / "docs/CAPABILITY-MATRIX.md").read_text(encoding="utf-8")
    tables = re.findall(r"(?m)^\|[^\n]+\|$", matrix)
    matrix_rows = [row for row in tables if row.count("|") >= 8 and not re.match(r"^\|\s*[-:]", row)]
    # One header row per table; matrix has a single capability table.
    matrix_count = len(matrix_rows) - 1
    if matrix_count < 30: errors.append(f"capability matrix has only {matrix_count} rows")
    if "不支持" not in matrix: errors.append("capability matrix lacks explicit unsupported cells")
    for document in ("API", "INTEGRATION", "CAPABILITY-MATRIX"):
        path = ROOT / f"docs/{document}.md"
        content = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.S)
        for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", content):
            url = urlsplit(link)
            if not url.scheme and url.path and not (path.parent / unquote(url.path)).exists():
                errors.append(f"{document}: missing linked path {link}")
    exported = None
    if binary:
        sys.path.insert(0, str(ROOT / "tools/abi"))
        from check_exports import inspect
        exported = inspect(binary, set(public))
        for part in exported["slices"]:
            if part["missing"] or part["extra"]:
                errors.append(f"binary differs from public headers: missing={part['missing']} extra={part['extra']}")
    return {
        "public_headers": len(headers), "headers_declaring_functions": len({v[1] for v in public.values()}),
        "modules": len(modules), "module_names": modules,
        "documented_functions": len(set(names) & set(public)), "public_functions": len(public),
        "coverage_percent": round(100 * len(set(names) & set(public)) / len(public), 2),
        "frozen_contract_functions": len(contract), "abi": {label: abi[label] for label in ("稳定", "实验", "内部")},
        "examples": len(examples), "capability_rows": matrix_count,
        "binary": exported, "errors": errors, "passed": not errors,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, help="optionally compare the current aggregate DLL exports")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = check(args.binary)
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output: args.output.write_text(output, encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(output, end="")
    return int(not report["passed"])


if __name__ == "__main__":
    raise SystemExit(main())
