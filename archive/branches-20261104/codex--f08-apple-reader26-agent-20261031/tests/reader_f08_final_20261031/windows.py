"""Build the original full Windows native package from the final admitted source."""
import argparse
import importlib.util
import json
import shutil
from pathlib import Path

from source import ROOT, admission, need, sha

NATIVE = ROOT / "tests/reader_f08_windows_native_frame_20261031/build.py"
REQUIRED_HELPERS = {
    "tests/reader_perf_windows/perf_windows.py",
    "tests/reader_perf_windows/diagnose_txt_import.py",
    "tests/reader_perf_windows/verify_composition.py",
    "tests/reader_product_performance_handoff/sample_windows_interactions.py",
}

def copy_checked(relative, destination, expected):
    source = ROOT / relative
    need(sha(source) == expected, "source snapshot changed: " + relative)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    need(sha(destination) == expected, "packaged source differs: " + relative)

def package_sources(admitted, evidence):
    evidence = Path(evidence)
    evidence.mkdir(parents=True, exist_ok=True)
    helpers = None
    try:
        for relative, digest in admitted["adapter_files"].items():
            copy_checked(relative, evidence / "final-source" / relative, digest)
        path = evidence / "build-identity.json"
        if path.is_file():
            built = json.loads(path.read_text(encoding="utf-8"))
            need(all(built[k] == admitted[k] for k in ("source_sha", "run_id", "attempt")),
                 "same final source/run build identity")
            helpers = built["unchanged_helpers"]
            need(REQUIRED_HELPERS <= set(helpers), "complete native_full helper identities")
            for relative, digest in helpers.items():
                copy_checked(relative, evidence / "native-helpers" / relative, digest)
    finally:
        (evidence / "final-source.json").write_text(json.dumps({**admitted,
            "platform": "windows", "native_full_helper_root": "native-helpers",
            "native_helpers": helpers, "all_ui_frame_census_complete": False,
            "f08_accepted": False}, indent=2) + "\n", encoding="utf-8")

def build():
    spec = importlib.util.spec_from_file_location("final_windows_native_build", NATIVE)
    native = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(native)
    native.guard = admission
    original_seal = native.B.seal
    def seal():
        try:
            package_sources(admission(), native.B.EVIDENCE)
        finally:
            original_seal()
    native.B.seal = seal
    native.main()  # Original feature flags, package checks, six CTests and controls.

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("guard", "build"))
    mode = parser.parse_args().mode
    if mode == "guard":
        print(json.dumps(admission(), indent=2))
    else:
        build()
