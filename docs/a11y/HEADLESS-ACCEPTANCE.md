本轮完成无窗口验收迁移；宿主只编译，运行时 UIA/焦点/视觉项交主控安排。

1. 上一轮进度

A11Y-OUT.txt 在本轮开始时的最后一行：

> 步骤 3 完成：编译 EXReader.exe(-Werror) 通过；探测：UIA 已读到壳层按钮名称+HelpText（IAccPropServices 生效）；封面页无文本→DocumentRange 返回 ELEMENTNOTAVAILABLE（符合现有契约），取证脚本改为翻到有文本页再读。写取证脚本 docs/ui/acceptance/check_a11y_c2.py。

当前工作树缺少 b1/b2 源文件，因此从原功能分支 `471900a2`（WebDAV）和 `83a554ae`（OPDS）取回必要源码及构建登记，复用原方案。未合并它们的 GUI 脚本和历史宿主验收产物。

2. GUI 验收替换对照

| 原验收 | 本轮替代 | 证据 |
| --- | --- | --- |
| WebDAV 宿主窗口及操作脚本 | `check_sync.c` 包含生产宿主实现但不进入 WinMain；直接使用 `sy_sync_now`、真实存储加载器和内存 WebDAV TCP 服务；`windows-selection-sync` 改为这个不创建 HWND 的控制台入口 | `ctest-final.txt` |
| OPDS 宿主操作/截图 | 宿主编译通过 + `native-opds` + `check_shell_opds` 调用与宿主共享的 WinHTTP 网络层；本地服务 bind 回环随机端口，只 accept、不响应，断言 WinHTTP 12002 → ONET_TIMEOUT、HTTP=0、有中文提示及耗时上限 | `opds-net.json`、`opds-timeout.json` |
| C2 启动应用、外部 UIA、模拟按键和切换系统高对比度 | `check_a11y_c2.py` 改成仅用标准库读取源码，检查 Name/HelpText 注册路径、正文提供器/事件调用、Tab 配置、焦点环 token 与系统颜色读取路径；生成静态 JSON 和人工清单 | `c2/result.json`、`c2-static.txt` |
| 重新拍摄 C2 截图 | 对 /ui 证据中已有 25 张 PNG 记录路径、大小和 SHA256；保持历史证据标记 | `c2/result.json` |
| 真实书籍宿主回归 | 通过 DLL 接口逐页重排和离屏光栅化，比较书籍源哈希、页数和逐页像素哈希 | `realbooks.json.gz`、`realbooks.diff.json` |

WebDAV 的 15 类场景：合并、首次上传、增量、冲突、墓碑、LWW、401、404、超时、403、500 重试、远端损坏、离线队列、重连、凭据。额外覆盖空闲不上传、第二设备拉取及两空设备各新增一条批注的合并。

控制台入口不初始化窗口、字体或 publication。原选择测试中的 HWND/剪贴板用例不在本轮运行。慢服务器收尾等待连接线程结束，避免延迟请求消耗后续错误注入；本地停止监听产生真实断网，重连复用同一端口。凭据使用 DPAPI 的 `CRYPTPROTECT_UI_FORBIDDEN` 路径。

集成时修复两处编译问题：HTTP→HTTPS 升级可能超长截断，改为拒绝过长地址，并加入边界检查；同步命令行便捷入口在 GUI 构建下未使用，改为 `static inline`。

3. 验证命令与实际输出

所有证据相对路径均位于 [headless](../ui/evidence/a11y-uia-20261110/headless/)。

```powershell
$env:PYTHONUTF8='1'
cmake -S . -B build/a11y -DCMAKE_PROJECT_EXReader_INCLUDE=C:/Users/Oscar/Documents/Codex/EXReader-c2-a11y-20261110/examples/windows/selection_tests.cmake
cmake --build build/a11y --target check_sync check_shell_opds exreader-opds-test -j 2
& docs/ui/acceptance/build_tts_host.ps1 -SdkBuild build/a11y -Output build/headless-host
```

构建均退出 0；宿主 EXReader.exe SHA256 为 `3fc6b0a2e540f09705ace77d8a01622b467436a6f26a3f1db89a665d0f1ae84c`。完整二进制和源码哈希见 `build-provenance.json`。EXReader.exe 只编译，未启动。

```powershell
ctest --test-dir build/a11y -R '^(windows-selection-sync|windows-opds-timeout|windows-a11y-c2-static|native-opds)$' -V
```

退出 0，实际汇总 `100% tests passed out of 4`；完整输出见 `ctest-final.txt`。WebDAV 的实际输出包括：

```text
PASS sync: 15 scenarios; HWNDs created=0
OFFLINE server down: failure reported, 3 drafts queued and persisted in sync.json
RECONNECT 3/3 offline edits pushed (X annotations=5, Z created, W created), queue empty
CREDENTIALS password/username absent from all files; DPAPI blob roundtrip ok; tampered blob rejected; delete removes file
```

```powershell
& build/a11y/check_shell_opds.exe https://www.gutenberg.org/ebooks.opds/ build/opds-online
```

退出 0。实际输出节选：

```text
PASS error_timeout_local_accept_no_response code=timeout win_error=12002 http=0 elapsed_ms=4015 accepted=1
PASS list_ge_20 ... entries=25
PASS next_page_differs page1=25 page2=25 overlap=0
PASS download_epub bytes=24864457 ... magic=PK
PASS opensearch_ge_1 ... entries=7
PASS cache_hit_within_ttl second fetch from_cache=1 hits=1
PASS cache_expires fetch with expired ttl from_cache=0
```

上述带省略号的行仅节选字段；原始完整输出在 `opds-console.txt`。首次线上 OpenSearch 返回 HTTP 504，保留 `opds-console-attempt1.txt` 和 `opds-net-attempt1.json`；重试后全部检查通过。本地超时回归不依赖 Gutenberg。

```powershell
python -X utf8 docs/ui/acceptance/check_a11y_c2.py --self-test --out docs/ui/evidence/a11y-uia-20261110/headless/c2
```

退出 0，34 项静态/证据库存检查通过；三个反例分别删除 Name、HelpText 和注册调用，均被拒绝。实际尾部输出：

```text
Historical screenshots: 25; runtime UIA: pending_external_manual
PASS static negative controls: missing Name, HelpText, registration call
```

```powershell
python tools/regress/run_realbooks.py --manifest tools/regress/corpus.json --dll build/a11y/libexreader.dll --font C:/Users/Oscar/exr-deps/reader-font/Reader.otf --layout tools/regress/layout.json --output build/headless-realbooks.json --baseline docs/ui/evidence/a11y-uia-20261110/final/realbooks.json --workers 4 --source-revision headless-c2-working-tree
python tools/regress/run_realbooks.py --baseline docs/ui/evidence/a11y-uia-20261110/final/realbooks.json --candidate build/headless-realbooks.json --output docs/ui/evidence/a11y-uia-20261110/headless/realbooks.diff.json
```

两个命令均退出 0。实际输出：

```text
"requested_books": 19, "successful_books": 19, "failed_books": [], "total_pages": 11318, "total_glyphs": 8648571
{"comparable": true, "incompatible_conditions": [], "added_books": [], "removed_books": [], "hash_changed_pages": 0, "failed_books": [], "needs_review": false}
```

19 本源书哈希及页数未变，逐页像素哈希 0 变化。完整结果压缩保存在 `realbooks.json.gz`。

```powershell
python -X utf8 tools/check_layers.py build/a11y
python -X utf8 tools/check_version_consistency.py
git diff --check
```

均退出 0。实际输出：

```text
121 objects, 1361 symbol references, 0 remaining inverse references, 0 new
1068 source/header dependencies, 0 inverse includes
PASS: SDK 3.42.0; ABI 1; 587 live exact literal exceptions
```

受保护文件逐字节校验见 `protected-files.json`：`tests/check_reading_release.py` SHA256 `6eb22a304686b2160d1f283a709936bfdfd65c3b0f5e10bb060f457c4faffb2b` 未变；`tools/version_literal_exceptions.json` 字节未变且仍为 indent=2。未新增 src/*.h；新增 OPDS 源码及公共头文件在 layers.json 登记。

4. 真实窗口待办

完整步骤见 [C2-MANUAL-CHECK.md](C2-MANUAL-CHECK.md)。以下项目需要真实窗口，因为它们依赖运行中的原生控件、外部可访问树、焦点状态或实际显示像素，交主控安排用户在场验收：

- 外部 UIA 读取控件 Name/HelpText、正文/选区及 TextChanged、TextSelectionChanged、StructureChanged 事件。
- Tab/Shift+Tab 循环、搜索/目录/设置展开和关闭后的焦点连续性；真实键盘翻页和目录跳转。
- 按钮焦点环、正文无整页焦点边框、目标 DPI 下清晰度与裁切。
- 主控安排的高对比度环境下，正文、按钮、目录、设置的对比度观感。
- 新增 WebDAV/OPDS 界面的原生焦点及读屏体验。

本轮运行时 UIA 和视觉验收保持待确认。未运行任何 GUI 主程序、浏览器或 CUA；未模拟输入，未修改系统设置。

验收代码提交 `1f07047e` 已推送，draft PR：[#130](https://github.com/NoGod3524/EXReader/pull/130)。PR 与 main 仅共享进度文件 OUT.txt 冲突；本分支该文件为空，已恢复 main 的记录以消除冲突。引擎源码及上述验证结果保持一致。
