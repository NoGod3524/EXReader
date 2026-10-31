"""Actions-only retained builds. No production/source rewrite and no automatic CI submission."""
import argparse
import hashlib
import importlib.abc
import importlib.util
import os
from pathlib import Path
import runpy
import sys
from identity import ROOT, SCOPE, identity, require, write_json

class SDK342Loader(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Version-only in-memory adapter; recorded source remains byte-for-byte unmodified."""
    def __init__(self, audit):
        self.audit = audit
        self.target = ROOT / "tests/reader_windows_raw3/host_build.py"
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "host_build":
            return importlib.util.spec_from_file_location(fullname, self.target, loader=self)
        return None
    def create_module(self, spec):
        return None
    def exec_module(self, module):
        text = self.target.read_text(encoding="utf-8")
        require("3.41.0" in text, "frozen Windows helper version no longer matches")
        adapted = text.replace("3.41.0", SCOPE["sdk_version"])
        self.audit.append({"path": str(self.target.relative_to(ROOT)),
                           "original_sha256": hashlib.sha256(text.encode()).hexdigest(),
                           "adapted_sha256": hashlib.sha256(adapted.encode()).hexdigest(),
                           "replacement": ["3.41.0", SCOPE["sdk_version"]],
                           "occurrences": text.count("3.41.0")})
        exec(compile(adapted, str(self.target), "exec"), module.__dict__)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", choices=["windows", "macos", "iphone", "ipad"], required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    stamp = identity()
    changes = []
    accepted = False
    try:
        if a.host == "windows":
            require(os.name == "nt", "Windows build requires Windows runner")
            loader = SDK342Loader(changes)
            sys.meta_path.insert(0, loader)
            path = ROOT / "tests/reader_wave3_c09/build.py"
            text = path.read_text(encoding="utf-8")
            require("3.41.0" in text, "frozen C09 version no longer matches")
            adapted = text.replace("3.41.0", SCOPE["sdk_version"])
            changes.append({"path": str(path.relative_to(ROOT)),
                            "original_sha256": hashlib.sha256(text.encode()).hexdigest(),
                            "adapted_sha256": hashlib.sha256(adapted.encode()).hexdigest(),
                            "replacement": ["3.41.0", SCOPE["sdk_version"]],
                            "occurrences": text.count("3.41.0")})
            sys.argv = [str(path)]
            exec(compile(adapted, str(path), "exec"),
                 {"__name__": "__main__", "__file__": str(path), "__package__": None})
        else:
            require(sys.platform == "darwin", "Apple build requires macOS runner")
            os.environ["EXR_APPLE_SDK_VERSION"] = SCOPE["sdk_version"]
            target = "macos" if a.host == "macos" else "iphonesimulator"
            path = ROOT / "tests/apple_sdk342_host/build.py"
            sys.argv = [str(path), "--target", target]
            runpy.run_path(str(path), run_name="__main__")
        accepted = True
    finally:
        write_json(a.output, {**stamp, "host": a.host, "build_completed": accepted,
                              "sdk_version": SCOPE["sdk_version"], "in_memory_adapters": changes,
                              "product_source_changed": False, "complete_product_accepted": False})
if __name__ == "__main__":
    main()
