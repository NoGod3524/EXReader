# M-E2a 表格 UI 交付

基于 `210022e3`，实现位于当前 `codex/word-editor-tables-20261112` 分支。实际 Windows 宿主已构建为 `build/tables-host/EXReader.exe`。

UI 按文档顺序寻址单元格段落，使用同一模型的稳定 ID 修改内容。新增实验 API `exr_edit_insert_run`，空段落的首个 run 与输入共用一个事务；同格段落插入、删除、属性修改也保留其他段落。跨单元格删除整体回滚。合并、底纹、嵌套及 opaque 内容沿用引擎保护。

## ①—⑧：真实宿主 headless 驱动

命令：`ctest --test-dir build/tables-host -R windows-table-ui -V`，exit 0。完整原始输出见 [ui.txt](ui.txt)。不创建 HWND，不使用 SendInput。

```text
1: 1 PASS open fixture -> Tab cell=(0,0); border_pixels=58 caret_pixels=22 caret=(30.0,144.4) inside cell; hit-test PASS
1: 1 extra PASS Tab row wrap / Shift+Tab / Right enters cell
1: 2 PASS typed AB -> Ctrl+S -> reopened cell(0,0)=AB
1: 3 PASS Enter paragraphs=1->2 zero-run=0; typed X -> [AB|X]; sibling cell=keep
1: 4 PASS one Ctrl+Z -> [AB|empty], Enter retained, inserted run removed
1: 5 PASS toolbar +row 2->3; -row 3->2; each undo/redo is one transaction; text retained
1: 6 PASS toolbar column +5%/-5% twips=2400->2520->2400 pixels=160.0->168.0->160.0
1: 7 PASS toolbar delete table -> table block absent; border layouts=0; toolbar hidden
1: 8 PASS Ctrl+S -> reopen: rows=2 columns=2 widths=[2520,2400] all cell paragraphs/text equal [AB|X], keep
1: extra PASS Delete/Backspace join within cell + undo; cross-cell deletion rolls back without text loss
1: M-E2a table UI headless acceptance PASS (no HWND / no SendInput)
1/1 Test #1: windows-table-ui .................   Passed    0.68 sec
100% tests passed out of 1
Total Test time (real) =   0.69 sec
```

驱动先写出并打开表格夹具，经过保存后再次真正打开 DOCX；工具条操作通过实际按钮坐标命中。往返比较包含全部行、列、格、段落、文本和列宽。[最终截图](table-edited.png) 来自 Direct2D 内存 DC；[保存的 DOCX](table-edited.docx) 可直接打开。

## ⑨：现有 ctest

命令：`ctest --test-dir build/tables -E '^(sdk-release|sdk-doc-coverage)$' --output-on-failure -j 6`，exit 0。完整原始输出见 [ctest.txt](ctest.txt)。

```text
420/420 Test #420: sdk-doc-dictionary .................................   Passed    0.73 sec
100% tests passed out of 420
Total Test time (real) = 158.68 sec
```

新增 `native-docx-edit-insert-run` 已登记到 CTest，并加入 `tests/fixtures/docx-real/codex/register.cmake` 的 ASan 预载正则。额外的公开 ABI 回归真实输出见 [insert-run.txt](insert-run.txt)：覆盖零 run、同格前后段落、ID、pStyle、输入别名、失败事务、非法 UTF-8、受保护单元格及保存往返。

原有真实宿主驱动 `check_shell_docedit.exe tests/fixtures/rich.docx <输出目录>` 也 exit 0，M-E1 与 M-E2c 全部通过，原始输出见 [baseline-ui.txt](baseline-ui.txt)。

## ⑩：SDK 文档

`python -X utf8 tools/check_sdk_docs.py`：exit 0；486/486，100%，`errors: []`，`passed: true`。完整 JSON 见 [sdk-docs.json](sdk-docs.json)。新增 API 六标签齐全，ABI=实验；未新增头文件，现有 edit.h 已在 layers.json 登记。

`python -X utf8 tools/check_sdk_docs.py --binary build/tables/libexreader.dll`：exit 0，486 exports，`passed: true`。完整 JSON 见 [sdk-docs-binary.json](sdk-docs-binary.json)。

`python -X utf8 tools/check_layers.py build/tables`：exit 0，128 objects / 1507 symbol references，0 new inverse references、0 inverse includes，见 [layers.txt](layers.txt)。`git diff --check` 通过。

## 构建与推送状态

已执行 `cmake --build build/tables -j 6`、`cmake --install build/tables`，再以该 SDK 配置 Windows consumer，构建 `check_shell_table`、`check_shell_docedit` 和 `EXReader`，均 exit 0。第三方依赖复用本机已有的固定版本源码目录；编辑引擎来自当前工作树的 `src/docx_edit.c`。

未改 `tests/check_reading_release.py`，未改或重排 `tools/version_literal_exceptions.json`，未放宽既有断言，未使用 GUI 自动化。

未推送。实际执行 `pwsh -NoProfile -File ops/prepush-check.ps1` 返回 exit 64，因当前仓库没有该脚本；原始输出见 [prepush.txt](prepush.txt)。没有绕过这个推送门禁。
