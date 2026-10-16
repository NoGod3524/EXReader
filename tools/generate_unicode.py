#!/usr/bin/env python3
"""Generate EXReader's pinned Unicode tables (Python standard library only).

    python tools/generate_unicode.py --download
    python tools/generate_unicode.py --download --check

The first command populates build/unicode-cache and writes the generated header
and official test/license fixtures. The second verifies byte-for-byte output.
Normal C builds use the committed header and do not run this script or use the
network. Downloaded files are data, never executable Python or C sources.
"""

# SPDX-License-Identifier: GPL-3.0-only
import argparse
import hashlib
from pathlib import Path
import re
import sys
import urllib.request


VERSION = "17.0.0"
BASE_URL = f"https://www.unicode.org/Public/{VERSION}/ucd/"
# SHA-256 pins apply to the original bytes, including the official test corpus.
SOURCES = {
    "GraphemeBreakProperty.txt": (
        BASE_URL + "auxiliary/GraphemeBreakProperty.txt",
        "d6b51d1d2ae5c33b451b7ed994b48f1f4dc62b2272a5831e7fd418514a6bae89",
    ),
    "emoji-data.txt": (
        BASE_URL + "emoji/emoji-data.txt",
        "2cb2bb9455cda83e8481541ecf5b6dfda66a3bb89efa3fa7c5297eccf607b72b",
    ),
    "DerivedCoreProperties.txt": (
        BASE_URL + "DerivedCoreProperties.txt",
        "24c7fed1195c482faaefd5c1e7eb821c5ee1fb6de07ecdbaa64b56a99da22c08",
    ),
    "LineBreak.txt": (
        BASE_URL + "LineBreak.txt",
        "e6a18fa91f8f6a6f8e534b1d3f128c21ada45bfe152eb6b1bcc5e15fd8ac92e6",
    ),
    "GraphemeBreakTest.txt": (
        BASE_URL + "auxiliary/GraphemeBreakTest.txt",
        "e2d134d2c52919bace503ebb6a551c1855fe1a1faec18478c78fff254a1793ec",
    ),
    "LICENSE.txt": (
        "https://www.unicode.org/license.txt",
        "e7a93b009565cfce55919a381437ac4db883e9da2126fa28b91d12732bc53d96",
    ),
}
GCB = (
    "Other", "CR", "LF", "Control", "Extend", "ZWJ", "Regional_Indicator",
    "Prepend", "SpacingMark", "L", "V", "T", "LV", "LVT",
)
INCB = ("None", "Consonant", "Extend", "Linker")
LB = (
    "XX", "AI", "AK", "AL", "AP", "AS", "B2", "BA", "BB", "BK", "CB",
    "CJ", "CL", "CM", "CP", "CR", "EB", "EM", "EX", "GL", "H2", "H3",
    "HH", "HL", "HY", "ID", "IN", "IS", "JL", "JT", "JV", "LF", "NL",
    "NS", "NU", "OP", "PO", "PR", "QU", "RI", "SA", "SG", "SP", "SY",
    "VF", "VI", "WJ", "ZW", "ZWJ",
)
RANGE = re.compile(r"([0-9A-F]{4,6})(?:\.\.([0-9A-F]{4,6}))?\Z")


def source_data(name, cache, fixture_dir, download):
    """Read only bytes matching the pinned source; never silently update pins."""
    url, expected = SOURCES[name]
    fixture = fixture_dir / name
    path = fixture if name in ("GraphemeBreakTest.txt", "LICENSE.txt") and fixture.exists() else cache / name
    if path.exists():
        data = path.read_bytes()
    elif download:
        request = urllib.request.Request(url, headers={"User-Agent": "EXReader-Unicode-Generator/1"})
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
    else:
        raise ValueError(f"missing {path}; run again with --download")
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise ValueError(f"{path}: SHA-256 mismatch: expected {expected}, got {actual}")
    if not path.exists():
        cache.mkdir(parents=True, exist_ok=True)
        (cache / name).write_bytes(data)
    return data


def property_ranges(data, kind):
    values = {name: index for index, name in enumerate({"gcb": GCB, "incb": INCB, "lb": LB}.get(kind, ("No", "Extended_Pictographic")))}
    result = []
    for number, line in enumerate(data.decode("utf-8").splitlines(), 1):
        content = line.split("#", 1)[0].strip()
        if not content:
            continue
        fields = [field.strip() for field in content.split(";")]
        if kind == "incb":
            if len(fields) < 2 or fields[1] != "InCB":
                continue
            if len(fields) != 3:
                raise ValueError(f"InCB line {number}: invalid property fields")
            prop = fields[2]
        else:
            if len(fields) != 2:
                raise ValueError(f"{kind} line {number}: invalid property fields")
            prop = fields[1]
            if kind == "ep" and prop != "Extended_Pictographic":
                continue
        match = RANGE.fullmatch(fields[0])
        if not match or prop not in values:
            raise ValueError(f"{kind} line {number}: invalid range or unknown property")
        first, last = int(match[1], 16), int(match[2] or match[1], 16)
        result.append((first, last, values[prop]))
    # Validate default ranges as well, before excluding them from the C table.
    return merge_ranges(result)


def merge_ranges(ranges):
    result = []
    for first, last, value in sorted(ranges):
        if not 0 <= first <= last <= 0x10FFFF or not 0 <= value <= 255:
            raise ValueError("invalid Unicode interval")
        if result and first <= result[-1][1]:
            raise ValueError(f"overlapping Unicode intervals at U+{first:04X}")
        if result and first == result[-1][1] + 1 and value == result[-1][2]:
            result[-1] = (result[-1][0], last, value)
        else:
            result.append((first, last, value))
    return result


def check_hangul(ranges):
    """Check the algorithm used by the C classifier before omitting LV/LVT."""
    expected = 0xAC00
    for first, last, value in ranges:
        if value not in (GCB.index("LV"), GCB.index("LVT")):
            continue
        if first != expected or last > 0xD7A3:
            raise ValueError("unexpected Hangul syllable interval")
        for codepoint in range(first, last + 1):
            actual = "LVT" if (codepoint - 0xAC00) % 28 else "LV"
            if value != GCB.index(actual):
                raise ValueError("Hangul LV/LVT algorithm differs from Unicode data")
        expected = last + 1
    if expected != 0xD7A4:
        raise ValueError("incomplete Hangul syllable data")


def enum_lines(name, properties):
    result = [f"enum exr_{name} {{"]
    result.extend(f"    exr_{name}_{prop.lower()} = {index}," for index, prop in enumerate(properties))
    return result + ["};", ""]


def table_lines(name, ranges):
    result = [f"static const exr_unicode_range exr_{name}_ranges[] = {{"]
    # Compact source, with four intervals per line, keeps this header under 100KB.
    rows = [f"{{0x{first:X},0x{last:X},{value}}}," for first, last, value in ranges]
    result.extend("    " + "".join(rows[index:index + 4]) for index in range(0, len(rows), 4))
    return result + [
        "};",
        f"#define EXR_{name.upper()}_RANGE_COUNT (sizeof(exr_{name}_ranges) / sizeof(exr_{name}_ranges[0]))",
        "",
    ]


def generate(data):
    gcb = property_ranges(data["GraphemeBreakProperty.txt"], "gcb")
    check_hangul(gcb)
    tables = {
        "gcb": [r for r in gcb if r[2] not in (0, GCB.index("LV"), GCB.index("LVT"))],
        "incb": [r for r in property_ranges(data["DerivedCoreProperties.txt"], "incb") if r[2]],
        "ep": property_ranges(data["emoji-data.txt"], "ep"),
        "lb": [r for r in property_ranges(data["LineBreak.txt"], "lb") if r[2]],
    }
    lines = [
        "/* Generated by tools/generate_unicode.py; do not edit.",
        f" * Unicode {VERSION}; data license: Unicode-3.0.",
        " * Copyright (c) 1991-2026 Unicode, Inc. See tests/fixtures/unicode/LICENSE.txt.",
        " * Reproduce: python tools/generate_unicode.py --download --check",
        " * Sources and SHA-256:",
    ]
    for name, (url, sha256) in SOURCES.items():
        lines.extend([f" * {url}", f" *   {sha256}"])
    lines.extend([
        " */", "#ifndef EXR_UNICODE_DATA_H", "#define EXR_UNICODE_DATA_H", "",
        "#include <stdint.h>", "", f'#define EXR_UNICODE_VERSION "{VERSION}"', "",
        "typedef struct exr_unicode_range {",
        "    uint32_t first, last;",
        "    uint8_t value;",
        "} exr_unicode_range;", "",
    ])
    for name, properties in (("gcb", GCB), ("incb", INCB), ("lb", LB)):
        lines.extend(enum_lines(name, properties))
    lines.extend([
        "/* Omitted ranges have default property 0. Hangul GCB LV/LVT is computed",
        " * for U+AC00..U+D7A3: (cp - 0xAC00) % 28 == 0 means LV, otherwise LVT.",
        " * Extended_Pictographic has value 1. Tables are sorted and disjoint. */",
    ])
    for name, ranges in tables.items():
        lines.extend(table_lines(name, ranges))
    lines.extend(["#endif /* EXR_UNICODE_DATA_H */", ""])
    output = "\n".join(lines).encode("utf-8")
    if len(output) >= 100_000:
        raise ValueError(f"Unicode header unexpectedly exceeds 100KB: {len(output)} bytes")
    return output, tables


def self_check():
    if merge_ranges([(3, 4, 1), (1, 2, 1), (7, 8, 2)]) != [(1, 4, 1), (7, 8, 2)]:
        raise ValueError("interval merge self-check failed")
    for invalid in ([(1, 3, 1), (3, 4, 2)], [(-1, 2, 1)], [(4, 3, 1)], [(0, 0x110000, 1)]):
        try:
            merge_ranges(invalid)
        except ValueError:
            continue
        raise ValueError("invalid interval self-check failed")


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--download", action="store_true", help="fetch missing SHA-256-pinned Unicode data")
    parser.add_argument("--check", action="store_true", help="compare generated files without changing them")
    parser.add_argument("--cache-dir", type=Path, default=root / "build" / "unicode-cache")
    args = parser.parse_args()
    fixture_dir = root / "tests" / "fixtures" / "unicode"
    self_check()
    data = {name: source_data(name, args.cache_dir, fixture_dir, args.download) for name in SOURCES}
    header, tables = generate(data)
    outputs = {root / "src" / "unicode_data.h": header}
    outputs.update({fixture_dir / name: data[name] for name in ("GraphemeBreakTest.txt", "LICENSE.txt")})
    for path, content in outputs.items():
        if args.check:
            if not path.exists() or path.read_bytes() != content:
                raise ValueError(f"generated output differs: {path}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    print(f"Unicode {VERSION}: {len(header)}-byte header; " + ", ".join(f"{name}={len(ranges)}" for name, ranges in tables.items()))
    print("Generated files match." if args.check else "Generated header and official fixtures.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)
