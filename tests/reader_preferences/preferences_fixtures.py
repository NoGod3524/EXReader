# SPDX-License-Identifier: MIT
"""Canonical preference documents and refusal fixtures for the F3 package."""
import json
from pathlib import Path

DEFAULTS = {
    "format": "exreader-preferences",
    "format_version": 1,
    "font_size": 24,
    "line_spacing": 1.6,
    "paragraph_spacing": 12,
    "margin": 48,
    "theme": "light",
    "page_turn_direction": "ltr",
    "page_turn_input": "tap",
    "fixed_page_zoom": 100,
    "light_foreground": "#1A1A1AFF",
    "light_background": "#FFFFFFFF",
    "dark_foreground": "#E6E6E6FF",
    "dark_background": "#101010FF",
}

ORDER = list(DEFAULTS)


def render(values, raw=None, indent="  "):
    raw = raw or {}
    lines = []
    for key in ORDER:
        if key not in values:
            continue
        if key in raw:
            encoded = raw[key]
        else:
            encoded = json.dumps(values[key])
        lines.append(f'{indent}"{key}": {encoded}')
    return "{\n" + ",\n".join(lines) + "\n}\n"


def document(**overrides):
    values = dict(DEFAULTS)
    values.update(overrides)
    return render(values)


def write_fixtures(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    fixtures = {
        "valid.json": document(),
        "unknown-version.json": document(format_version=2),
        "nan.json": render(DEFAULTS, {"font_size": "NaN"}),
        "infinity.json": render(DEFAULTS, {"line_spacing": "Infinity"}),
        "huge-exponent.json": render(DEFAULTS, {"margin": "1e9999"}),
        "bad-enum.json": document(theme="sepia"),
        "bad-direction.json": document(page_turn_direction="diagonal"),
        "bad-input.json": document(page_turn_input="mouse"),
        "bad-color.json": document(light_foreground="#12345"),
        "bad-format.json": document(format="other-reader"),
        "zoom-fraction.json": document(fixed_page_zoom=100.5),
        "wrong-type.json": document(font_size="24"),
        "missing.json": render({k: v for k, v in DEFAULTS.items() if k != "margin"}),
        "trailing.json": document() + "x\n",
        "empty.json": "",
        "format_only.json": "[]\n",
    }
    for name, text in fixtures.items():
        (directory / name).write_text(text, encoding="utf-8")

    valid = document()
    (directory / "truncated.json").write_text(valid[: len(valid) // 2], encoding="utf-8")
    (directory / "duplicate.json").write_text(
        valid.replace('"margin": 48,', '"margin": 48,\n  "margin": 48,'), encoding="utf-8"
    )
    (directory / "unknown-key.json").write_text(
        valid.replace('"margin": 48,', '"margin": 48,\n  "unknown_setting": 1,'), encoding="utf-8"
    )
    (directory / "nul.json").write_bytes(valid.encode("utf-8").replace(b"\"light\"", b"\"li\x00ght\""))
    (directory / "bad-utf8.bin").write_bytes(valid.encode("utf-8").replace(b"\"light\"", b"\"li\xffght\""))
    (directory / "oversize.json").write_text(valid + " " * (70000 - len(valid)), encoding="utf-8")
    return directory
