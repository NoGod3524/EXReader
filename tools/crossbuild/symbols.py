#!/usr/bin/env python3
"""Compare every named dynamic export in a five-platform binary cohort."""
import argparse
import hashlib
import json
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/abi"))
from check_exports import inspect_bytes

PLATFORMS = {"windows", "linux", "macos", "android", "ios"}


def public_symbols(directory):
    symbols = set()
    for header in Path(directory).glob("*.h"):
        text = re.sub(r"/\*.*?\*/|//[^\n]*", "", header.read_text(encoding="utf-8"), flags=re.S)
        symbols.update(re.findall(r"EXR_API[^;]*?\b(exr_[A-Za-z0-9_]+)\s*\(", text))
    if not symbols:
        raise ValueError("no EXR_API declarations found")
    return symbols


def inspect_shared(path):
    data = Path(path).read_bytes()

    def require_shared(blob):
        magic = blob[:4]
        if blob.startswith(b"!<arch>\n"):
            raise ValueError("an archive's global definitions are not dynamic exports")
        if blob.startswith(b"\x7fELF") and int.from_bytes(blob[16:18], "little" if blob[5] == 1 else "big") != 3:
            raise ValueError("ELF input must be a shared object (ET_DYN)")
        if magic in (b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xfe\xed\xfa\xce"):
            if int.from_bytes(blob[12:16], "little" if magic[0] in (0xcf, 0xce) else "big") != 6:
                raise ValueError("Mach-O input must be MH_DYLIB; object definitions are not exports")
        if magic in (b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf", b"\xbe\xba\xfe\xca", b"\xbf\xba\xfe\xca"):
            endian = ">" if magic[0] == 0xca else "<"
            wide = magic in (b"\xca\xfe\xba\xbf", b"\xbf\xba\xfe\xca")
            count, = struct.unpack_from(endian + "I", blob, 4)
            for i in range(count):
                entry = struct.unpack_from(endian + ("IIQQII" if wide else "IIIII"), blob, 8 + i * (32 if wide else 20))
                require_shared(blob[entry[2]:entry[2] + entry[3]])

    require_shared(data)
    parts = inspect_bytes(data)
    # A universal binary must retain a separate observation for each slice.
    return data, parts


def reason(symbol, public):
    if symbol == "__emutls_get_address":
        return "Android NDK compiler-rt emulated TLS helper exported by the unrestricted ELF link"
    if symbol in public:
        return "Public EXR_API declaration; a missing export indicates differing source, enabled modules, or an export-list defect"
    if symbol.startswith("exr_"):
        return "EXReader internal definition absent from public EXR_API headers; unrestricted ELF/Mach-O link exposes it"
    return "Statically linked dependency/internal definition; unrestricted ELF/Mach-O link exposes it"


def compare(rows, public):
    sets = {row["platform"]: set(row["symbols"]) for row in rows}
    if len(rows) != 5 or set(sets) != PLATFORMS:
        raise ValueError("supply exactly one selected slice for each of windows/linux/macos/android/ios")
    common = set.intersection(*sets.values())
    union = set.union(*sets.values())
    differences = [{"name": name, "present_on": sorted(p for p, names in sets.items() if name in names),
                    "absent_on": sorted(p for p, names in sets.items() if name not in names),
                    "reason": reason(name, public)} for name in sorted(union - common)]
    platform_results = []
    for row in rows:
        platform = row["platform"]
        others = set.union(*(names for p, names in sets.items() if p != platform))
        names = sets[platform]
        platform_results.append({**row, "symbols": sorted(names), "export_count": len(names),
                                 "unique_symbols": sorted(names - others),
                                 "unique_count": len(names - others),
                                 "beyond_common_count": len(names - common),
                                 "missing_from_union": sorted(union - names)})
    return {"schema": 1,
            "comparison_scope": "All named dynamic exports; not only exr_* and not archive definitions",
            "normalization": "Mach-O removes exactly one leading ABI underscore; PE/ELF names are unchanged",
            "common_count": len(common), "common_symbols": sorted(common),
            "union_count": len(union), "difference_count": len(differences),
            "desktop_sets_equal": sets["windows"] == sets["linux"] == sets["macos"],
            "all_sets_equal": len({tuple(sorted(names)) for names in sets.values()}) == 1,
            "platforms": platform_results, "differences": differences}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", type=Path, help="JSON list of platform/path/source_commit; optional machine selects a fat slice")
    parser.add_argument("--public-headers", type=Path, default=ROOT / "include/exr")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-desktop-equal", action="store_true")
    args = parser.parse_args()
    try:
        rows = []
        for entry in json.loads(args.inputs.read_text(encoding="utf-8")):
            data, parts = inspect_shared(entry["path"])
            if "machine" in entry:
                parts = [part for part in parts if part["machine"] == entry["machine"]]
            if len(parts) != 1:
                raise ValueError(f"{entry['platform']}: select exactly one machine, found {len(parts)} slices")
            rows.append({**entry, **parts[0], "size_bytes": len(data),
                         "sha256": hashlib.sha256(data).hexdigest()})
        report = compare(rows, public_symbols(args.public_headers))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"common={report['common_count']} differences={report['difference_count']} desktop_equal={report['desktop_sets_equal']}")
        for row in report["platforms"]:
            print(f"{row['platform']}: exports={row['export_count']} unique={row['unique_count']} beyond_common={row['beyond_common_count']}")
        return int(args.require_desktop_equal and not report["desktop_sets_equal"])
    except (OSError, ValueError, KeyError, IndexError, struct.error) as error:
        parser.exit(2, f"error: {error}\n")


if __name__ == "__main__":
    sys.exit(main())
