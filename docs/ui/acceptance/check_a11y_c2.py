#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""C2 headless acceptance: inspect source and inventory existing evidence only.

Usage: python check_a11y_c2.py [--out DIR] [--self-test]
No application, UI Automation client, input injection, or system setting access.
Runtime UIA and visual/focus acceptance stay pending in C2-MANUAL-CHECK.md.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MANUAL = ROOT / "docs/a11y/C2-MANUAL-CHECK.md"
SOURCES = [
    "examples/reader.c", "apps/reader/desktop/windows_accessibility.inc",
    "examples/windows/shell_screen.inc", "examples/windows/shell_settings.inc",
    "examples/windows/shell_toc.inc", "examples/windows/shell_tokens.h",
    "examples/windows/shell_d2d.cpp",
]
EXPECTED = {
    "shell_back": "返回书架", "shell_search_button": "全文搜索",
    "shell_toc": "目录", "shell_settings": "设置", "shell_toc_panel": "目录面板",
    "shell_toc_list": "目录列表", "shell_panel": "阅读设置",
    "shell_search_bar": "全文搜索栏", "shell_search_edit": "搜索关键词",
    "shell_search_prev": "上一处", "shell_search_next": "下一处",
    "shell_search_case": "区分大小写", "shell_search_word": "全词匹配",
    "shell_search_close": "关闭搜索",
    "shell_segments[0]": "浅色主题", "shell_segments[1]": "深色主题",
    "shell_segments[2]": "跟随系统主题", "style_preset": "排版预设",
    "shell_tap_buttons[0]": "点击分区 20 / 60 / 20",
    "shell_tap_buttons[1]": "点击分区 25 / 50 / 25",
}


def code_only(source):
    # Preserve strings; discard comments so a commented-out registration fails.
    return re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"',
                  lambda m: m[0] if m[0].startswith('"') else ' ', source, flags=re.S)


def function(source, name):
    match = re.search(r'\b' + re.escape(name) + r'\([^;{}]*\)\s*{', source)
    if not match:
        return ""
    start, depth = match.end(), 1
    tokens = re.finditer(r'"(?:\\.|[^"\\])*"|[{}]', source[start:])
    for token in tokens:
        if token[0] == '{':
            depth += 1
        elif token[0] == '}':
            depth -= 1
            if not depth:
                return source[start:start + token.start()]
    return ""


def validate(sources):
    rows = []

    def check(name, ok):
        rows.append({"check": name, "pass": bool(ok), "kind": "static"})

    reader, provider, screen, settings, toc, tokens, d2d = (
        code_only(sources[name]) for name in SOURCES)
    names = function(screen, "shell_a11y_names")
    for control, name in EXPECTED.items():
        pattern = (r'host_a11y_describe\(\s*' + re.escape(control) +
                   r'\s*,\s*L"' + re.escape(name) + r'"\s*,\s*L"[^"\n]+"\s*\)')
        check("Name+HelpText:" + control, re.search(pattern, names))
    check("dynamic_style_fields", all('L"' + field + '"' in names
          for field in ("字号", "行距", "段距", "上边距", "右边距", "下边距", "左边距", "字距"))
          and 'i < 8' in names and 'host_a11y_describe(style_edits[i], field[i],' in names
          and 'host_a11y_describe(style_buttons[2*i], name,' in names
          and 'host_a11y_describe(style_buttons[2*i+1], name,' in names)
    check("registration_called_during_shell_create",
          "shell_a11y_names();" in function(screen, "shell_create") and 'shell_create(parent);' in reader)
    describe = function(provider, "host_a11y_describe")
    check("IAccPropServices_Name_HelpText", all(token in describe for token in (
        'CoCreateInstance', 'SetHwndPropStr', 'host_a11y_prop_name, name', 'host_a11y_prop_help, help'))
        and '0x608d3df8' in provider and '0xc831e11f' in provider)
    check("page_name_and_provider_dispatch", 'L"EXReaderPage", L"阅读区域"' in reader
          and 'return host_a11y_page_object(window, wparam, lparam);' in reader)
    check("text_provider_interfaces", all(token in provider for token in (
        'ITextProvider', 'ITextRangeProvider', 'IValueProvider', 'UIA_Text_TextChangedEventId',
        'UIA_Text_TextSelectionChangedEventId', 'UiaRaiseStructureChangedEvent')))
    check("panel_structure_event_calls", 'host_a11y_panel_toggled(shell_panel,shell_panel_open)' in settings
          and 'host_a11y_panel_toggled(shell_toc_panel,open)' in toc)
    tab = function(screen, 'shell_tab_stops')
    stops = re.findall(r'stops\[count\+\+\] = (shell_back|shell_search_button|g\.page|shell_toc|shell_settings);', tab)
    check("closed_tab_order", stops == ['shell_back', 'shell_search_button', 'g.page', 'shell_toc', 'shell_settings'])
    check("tab_skips_hidden_disabled", '!IsWindowVisible(window)' in tab and '!IsWindowEnabled(window)' in tab)
    check("reverse_tab_wrap", '(shift ? count - 1 : 1)) % count' in function(screen, 'shell_tab_next'))
    check("focus_stroke_2px_scaled", 'SHELL_FOCUS_STROKE=2' in tokens and
          '(float)SHELL_FOCUS_STROKE*k' in d2d and 's->dpi/96.f' in d2d)
    check("contrast_system_palette", all(token in reader for token in (
        'SPI_GETHIGHCONTRAST', 'HCF_HIGHCONTRASTON', 'COLOR_WINDOW', 'COLOR_WINDOWTEXT', 'COLOR_HIGHLIGHT')))
    check("contrast_theme_d2d_path", 'dark == 2 ? shell_theme_contrast' in d2d
          and 'WM_SYSCOLORCHANGE' in reader)
    return rows


def self_test(sources):
    baseline = validate(sources)
    assert all(row['pass'] for row in baseline), [r for r in baseline if not r['pass']]
    for old, new in [('L"返回书架"', 'L""'), ('L"回到书架，快捷键 Ctrl+W"', 'NULL'),
                     ('shell_a11y_names();', '/* shell_a11y_names(); */')]:
        broken = dict(sources)
        broken[SOURCES[2]] = sources[SOURCES[2]].replace(old, new)
        assert any(not row['pass'] for row in validate(broken)), old
    print('PASS static negative controls: missing Name, HelpText, registration call')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'build/a11y-c2-static')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    sources = {name: (ROOT / name).read_text(encoding='utf-8') for name in SOURCES}
    checks = validate(sources)
    # Historical evidence is inventoried, never promoted to a current runtime pass.
    evidence = ROOT / 'docs/ui/evidence/a11y-uia-20261110'
    shots = [{"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size,
              "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "kind": "historical"}
             for path in sorted(evidence.rglob('*.png'))]
    checks.append({"check": "existing_screenshots_available", "pass": bool(shots), "kind": "evidence_inventory"})
    checks.append({"check": "manual_checklist_available", "pass": MANUAL.is_file(), "kind": "static"})
    args.out.mkdir(parents=True, exist_ok=True)
    result = {"mode": "headless-static", "runtime_uia": "pending_external_manual",
              "checks": checks, "historical_screenshots": shots,
              "sources": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES},
              "manual_checklist": MANUAL.relative_to(ROOT).as_posix()}
    (args.out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (args.out / 'C2-MANUAL-CHECK.md').write_bytes(MANUAL.read_bytes())
    for row in checks:
        print(('PASS' if row['pass'] else 'FAIL') + ' ' + row['check'])
    print(f"Historical screenshots: {len(shots)}; runtime UIA: pending_external_manual")
    if args.self_test:
        self_test(sources)
    return int(any(not row['pass'] for row in checks))


if __name__ == '__main__':
    raise SystemExit(main())
