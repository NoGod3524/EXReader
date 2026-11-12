#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate C2 manual checklist and check static registration; never starts an app."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[3]
MANUAL = """# C2 人工验收清单

本文件由 `python docs/ui/acceptance/check_a11y_c2.py --output evidence/headless-20261110/c2.json` 生成。
静态配置与历史截图校验不能证明当前进程的 UIA 属性、事件或视觉表现通过。
以下项目均待主控安排，在用户在场且明确授权的独立验收环境完成；本轮不启动窗口、不模拟输入、不修改系统设置。

| 待确认项 | 为什么需要真实窗口 | 用户在场时的步骤与通过条件 |
| --- | --- | --- |
| 外部 UIA 名称与 HelpText | 必须读取运行中应用的 HWND 和 Windows 代理实际暴露的属性 | 主控安排启动应用并用独立 UIA 检查器读取正文、顶栏、搜索、目录、设置及云同步控件；逐项比对名称、HelpText、角色、启用状态 |
| TextPattern 与事件 | 静态代码不能证明跨进程 COM、TextChanged、SelectionChanged、StructureChanged 实际送达 | 人工翻页、选文、切章和开关面板；外部观察正文及选区与屏幕一致，事件送达 |
| Tab / Shift+Tab 顺序 | 取决于可见、启用的真实控件及焦点状态 | 人工依次测试关闭面板、搜索展开、目录展开、设置展开；正反向循环，无隐藏或禁用控件进入，无焦点陷阱 |
| 焦点环 | 栅格化、DPI 与真实焦点只能在窗口中确认 | 人工 Tab 到目录与设置，检查 2 × DPI/96 像素焦点环清楚、未截断；正文获焦不出现整页边框 |
| 快捷键与焦点返回 | 需要真实键盘消息与活动窗口 | 人工测试 Ctrl+F、Esc、PageUp/PageDown、Home/End、目录回车跳转；内容变化，关闭面板后焦点可继续阅读 |
| 对比度观感 | 实际系统配色、显示器和用户感知不能由静态配置推出 | 在预先配置的独立对比度测试环境查看正文、选择文字、目录、设置、搜索、禁用控件和焦点环；文字可读且选区可辨认；本脚本不切换任何系统设置 |
| OPDS 宿主交互 | 控制台网络/解析成功不能证明窗口布局、进度条和取消按钮的表现 | 主控另行安排目录导航、搜索、下载进度与取消、导入后打开的人工验收 |
| WebDAV 宿主状态 | 同步引擎成功不能证明设置页的状态文案与焦点 | 主控另行检查保存凭据、立即同步、失败提示、离线草稿数量和重连显示 |

已有 /ui 截图来源、提交与 SHA256 见 [C2-EVIDENCE.json](C2-EVIDENCE.json)。仅复用历史截图，不重拍，不把它们计为本轮运行时通过。
"""


def body(source, name):
    match = re.search(r'\b' + re.escape(name) + r'\s*\([^;{}]*\)\s*\{', source)
    if not match:
        raise ValueError(f'missing function definition: {name}')
    start = match.end() - 1
    level = 0
    # Skip strings/comments when counting C braces.
    tokens = re.finditer(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|\x27(?:\\.|[^\x27\\])*\x27|[{}]', source[start:])
    for token in tokens:
        if token.group() == '{':
            level += 1
        elif token.group() == '}':
            level -= 1
            if not level:
                return re.sub(r'//[^\n]*|/\*[\s\S]*?\*/', '', source[start:start + token.end()])
    raise ValueError(f'unclosed function: {name}')


def inspect(root):
    checks = []
    sources = {}

    def read(path):
        value = (root / path).read_text(encoding='utf-8')
        sources[path] = hashlib.sha256((root / path).read_bytes()).hexdigest()
        return value

    def check(name, ok, detail):
        checks.append(dict(check=name, passed=bool(ok), detail=detail))
        print(f'{"PASS" if ok else "FAIL"} {name}: {detail}')

    reader = read('examples/reader.c')
    screen = read('examples/windows/shell_screen.inc')
    provider = read('apps/reader/desktop/windows_accessibility.inc')
    names = body(screen, 'shell_a11y_names')
    creation = body(screen, 'shell_create')
    check('registration_reachable', '#include "../apps/reader/desktop/windows_accessibility.inc"' in reader and
          'shell_create(parent);' in body(reader, 'create_controls') and
          'shell_a11y_names();' in creation and creation.index('shell_a11y_names();') > creation.index('shell_search_create(parent);'),
          'create_controls -> shell_create -> shell_a11y_names after panel creation')
    expected = {
        'shell_back': '返回书架', 'shell_search_button': '全文搜索', 'shell_toc': '目录',
        'shell_settings': '设置', 'shell_toc_panel': '目录面板', 'shell_toc_list': '目录列表',
        'shell_panel': '阅读设置', 'shell_search_bar': '全文搜索栏', 'shell_search_edit': '搜索关键词',
        'shell_search_prev': '上一处', 'shell_search_next': '下一处', 'shell_search_case': '区分大小写',
        'shell_search_word': '全词匹配', 'shell_search_close': '关闭搜索',
        'shell_segments[0]': '浅色主题', 'shell_segments[1]': '深色主题', 'shell_segments[2]': '跟随系统主题',
        'style_preset': '排版预设', 'shell_tap_buttons[0]': '点击分区 20 / 60 / 20',
        'shell_tap_buttons[1]': '点击分区 25 / 50 / 25',
    }
    for control, name in expected.items():
        check('name_help_' + control, bool(re.search(r'host_a11y_describe\(\s*' + re.escape(control) +
              r'\s*,\s*L"' + re.escape(name) + r'"\s*,\s*L"[^"\n]+"\s*\)', names)), name)
    check('style_fields', 'for (int i = 0; i < 8; i++)' in names and
          all(f'L"{s}"' in names for s in ('字号','行距','段距','上边距','右边距','下边距','左边距','字距')) and
          all(s in names for s in ('host_a11y_describe(style_buttons[2*i], name, L"',
                                    'host_a11y_describe(style_buttons[2*i+1], name, L"',
                                    'host_a11y_describe(style_edits[i], field[i], L"')),
          '8 fields, increment/decrement names and help')
    for control in ('style_save', 'style_reset', 'GetDlgItem(shell_panel, IDC_SHELL_DICTIONARY)', 'GetDlgItem(shell_panel, IDC_SHELL_SYNC)'):
        check('native_help_' + control, bool(re.search(r'host_a11y_describe\(' + re.escape(control) +
              r', NULL, L"[^"\n]+"\)', names)), 'native caption retained, explicit help registered')
    describe = body(provider, 'host_a11y_describe')
    check('native_property_registration', all(s in describe for s in ('CoCreateInstance(', 'SetHwndPropStr(',
          'host_a11y_prop_name, name', 'host_a11y_prop_help, help')), 'IAccPropServices name/help path present')
    check('page_name_help', bool(re.search(r'if \(id == UIA_NamePropertyId\) return host_a11y_bstr\(out, L"[^"\n]+"\)', provider)) and
          bool(re.search(r'if \(id == UIA_HelpTextPropertyId\) return host_a11y_bstr\(out, L"[^"\n]+"\)', provider)),
          'page provider returns nonempty Name and HelpText')
    for event in ('UIA_Text_TextChangedEventId', 'UIA_Text_TextSelectionChangedEventId', 'UiaRaiseStructureChangedEvent'):
        check(event, event in provider, 'static provider event path; runtime delivery pending')
    tokens = read('examples/windows/shell_tokens.h')
    d2d = read('examples/windows/shell_d2d.cpp')
    settings = read('examples/windows/shell_settings.inc')
    check('focus_stroke', bool(re.search(r'SHELL_FOCUS_STROKE\s*=\s*2\b', tokens)) and
          'SHELL_FOCUS_STROKE*k' in body(d2d, 'shell_d2d_control'), '2px token used by draw path')
    contrast = body(reader, 'shell_contrast_refresh')
    check('contrast_palette', all(s in contrast for s in ('SPI_GETHIGHCONTRAST','COLOR_WINDOWTEXT','COLOR_HIGHLIGHT','COLOR_HIGHLIGHTTEXT')) and
          'shell_contrast_refresh();' in body(settings,'shell_apply_theme'), 'read system palette and apply it')
    check('contrast_read_only', 'SPI_SETHIGHCONTRAST' not in reader and 'SPI_SETHIGHCONTRAST' not in settings,
          'host does not set high contrast')
    check('tab_configuration', all(s in body(screen,'shell_tab_stops') for s in ('shell_back','shell_search_button','g.page','shell_toc','shell_settings','IsWindowVisible','IsWindowEnabled')),
          'declared order and visible/enabled filtering; actual focus pending')
    evidence = json.loads(read('docs/a11y/C2-EVIDENCE.json'))
    for item in evidence['screenshots']:
        data = (root / item['path']).read_bytes()
        valid = data[:8] == b'\x89PNG\r\n\x1a\n' and len(data) >= 24
        width, height = struct.unpack('>II', data[16:24]) if valid else (0, 0)
        check('historical_' + Path(item['path']).name, valid and width > 0 and height > 0 and
              hashlib.sha256(data).hexdigest() == item['sha256'], f'existing screenshot {width}x{height}, SHA256 checked')
    return dict(mode='headless-static-only', checks=checks, source_sha256=sources,
                runtime_uia='pending manual check', screenshot_source_commit=evidence['source_commit'],
                passed=all(c['passed'] for c in checks))


def self_test():
    import contextlib
    import io
    import shutil
    import tempfile
    manifest = json.loads((ROOT / 'docs/a11y/C2-EVIDENCE.json').read_text(encoding='utf-8'))
    paths = ['examples/reader.c', 'examples/windows/shell_screen.inc',
             'apps/reader/desktop/windows_accessibility.inc', 'examples/windows/shell_tokens.h',
             'examples/windows/shell_d2d.cpp', 'examples/windows/shell_settings.inc',
             'docs/a11y/C2-EVIDENCE.json'] + [v['path'] for v in manifest['screenshots']]
    with tempfile.TemporaryDirectory(prefix='exreader-c2-static-') as folder:
        root = Path(folder)
        for name in paths:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        mutations = [
            ('examples/windows/shell_screen.inc', 'L"返回书架"', 'L""', 'name_help_shell_back'),
            ('examples/windows/shell_screen.inc', 'shell_a11y_names();', '/* registration removed */', 'registration_reachable'),
            ('apps/reader/desktop/windows_accessibility.inc', 'host_a11y_prop_help, help', 'host_a11y_prop_name, help', 'native_property_registration'),
        ]
        for name, before, after, expected in mutations:
            target = root / name
            original = target.read_text(encoding='utf-8')
            assert before in original
            target.write_text(original.replace(before, after), encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                result = inspect(root)
            assert not result['passed'] and any(c['check'] == expected and not c['passed'] for c in result['checks'])
            target.write_text(original, encoding='utf-8')
            print('PASS negative control: ' + expected)
        target = root / manifest['screenshots'][0]['path']
        target.write_bytes(target.read_bytes() + b'tampered')
        with contextlib.redirect_stdout(io.StringIO()):
            result = inspect(root)
        assert not result['passed']
        print('PASS negative control: historical screenshot tampering')
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--source-root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/c2-static.json')
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = inspect(args.source_root.resolve())
    # The checklist is part of the delivery, generated deterministically from this script.
    (ROOT / 'docs/a11y/C2-MANUAL-CHECK.md').write_text(MANUAL, encoding='utf-8')
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f"{sum(c['passed'] for c in result['checks'])}/{len(result['checks'])} static/evidence checks passed; runtime UIA pending")
    return int(not result['passed'])


if __name__ == '__main__':
    raise SystemExit(main())
