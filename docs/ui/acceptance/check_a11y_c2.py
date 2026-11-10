#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""C2 headless acceptance: source assertions, historical PNG hashes, manual list.

Usage: python -X utf8 docs/ui/acceptance/check_a11y_c2.py [--self-test]
Uses only Python file operations. Does not launch or attach to an application.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
SOURCES = {
    'reader': 'examples/reader.c',
    'screen': 'examples/windows/shell_screen.inc',
    'uia': 'apps/reader/desktop/windows_accessibility.inc',
    'search': 'examples/windows/shell_search.inc',
    'toc': 'examples/windows/shell_toc.inc',
    'settings': 'examples/windows/shell_settings.inc',
    'tokens': 'examples/windows/shell_tokens.h',
    'draw': 'examples/windows/shell_d2d.cpp',
}
NAMES = {
    'shell_back': '返回书架', 'shell_search_button': '全文搜索',
    'shell_toc': '目录', 'shell_settings': '设置',
    'shell_toc_panel': '目录面板', 'shell_toc_list': '目录列表',
    'shell_panel': '阅读设置', 'shell_search_bar': '全文搜索栏',
    'shell_search_edit': '搜索关键词', 'shell_search_prev': '上一处',
    'shell_search_next': '下一处', 'shell_search_case': '区分大小写',
    'shell_search_word': '全词匹配', 'shell_search_close': '关闭搜索',
}
MANUAL = [
    ('外部 UIA', '需要真实窗口，因为 UIA 必须读取运行中的控件树与 provider。用户在场时手动打开应用和有文字的书页，从独立 UIA 客户端检查 Name、HelpText、角色、可用状态、TextPattern/DocumentRange、ValuePattern、选择范围；翻页、选择、翻章和开关面板时核对 TextChanged、TextSelectionChanged、StructureChanged。封面无文本须单独记录。'),
    ('Tab 与焦点恢复', '需要真实窗口，因为实际焦点受可见性、启用状态和消息循环影响。人工按 Tab/Shift+Tab 检查 返回书架→全文搜索→正文→目录→设置 循环；分别打开搜索、目录、设置检查子控件顺序，Esc 关闭后焦点回到正文，禁用控件不能困住焦点。'),
    ('焦点环', '需要真实窗口，因为静态 token 不能证明实际绘制、裁切与缩放。人工检查目录、设置、搜索和各设置按钮的焦点环，在用户当前 DPI 下应清晰完整；正文聚焦时无额外页面边框。'),
    ('对比度观感', '需要真实窗口，因为截图和颜色配置不能证明用户屏幕上的可读性。先在当前主题检查文字、选区、焦点环、禁用控件和面板；高对比度仅由用户本人决定是否切换并操作，检查完成由用户恢复。自动验收不得切换主题、高对比度、DPI 或输入法。'),
    ('同步宿主呈现', '需要真实窗口，因为控制台只能证明同步数据和状态码。人工检查设置→云同步入口、错误和离线队列的文字、后台完成后的状态刷新及保存后密码框清空。'),
    ('OPDS 宿主呈现', '需要真实窗口，因为控制台不能验证面板交互和进度呈现。人工检查书源入口、搜索/翻页/返回、下载进度与取消、下载后导入并打开、超时错误显示。'),
]


def static_checks(source):
    # Ignore comments so dead descriptions cannot satisfy registrations.
    s = {k: re.sub(r'"(?:\\.|[^"\\])*"|/\*.*?\*/|//[^\n]*',
                   lambda m: '' if m[0].startswith(('/',)) else m[0], v, flags=re.S)
         for k, v in source.items()}
    result = {}
    for control, name in NAMES.items():
        pattern = rf'host_a11y_describe\({control},\s*L"{name}",\s*L"[^"]+"\);'
        result['Name/HelpText:' + control] = bool(re.search(pattern, s['screen']))
    result['Name/HelpText:style-fields'] = all(x in s['screen'] for x in (
        'host_a11y_describe(style_buttons[2*i], name, L"按一步减小这一项")',
        'host_a11y_describe(style_buttons[2*i+1], name, L"按一步增大这一项")',
        'host_a11y_describe(style_edits[i], field[i], L"直接输入数值，离开输入框后生效")'))
    result['registration:backend'] = all(x in s['uia'] for x in (
        'CoCreateInstance(&host_a11y_clsid_props',
        'SetHwndPropStr(host_a11y_props, window, OBJID_CLIENT, CHILDID_SELF, host_a11y_prop_name, name)',
        'SetHwndPropStr(host_a11y_props, window, OBJID_CLIENT, CHILDID_SELF, host_a11y_prop_help, help)'))
    create = re.search(r'static void shell_create\(HWND parent\)\s*\{(.*?)\n\}', s['screen'], re.S)
    result['registration:after-controls-created'] = bool(create and re.search(
        r'shell_create_panel\(parent\);\s*shell_toc_create\(parent\);\s*shell_search_create\(parent\);\s*shell_a11y_names\(\);', create[1]))
    result['registration:reader-include'] = '#include "../apps/reader/desktop/windows_accessibility.inc"' in s['reader']
    result['events:structure'] = all(('host_a11y_panel_toggled(' in s[key]) for key in ('toc', 'settings')) and 'UiaRaiseStructureChangedEvent(' in s['uia'] and 'host_a11y_structure_changed();' in s['uia']
    result['events:text-and-selection'] = all(x in s['uia'] for x in ('UIA_Text_TextChangedEventId', 'UIA_Text_TextSelectionChangedEventId'))
    result['keyboard:tab-handler'] = 'shell_tab_next(focus,shift)' in s['toc'] and 'next = stops[(at + (shift ? count - 1 : 1)) % count]' in s['screen']
    stops = re.search(r'static int shell_tab_stops\([^)]*\)\s*\{(.*?)int panel_start', s['screen'], re.S)
    order = re.findall(r'stops\[count\+\+\] = (\w+(?:\.\w+)?);', stops[1]) if stops else []
    expected = ['shell_back', 'shell_search_button', 'g.page', 'shell_toc', 'shell_settings']
    result['keyboard:base-order'] = [x for x in order if x in expected] == expected
    result['focus-ring:token'] = bool(re.search(r'SHELL_FOCUS_STROKE\s*=\s*2\b', s['tokens'])) and 'SHELL_FOCUS_STROKE' in s['draw']
    result['contrast:configuration'] = 'shell_theme_contrast' in s['settings'] and 'HCF_HIGHCONTRASTON' in s['reader'] and 'case WM_SYSCOLORCHANGE:' in s['reader']
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    source = {k: (ROOT / path).read_text(encoding='utf-8') for k, path in SOURCES.items()}
    checks = static_checks(source)
    if args.self_test:
        broken = dict(source, screen=source['screen'].replace('L"返回书架", L"回到书架，快捷键 Ctrl+W"', 'L"返回书架", NULL'))
        assert not static_checks(broken)['Name/HelpText:shell_back']
        broken = dict(source, screen=source['screen'].replace('shell_a11y_names();', ''))
        assert not static_checks(broken)['registration:after-controls-created']
        print('PASS negative checks: missing HelpText and missing registration caller rejected')
    evidence = ROOT / 'docs/ui/evidence/a11y-uia-20261110/reused'
    manifest = json.loads((evidence / 'manifest.json').read_text(encoding='utf-8'))
    images = manifest['images']
    checks['historical-screenshots'] = len(images) == 9 and manifest['historical_only'] and all(
        (evidence / row['path']).read_bytes().startswith(b'\x89PNG\r\n\x1a\n') and
        hashlib.sha256((evidence / row['path']).read_bytes()).hexdigest() == row['sha256'] for row in images)
    manual = ROOT / 'docs/a11y/C2-MANUAL-CHECK.md'
    manual.parent.mkdir(parents=True, exist_ok=True)
    lines = ['# C2 人工验收交接', '',
             '本轮仅编译、控制台测试和静态校验。下列项目全部待主控安排用户在场后确认，不能记为已通过。', '',
             '自动脚本不启动应用、不附着 UIA、不模拟输入、不更改系统设置。', '']
    for title, detail in MANUAL:
        lines.extend([f'- [ ] **{title}**：{detail}', ''])
    lines.extend(['## 复用的旧截图', '',
                  f'来源提交 `{manifest["origin_commit"]}`，目录 `{manifest["origin_directory"]}`。仅作为历史证据，不代表当前构建已完成人工验收。', ''])
    for row in images:
        lines.append(f'- [{row["path"]}](../ui/evidence/a11y-uia-20261110/reused/{row["path"]}) · SHA-256 `{row["sha256"]}`')
    manual.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    report = dict(mode='headless-static', checks=checks, accepted=all(checks.values()),
                  runtime_uia='pending-user-present-manual-check',
                  sources={path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in SOURCES.values()},
                  manual_checklist='docs/a11y/C2-MANUAL-CHECK.md')
    out = ROOT / 'docs/ui/evidence/headless-20261110'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'a11y-static.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for name, passed in checks.items():
        print(('PASS ' if passed else 'FAIL ') + name)
    print(f'{sum(checks.values())}/{len(checks)} static checks; 9 historical PNGs; manual checklist generated')
    return int(not report['accepted'])


if __name__ == '__main__':
    raise SystemExit(main())
