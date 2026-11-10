# SPDX-License-Identifier: MIT
"""Build the host checks, run them, and retain byte/hash evidence. Stdlib only."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", default="Release")
    parser.add_argument("--clean-first", action="store_true")
    args = parser.parse_args()
    build, output = args.build.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text('{"automated_checks":"running"}\n', encoding="utf-8")

    def run(command, name):
        result = subprocess.run(command, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=300)
        log = result.stdout + result.stderr
        (output / name).write_text(log, encoding="utf-8")
        print(log, end="")
        if result.returncode:
            raise SystemExit(f"Failed ({result.returncode}): {command}")
        return log

    command = ["cmake", "--build", str(build), "--config", args.config,
               "--target", "EXReader", "check_shell_edit_model", "check_shell_edit_ui",
               "--parallel", "4"]
    if args.clean_first:
        command.append("--clean-first")
    log = run(command, "build.log")
    if "warning:" in log.lower():
        raise SystemExit("Compiler warning in build.log")
    for name in ("check_shell_edit_model", "check_shell_edit_ui"):
        executable = build / (name + ".exe")
        if not executable.exists():
            executable = build / args.config / (name + ".exe")
        run([str(executable), str(output)], name + ".log")
    run([str(executable), "--reopen", str(output)], "fresh-process-reopen.log")

    pairs = [("undo-before", "undo-after"), ("redo-before", "redo-after"),
             ("ui-undo-before", "ui-undo-after"), ("ui-redo-before", "ui-redo-after"),
             ("ui-before-save", "ui-after-reopen"),
             ("ui-before-save", "process-after-reopen")]
    hashes = {}
    for before, after in pairs:
        a, b = output / (before + ".utf8"), output / (after + ".utf8")
        if a.read_bytes() != b.read_bytes():
            raise SystemExit(f"Content mismatch: {before} != {after}")
        for path in (a, b):
            hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    docx = output / "roundtrip.docx"
    hashes[docx.name] = hashlib.sha256(docx.read_bytes()).hexdigest()
    with zipfile.ZipFile(docx) as archive:
        if archive.testzip():
            raise SystemExit("Invalid DOCX ZIP")
        root = ET.fromstring(archive.read("word/document.xml"))
    w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    text = "\n".join("".join(t.text or "" for t in p.iter(w + "t"))
                     for p in root.iter(w + "p"))
    if text.encode("utf-8") != (output / "ui-before-save.utf8").read_bytes():
        raise SystemExit("DOCX XML content differs from the host model")
    report = {"automated_checks": "pass", "warnings": 0, "undo": 20, "redo": 20,
              "sha256": hashes,
              "interactive_checks": "pending: real-window caret/selection/IME/close-prompt screenshots and Microsoft Pinyin input"}
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
