"""Real GTK retained organization and DAV relay phases; never replaces native UI with SQL writes."""
import argparse
from pathlib import Path
import subprocess
import sys
from identity import ROOT, identity, require, snapshot_receipt, write_json

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["retained", "relay-first", "relay-return", "snapshot"], required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--package", type=Path, required=True)
    p.add_argument("--command-consumer", type=Path)
    p.add_argument("--inspect", type=Path)
    p.add_argument("--previous", type=Path)
    p.add_argument("--database", type=Path)
    a = p.parse_args()
    stamp = identity()
    require(sys.platform.startswith("linux"), "GTK Linux runner required")
    program = a.package / "bin/exreader-linux"
    require(program.is_file(), "actual GTK product missing")
    if a.mode == "snapshot":
        require(a.database is not None, "database required")
        snapshot_receipt("gtk", a.database, program, a.output, "readonly-projection")
        return
    if a.mode == "retained":
        require(a.command_consumer is not None and a.command_consumer.is_file(),
                "unchanged original command consumer required")
        command = [sys.executable, str(ROOT / "tests/linux_host/check_collections_ui.py"),
                   "--payload", str(a.package), "--command-consumer", str(a.command_consumer),
                   "--output", str(a.output)]
    else:
        require(a.previous is not None and a.previous.is_file(), "previous actual wire snapshot required")
        require(a.inspect is not None and a.inspect.is_file(), "public SDK readback consumer required")
        command = [sys.executable, str(ROOT / "tests/reader_windows_gtk_interop/gtk.py"),
                   "--phase", "gtk-first" if a.mode == "relay-first" else "gtk-return",
                   "--previous", str(a.previous), "--out", str(a.output),
                   "--package", str(a.package), "--inspect", str(a.inspect)]
    result = subprocess.run(command, cwd=ROOT, check=False)
    write_json(a.output.parent / (a.output.name + "-driver.json"),
               {**stamp, "host": "gtk", "mode": a.mode, "argv": command,
                "exit_code": result.returncode, "complete_product_accepted": False,
                "scope": "unchanged retained native UI or original two-host tag relay only"})
    require(result.returncode == 0, "original GTK failure retained")
if __name__ == "__main__":
    main()
