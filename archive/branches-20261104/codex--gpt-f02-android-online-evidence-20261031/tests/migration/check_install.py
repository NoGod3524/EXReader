"""Check the installed migration payload against its source bytes in Actions."""
import hashlib
import os
from pathlib import Path
import sys

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("Run this installation check in GitHub Actions")

root = Path(__file__).resolve().parents[2]
prefix = Path(sys.argv[1])
payload = prefix / "share/exreader-legacy-migration"
files = {
    "exporter/exr-legacy-export.js": root / "extras/migration/exporter/exr-legacy-export.js",
    "exporter/backup_to_pack.py": root / "extras/migration/exporter/backup_to_pack.py",
    "WP12-LEGACY-MIGRATION.md": root / "docs/WP12-LEGACY-MIGRATION.md",
    "WP12-MIGRATION-REVIEW.md": root / "docs/WP12-MIGRATION-REVIEW.md",
    "LICENSE": root / "LICENSE",
}
for name, source in files.items():
    installed = payload / name
    data = installed.read_bytes()
    if not data or data != source.read_bytes():
        raise SystemExit("missing, empty or changed installed payload: " + name)
    print(name, hashlib.sha256(data).hexdigest())
print("installed migration payload verified:", len(files))
