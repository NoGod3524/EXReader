# 无窗口验收报告

分支：`codex/webdav-sync-20261110`。引擎与宿主验收提交：`8c08679f35de45108c91ae7d1096b57d456eeb26`。Draft PR：[#131](https://github.com/NoGod3524/EXReader/pull/131)。

① 续跑起点（原进度文件最后一行）

> Step 3: ctest-group 'sync' (windows-selection-sync) PASS on first run - merge/first-upload/incremental/conflict/tombstone/LWW/401/404/timeout/403/retry/corrupt-remote/offline-queue/reconnect/credentials. Added shell_sync_drive.inc + mock_webdav_main.c for real-exe acceptance; baseline HEAD engine DLL building in ../EXReader-b1-baseline-20261110 for the 19-book regression.

② GUI 验收替换

| 原验收 | 本轮替代 |
|---|---|
| WebDAV 宿主窗口、编辑框和按钮驱动 | `check_sync.c` 直接调用生产 `sy_sync_now`，复用 `check_shell_sync.inc` 的 15 场景和真实 TCP mock；不创建 HWND。`windows-selection-sync` 现指向该控制台。 |
| `check_shell_sync.py` 启动宿主 | 改为只接受 `check_sync.exe` 且检查 PE Console subsystem=3，通过 `CREATE_NO_WINDOW` 执行并逐场景生成 JSON。 |
| OPDS 本地慢服务依赖 UI/Python GUI harness | `check_shell_opds.c` 内置 socket 服务，只 accept、不响应；`--timeout-only` 可离线独立运行，注册为 `windows-opds-timeout`。 |
| C2 外部 UIA、模拟按键、切换高对比度、重拍截图 | `check_a11y_c2.py` 只读源文件和旧 PNG：25 项静态检查、两项拒绝样例、9 张旧图哈希核验、生成待办清单。注册 `windows-a11y-static`。 |
| 宿主 UI 实际交互验收 | 宿主 `-O2 -Wall -Wextra -Werror` 编译 + 控制台等价业务路径；实际呈现交主控安排人工验收。 |

b1 原分支缺少 b2/C2 文件，因此把已提交的 b2 实现（`83a554ae`）和 C2 实现（`5cdc779c`）及构建/导出依赖纳入本分支，以便在同一工作树完成编译与验收。

编译中修复两处问题：OPDS URL 升级遇到容量不足时返回空地址供现有错误路径拒绝，避免截断 URL；同步控制台入口声明为 `static inline`，解决 GUI 宿主中的未使用函数警告。原宿主编译失败日志保留为 `build-host-failed.txt`。

已合并 `main` 的 `fe3d46e1`，唯一冲突 `OUT.txt` 保留 main 交接说明。补齐 OPDS 的五个 API 文档条目并扩展现有格式模块示例，SDK 文档覆盖检查与控制台示例均通过。


③ 命令与实际输出（合并 main 后）

命令在仓库根目录执行。完整参数、退出码与日志关联见 [commands.json](commands.json)。日志统一为 LF 并去除行尾空白。

```text
cmake --build build/w --target check_sync check_shell_opds exreader-opds-test -j 2
Linking CXX executable check_sync.exe (exit 0)
```
完整输出：[post-main-build-console.txt](post-main-build-console.txt)。

```text
ctest --test-dir build/w -V -R ^(windows-selection-sync|windows-opds-timeout|windows-a11y-static|native-opds)$
PASS WebDAV 15 scenarios; windows_created=0
PASS error_timeout code=timeout win_error=12002 http=0 accepted=1 elapsed_ms=4000
25/25 static checks; 9 historical PNGs; manual checklist generated
100% tests passed out of 4
```
完整输出：[post-main-ctest.txt](post-main-ctest.txt)。

```text
build\w\check_shell_opds.exe https://www.gutenberg.org/ebooks.opds/ docs\ui\evidence\headless-20261110\post-main-opds
13/13 checks passed; list=25; next overlap=0; search=7; EPUB=24864457 bytes, magic=PK; timeout win_error=12002; 404/cache checks passed
```
完整输出：[post-main-opds-gutenberg.txt](post-main-opds-gutenberg.txt)。

```text
C:\Python314\python.exe -X utf8 tools/check_version_consistency.py
PASS: SDK 3.42.0; ABI 1; 552 live exact literal exceptions
```
完整输出：[post-main-version-final.txt](post-main-version-final.txt)。

```text
C:\Python314\python.exe -X utf8 tools/check_layers.py build/w
121 objects, 1369 symbol references, 0 remaining inverse references, 0 new
1068 source/header dependencies, 0 inverse includes
```
完整输出：[post-main-layers.txt](post-main-layers.txt)。

```text
cmake -S examples/windows -B build/host -DEXR_SDK=out\sdk -DEXR_READER_WINDOWS_SHELL=ON "-DCMAKE_C_FLAGS=-O2 -Wall -Wextra -Werror"
Configuring done; Generating done (exit 0)
```
完整输出：[post-main-configure-host.txt](post-main-configure-host.txt)。

```text
cmake --build build/host --target EXReader -j 2
[3/3] Linking CXX executable EXReader.exe (exit 0; compile only)
```
完整输出：[post-main-build-host.txt](post-main-build-host.txt)。

```text
C:\Python314\python.exe -X utf8 tools/regress/run_realbooks.py --manifest tools/regress/corpus.json --dll build/w/libexreader.dll --font tests/fixtures/fonts/primary.ttf --layout tools/regress/layout.json --output docs\ui\evidence\headless-20261110\post-main-realbooks.json --baseline docs/ui/evidence/webdav-20261110/books-final.json --source-revision 8c08679f35de45108c91ae7d1096b57d456eeb26 --workers 2
19/19 books; 9995 pages; total_glyphs=8662386; source/page/glyph counts unchanged; hash_changed_pages=0; needs_review=false
```
完整输出：[post-main-realbooks.txt](post-main-realbooks.txt)。

```text
C:/Users/Oscar/AppData/Local/Microsoft/WinGet/Packages/BrechtSanders.WinLibs.POSIX.UCRT_Microsoft.Winget.Source_8wekyb3d8bbwe/mingw64/bin/gcc.exe -std=c11 -Wall -Wextra -Wpedantic -Werror -Iinclude docs/examples/formats.c build/w/libexreader.dll.a -o build/w/check_opds_docs.exe
exit 0 (-Wall -Wextra -Wpedantic -Werror)
```
完整输出：[post-main-docs-compile.txt](post-main-docs-compile.txt)。

```text
build\w\check_opds_docs.exe
format=2
OPDS entries=1 title=Catalog
```
完整输出：[post-main-docs-example.txt](post-main-docs-example.txt)。

```text
C:\Python314\python.exe -X utf8 tools/check_sdk_docs.py --output docs\ui\evidence\headless-20261110\sdk-docs-static.json
documented_functions=462; public_functions=462; coverage_percent=100.0; errors=[]; passed=true
```
完整输出：[post-main-docs-coverage.txt](post-main-docs-coverage.txt)。

`tests/check_reading_release.py` SHA-256 仍为 `6eb22a304686b2160d1f283a709936bfdfd65c3b0f5e10bb060f457c4faffb2b`，与续跑前字节一致。版本例外随 main 仅删除 35 个条目，其余 552 个条目内容不变，保留 indent=2。`include/exr/opds.h` 已登记 doc 层，没有新增 `src/*.h`。二进制和保护文件身份见 [post-main-artifact-identities.json](post-main-artifact-identities.json)。

19 本书使用 b1 原有 `books-final.json`、`tools/regress/layout.json` 和 `primary.ttf`；比较见 [post-main-realbooks.diff.json](post-main-realbooks.diff.json)，完整逐页记录见 [post-main-realbooks.json.gz](post-main-realbooks.json.gz)。早先的 787e86e0 验收和编译失败日志也保留在本目录。下载的 Gutenberg EPUB 仅保留在本地 `build/headless-opds/`，提交大小和 SHA-256。

④ 需要真实窗口的待办（本轮全部未执行）

- 外部 UIA：必须有运行中的控件树，检查 Name/HelpText、文本/选择 provider 和事件。
- Tab 顺序与焦点恢复：必须观察实际焦点和消息循环，检查正反向循环、面板子控件和 Esc 后焦点。
- 焦点环：必须观察实际绘制、裁切和当前 DPI 下的效果。
- 对比度观感：必须由用户看屏幕确认可读性；主题和高对比度仅由用户决定是否手动操作。
- 同步宿主呈现：状态刷新、错误文字、密码框清空需要实际控件。
- OPDS 宿主呈现：面板操作、进度、取消和下载后打开需要实际控件。

逐项步骤和旧截图链接见 [C2-MANUAL-CHECK.md](../../../a11y/C2-MANUAL-CHECK.md)，交主控在用户在场时安排。

本轮未启动 GUI 主程序、未注入输入、未改系统设置、未打开浏览器或使用 CUA；宿主 EXE 仅编译与读取文件身份。
