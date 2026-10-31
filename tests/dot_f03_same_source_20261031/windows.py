"""Run real retained Windows organization/relay UI. No manufactured revision or success."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
from identity import ROOT, identity, require, snapshot_receipt, write_json

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["retained", "relay-first", "relay-return", "snapshot"], required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--package", type=Path, required=True)
    p.add_argument("--fixtures", type=Path)
    p.add_argument("--probe", type=Path)
    p.add_argument("--command-consumer", type=Path)
    p.add_argument("--revision-consumer", type=Path)
    p.add_argument("--previous", type=Path)
    p.add_argument("--database", type=Path)
    a = p.parse_args()
    stamp = identity()
    require(os.name == "nt", "actual Windows runner required")
    exe = a.package / "EXReader.exe"
    require(exe.is_file(), "missing actual product executable")
    if a.mode == "snapshot":
        require(a.database is not None, "database required")
        snapshot_receipt("windows", a.database, exe, a.output, "readonly-projection")
        return
    require(a.probe is not None and a.probe.is_file(), "installed public readback probe required")
    if a.mode == "retained":
        require(all(x is not None and x.exists() for x in
                    (a.fixtures, a.command_consumer, a.revision_consumer)), "retained inputs missing")
        command = [sys.executable, str(ROOT / "tests/reader_windows_import_organize/check_ui.py"),
                   "--candidate", str(exe), "--font", str(a.package / "Reader.otf"),
                   "--fixtures", str(a.fixtures), "--cloud-probe", str(a.probe),
                   "--command-consumer", str(a.command_consumer),
                   "--revision-consumer", str(a.revision_consumer), "--output", str(a.output)]
    else:
        command = [sys.executable, str(ROOT / "tests/reader_windows_gtk_interop/windows.py"),
                   "--phase", "windows-first" if a.mode == "relay-first" else "windows-return",
                   "--out", str(a.output), "--package", str(a.package), "--probe", str(a.probe)]
        if a.mode == "relay-return":
            require(a.previous is not None and a.previous.is_file(), "real predecessor snapshot required")
            command += ["--previous", str(a.previous)]
    result = subprocess.run(command, cwd=ROOT, check=False)
    write_json(a.output.parent / (a.output.name + "-driver.json"),
               {**stamp, "host": "windows", "mode": a.mode, "argv": command,
                "exit_code": result.returncode, "complete_product_accepted": False,
                "scope": "unchanged native suite or original Windows/GTK tag relay only"})
    require(result.returncode == 0, "retained Windows failure; do not waive")
if __name__ == "__main__":
    main()
