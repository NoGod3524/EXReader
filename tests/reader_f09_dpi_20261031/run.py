# SPDX-License-Identifier: MIT
"""Actions-only build of the DPI-aware Windows host for a local Narrator highlight check.

Reuses the narrator-package build (same SDK, same packager, 26-check self-test). The guard now
allows exactly the ten DPI product files to differ from the parent and statically checks the
intended shape. CI runs at 96 DPI, so it cannot show scaling; the highlight check is manual.
"""
import importlib.util
import os
from pathlib import Path
import subprocess
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("f09_narrator_build", ROOT / "tests/reader_f09_narrator_package_20261031/run.py")
nb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nb)
PARENT = "1e3a1bc66b9465e42a3afb3cd72c8294d0bfcf39"
PRODUCT = {"examples/reader.c"} | {"apps/reader/desktop/" + n for n in (
    "windows_accounts_ui.inc", "windows_compact_ui.inc", "windows_import_organize_ui.inc",
    "windows_metadata_ui.inc", "windows_navigation.inc", "windows_preferences_ui.inc",
    "windows_records.inc", "windows_search.inc", "windows_wave3.inc")}
NEW = {"tests/reader_f09_dpi_20261031/run.py", ".github/workflows/dot-f09-dpi-aware-20261031.yml",
       "docs/reader-total-progress/DOT_F09_DPI_AWARE_20261031.md"}
def git(*argv):
    return subprocess.check_output(["git", *argv], cwd=ROOT, text=True).strip()
def guard():
    assert os.environ.get("GITHUB_ACTIONS") == "true", "Actions only"
    actual = git("rev-parse", "HEAD")
    assert actual == os.environ["GITHUB_SHA"]
    delta = set(git("diff", "--name-only", PARENT, "HEAD").splitlines())
    assert delta == PRODUCT | NEW, delta ^ (PRODUCT | NEW)
    # The provider and the a835 routing hunks must be untouched by this change.
    assert git("hash-object", "--path=apps/reader/desktop/windows_accessibility.inc",
               "apps/reader/desktop/windows_accessibility.inc") == git("rev-parse", PARENT + ":apps/reader/desktop/windows_accessibility.inc")
    reader = (ROOT / "examples/reader.c").read_text(encoding="utf-8")
    assert "host_init_dpi();" in reader and "SetProcessDpiAwarenessContext" in reader
    assert reader.count("GetStockObject(DEFAULT_GUI_FONT)") == 1, "only the helper fallback may use the stock font"
    assert "int selection_changed = g.selection.active;" in reader and "DLGC_WANTMESSAGE" in reader
    for rel in PRODUCT - {"examples/reader.c"}:
        assert "DEFAULT_GUI_FONT" not in (ROOT / rel).read_text(encoding="utf-8"), rel
    return actual
nb.PARENT = PARENT
nb.guard = guard
nb.OUT = ROOT / "build/f09-narrator-package"
if __name__ == "__main__":
    nb.main()
