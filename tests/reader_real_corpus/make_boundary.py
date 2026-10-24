#!/usr/bin/env python3
"""Synthetic boundary fixtures, kept outside the real-corpus manifest.

They prove that malformed input is rejected with a recorded status instead of a
crash. They are never counted as real documents or acceptance evidence.
"""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--consumer", required=True)
    parser.add_argument("--font", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    fixtures = {
        "empty.txt": (b"", "TXT"),
        "truncated.epub": (b"PK\x03\x04", "EPUB"),
        "not-a-pdf.pdf": (b"this is not a PDF document\n", "PDF"),
    }
    records = []
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name, (data, fmt) in fixtures.items():
            source = root / name
            source.write_bytes(data)
            outdir = root / (name + ".out")
            outdir.mkdir()
            command = [args.consumer, "--format", fmt, "--file", str(source),
                       "--font", args.font, "--out", str(outdir), "--query", "boundary"]
            proc = subprocess.run(command, capture_output=True, text=True, timeout=120,
                                  encoding="utf-8", errors="replace")
            result = None
            for line in reversed([l for l in proc.stdout.splitlines() if l.strip()]):
                try:
                    result = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue
            clean = (proc.returncode == 0 and result is not None and
                     (result.get("ops", {}).get("open") == "failed" or
                      result.get("ops", {}).get("import") == "failed"))
            records.append({"fixture": name, "format": fmt, "bytes": len(data),
                            "exit_code": proc.returncode, "clean_rejection": clean,
                            "ops": (result or {}).get("ops"), "stderr": proc.stderr[-4000:]})
            ok = ok and clean
    Path(args.out).write_text(json.dumps({"schema": 1, "synthetic": True,
                                          "counted_as_real": False, "checks": records,
                                          "passed": ok}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"boundary_passed": ok, "checks": len(records)}))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
