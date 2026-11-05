#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate the fixed boundary corpus and its expected statuses.

Each fixture is a real input for an installed public API, and its expected
outcome is written into manifest.json before any consumer reads it. The
canonical preferences document mirrors the installed writer byte for byte, so a
save/load round trip can be compared with the seed itself.
"""
import hashlib
import json
import sys
from pathlib import Path

HEX32 = "0123456789abcdef0123456789abcdef"
HEX64 = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
EPUB = "epub:" + HEX64
PDF = "pdf:" + HEX64

CANONICAL_PREFERENCES = (
    "{\n"
    '  "format": "exreader-preferences",\n'
    '  "format_version": 1,\n'
    '  "font_size": 24,\n'
    '  "line_spacing": 1.6,\n'
    '  "paragraph_spacing": 12,\n'
    '  "margin": 48,\n'
    '  "theme": "light",\n'
    '  "page_turn_direction": "ltr",\n'
    '  "page_turn_input": "tap",\n'
    '  "fixed_page_zoom": 100,\n'
    '  "light_foreground": "#1A1A1AFF",\n'
    '  "light_background": "#FFFFFFFF",\n'
    '  "dark_foreground": "#E6E6E6FF",\n'
    '  "dark_background": "#101010FF"\n'
    "}\n"
)


def seed(relative, kind, data, status, fuzz=False, limit=0, decode=None):
    assert isinstance(data, bytes), relative
    return {
        "file": relative,
        "kind": kind,
        "data": data,
        "status": status,
        "fuzz": fuzz,
        "limit": limit,
        "decode": decode,
    }


def canonical_document():
    return json.loads(CANONICAL_PREFERENCES)


def preferences_seeds():
    seeds = [
        seed("preferences/valid.json", "preferences", CANONICAL_PREFERENCES.encode(), "OK", fuzz=True)
    ]

    limits = canonical_document()
    limits.update(
        {
            "font_size": 256,
            "line_spacing": 5,
            "paragraph_spacing": 1024,
            "margin": 0,
            "theme": "system",
            "page_turn_direction": "vertical",
            "page_turn_input": "hardware_keys",
            "fixed_page_zoom": 400,
            "light_foreground": "#123456",
            "light_background": "#000000",
            "dark_foreground": "#FFFFFF",
            "dark_background": "#ABCDEF",
        }
    )
    seeds.append(
        seed("preferences/valid_limits.json", "preferences", (json.dumps(limits, indent=2) + "\n").encode(), "OK", fuzz=True)
    )

    padded = CANONICAL_PREFERENCES.encode() + b" " * (65530 - len(CANONICAL_PREFERENCES))
    assert len(padded) == 65530
    seeds.append(seed("preferences/valid_64k.json", "preferences", padded, "OK", fuzz=True))

    seeds.append(
        seed("preferences/missing_field.json", "preferences", json.dumps({"format": "exreader-preferences"}).encode(), "FORMAT")
    )
    seeds.append(
        seed("preferences/truncated.json", "preferences", CANONICAL_PREFERENCES[: len(CANONICAL_PREFERENCES) // 2].encode(), "FORMAT")
    )
    seeds.append(
        seed(
            "preferences/unknown_version.json",
            "preferences",
            CANONICAL_PREFERENCES.replace('"format_version": 1', '"format_version": 2').encode(),
            "VERSION",
        )
    )
    seeds.append(
        seed(
            "preferences/duplicate_key.json",
            "preferences",
            CANONICAL_PREFERENCES.replace(
                '"format": "exreader-preferences",',
                '"format": "exreader-preferences",\n  "format": "exreader-preferences",',
            ).encode(),
            "FORMAT",
        )
    )
    seeds.append(
        seed(
            "preferences/nul_string.json",
            "preferences",
            CANONICAL_PREFERENCES.replace('"theme": "light"', '"theme": "li\x00ht"').encode(),
            "FORMAT",
        )
    )
    seeds.append(
        seed(
            "preferences/nan_number.json",
            "preferences",
            CANONICAL_PREFERENCES.replace('"font_size": 24', '"font_size": 1e999').encode(),
            "RANGE",
        )
    )
    seeds.append(
        seed(
            "preferences/leading_zero.json",
            "preferences",
            CANONICAL_PREFERENCES.replace('"font_size": 24', '"font_size": 024').encode(),
            "FORMAT",
        )
    )
    seeds.append(
        seed(
            "preferences/bad_color.json",
            "preferences",
            CANONICAL_PREFERENCES.replace('"#1A1A1AFF"', '"#12345"').encode(),
            "FORMAT",
        )
    )
    seeds.append(
        seed(
            "preferences/bad_enum.json",
            "preferences",
            CANONICAL_PREFERENCES.replace('"theme": "light"', '"theme": "sepia"').encode(),
            "FORMAT",
        )
    )
    overflow = CANONICAL_PREFERENCES.encode() + b" " * (65537 - len(CANONICAL_PREFERENCES))
    assert len(overflow) == 65537
    seeds.append(seed("preferences/overflow_limit.json", "preferences", overflow, "LIMIT"))
    return seeds


def rid(label):
    """A stable, distinct 32-hex revision id per seed (shared ids collide)."""
    return hashlib.sha256(label.encode("utf-8")).hexdigest()[:32]


def envelope(entity_kind, entity_key, location_kind, payload, version=1):
    return {
        "version": version,
        "id": rid(entity_kind + "/" + entity_key + "/" + location_kind),
        "entity_kind": entity_kind,
        "entity_key": entity_key,
        "operation": "put",
        "location_kind": location_kind,
        "parents": [],
        "payload": payload,
    }


def reflow(version, exact, start, end, chapter=None):
    selector = {"exact": exact, "prefix": "", "suffix": "", "start": start, "end": end}
    if version == 2:
        selector["chapter"] = chapter
    return {
        "mode": "reflow_global",
        "parser_version": "j23-fuzz/1",
        "anchor_version": version,
        "selector": selector,
    }


def epub(version, part, exact, start, end, part_path="OEBPS/ch1.xhtml"):
    location = {
        "mode": "epub_chapter",
        "parser_version": "j23-fuzz/1",
        "anchor_version": version,
        "part_path": part_path,
        "selector": {"exact": exact, "prefix": "", "suffix": "", "start": start, "end": end},
    }
    if version == 2:
        location["part"] = part
    return location


def encode(document):
    return (json.dumps(document, separators=(",", ":")) + "\n").encode()


def wire_seeds():
    progress = envelope(
        "progress", EPUB, "reflow_global", {"book_key": EPUB, "location": reflow(1, "alpha", 0, 5)}
    )
    annotation = envelope(
        "annotation",
        EPUB + ":" + HEX32,
        "reflow_global",
        {
            "book_key": EPUB,
            "annotation_id": HEX32,
            "location": reflow(1, "alpha", 0, 5),
            "text": "note",
        },
    )
    point = envelope(
        "progress", EPUB, "reflow_global", {"book_key": EPUB, "location": reflow(2, "", 0, 0, None)}
    )
    epub_annotation = envelope(
        "annotation",
        EPUB + ":" + HEX32,
        "epub_chapter",
        {
            "book_key": EPUB,
            "annotation_id": HEX32,
            "location": epub(2, 0, "beta", 0, 4),
            "text": "note",
        },
    )
    tag = envelope("tag", HEX32, "none", {"name": "Travel"})
    book = envelope(
        "book",
        PDF,
        "none",
        {
            "format": "pdf",
            "source_sha256": HEX64,
            "source_bytes": 4096,
            "title": "Boundary",
            "author": "Fixture",
            "favorite": False,
        },
    )

    seeds = [
        seed(
            "wire/v1_progress_reflow.json",
            "wire",
            encode(progress),
            "OK",
            fuzz=True,
            decode={
                "entity_kind": "progress",
                "operation": "put",
                "mode": 1,
                "anchor_version": 1,
                "start": 0,
                "end": 5,
                "exact_size": 5,
                "book_key": EPUB,
            },
        ),
        seed(
            "wire/v1_annotation_reflow.json",
            "wire",
            encode(annotation),
            "OK",
            fuzz=True,
            decode={
                "entity_kind": "annotation",
                "mode": 1,
                "anchor_version": 1,
                "exact_size": 5,
                "book_key": EPUB,
                "annotation_id": HEX32,
            },
        ),
        seed(
            "wire/v2_progress_point.json",
            "wire",
            encode(point),
            "OK",
            fuzz=True,
            decode={
                "entity_kind": "progress",
                "mode": 1,
                "anchor_version": 2,
                "start": 0,
                "end": 0,
                "exact_size": 0,
            },
        ),
        seed(
            "wire/v2_epub_annotation.json",
            "wire",
            encode(epub_annotation),
            "OK",
            fuzz=True,
            decode={
                "entity_kind": "annotation",
                "mode": 2,
                "anchor_version": 2,
                "exact_size": 4,
                "part_path": "OEBPS/ch1.xhtml",
                "part": 0,
            },
        ),
        seed("wire/v1_tag.json", "wire", encode(tag), "OK", fuzz=True, decode={"status": 1}),
        seed("wire/v1_book.json", "wire", encode(book), "OK", fuzz=True),
    ]

    unknown = dict(progress)
    unknown["extra"] = 1
    seeds.append(seed("wire/unknown_field.json", "wire", encode(unknown), "FORMAT"))

    duplicate = json.dumps(progress, separators=(",", ":"))
    duplicate = duplicate.replace('"version":1', '"version":1,"version":1', 1)
    seeds.append(seed("wire/duplicate_key.json", "wire", (duplicate + "\n").encode(), "FORMAT"))

    invalid_utf8 = encode(annotation).replace(b'"text":"note"', b'"text":"\xc3("')
    assert b"\xc3(" in invalid_utf8
    seeds.append(seed("wire/invalid_utf8.json", "wire", invalid_utf8, "FORMAT"))

    nul_text = encode(annotation).replace(b'"text":"note"', b'"text":"no\x00te"')
    assert b"no\x00te" in nul_text
    seeds.append(seed("wire/nul_text.json", "wire", nul_text, "FORMAT"))

    unsupported = dict(progress)
    unsupported["version"] = 2
    seeds.append(seed("wire/unsupported_version.json", "wire", encode(unsupported), "FORMAT"))

    limit = b'{"version":1' + b" " * (1048577 - 12)
    assert len(limit) == 1048577
    seeds.append(seed("wire/byte_limit.bin", "wire", limit, "LIMIT"))
    return seeds


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: make_boundary_seeds.py <output-directory>")
    root = Path(sys.argv[1])
    (root / "preferences").mkdir(parents=True, exist_ok=True)
    (root / "wire").mkdir(parents=True, exist_ok=True)

    seeds = preferences_seeds() + wire_seeds()
    manifest = {
        "generated_by": "tests/reader_app_boundary_fuzz/make_boundary_seeds.py",
        "canonical_preferences": CANONICAL_PREFERENCES,
        "seeds": [],
    }
    for item in seeds:
        path = root / item["file"]
        path.write_bytes(item["data"])
        entry = {key: value for key, value in item.items() if key != "data"}
        entry["bytes"] = path.stat().st_size
        manifest["seeds"].append(entry)
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"seeds": len(manifest["seeds"]), "root": str(root)}))


if __name__ == "__main__":
    main()
