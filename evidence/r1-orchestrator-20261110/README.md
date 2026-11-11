R1 复核记录，2026-11-10。原始 checkout / origin/main 为 `6000a89d`；PR #124 固定为 `6cb452da`，PR #121 固定为 `5d642281`。复核分支已快进到 #124，修补在此基础上交付；#121 在独立目录测试，没有把其 workflow 删除合入本分支。

第 9 项原脚本实际位于 `C:/Users/Oscar/OneDrive/Desktop/deepseekHarness/ops/dispatch.ps1`。已保存原始字节为 [09-dispatch-before.ps1](09-dispatch-before.ps1)，修复同步至该路径及本仓库 `ops/dispatch.ps1`。没有启动真实 Codex / Claude agent；调度运行测试的目标是原生 CRT 参数回显程序。

| # | 结论 | 命令与实际结果 / 原始证据 |
|---|---|---|
| 1 | **有问题，已修**：x64 的 16 字节足够；x86 分配头过度对齐 | MSVC x64/x86 编译、运行 `tests/check_orchestrator_alignment.c`：模型类型均需 8 字节对齐；原 x86 分配头出现未对齐，修后两架构各 4096 次均为 0；[修前](01-header-before-x86.txt)、[修后 x86](01-header-after-x86.txt)、[修后 x64](01-header-after-x64.txt)。两架构各 11 组语义测试及 62 次注入分配失败通过。 |
| 2 | **有问题，夹具已修；另有边界外阻断** | 两次恢复均等于历史字节，但都撤掉了 `closing()`；`python tests/check_reading_release.py` 原版报 `WinError 32`。修后夹具数据库可立即删除，[前后对照](02-fixture-closure.json)；版本检查 `PASS: SDK 3.42.0; ABI 1; 587 live exact literal exceptions`。完整运行仍暴露 `tools/reading_release.py:93` 同类泄漏，[日志](02-release-after.txt)。该文件未修改；[拟议补丁](02-proposed-tool-fix.patch)在独立目录完整测试 `accepted=true, checks=54, exit=0`。 |
| 3 | **正确** | 两个字段都有真实读写；`gcc ... font_layout.c` 实测 x64 `sizeof(exr_font)=72, alignof=8, raster_cache=56, manager_required=64`。原生渲染确认缓存创建并复用；字体管理 4 组通过。[布局](03-layout.txt)、[缓存运行](03-runtime.txt)、[固定源文件哈希](03-font-sources.json)、[18 项回归](03-04-ctest.txt)。 |
| 4 | **有问题，已修**：声明新增 opaque block，模型仍拒绝；JSON 重复键 | `gcc ... src/docx_edit.c tests/check_edit_opaque_block.c`：原版 `create status=1`，修后 `status=0` 且 XML 深拷贝、undo/redo 保留、空 opaque 块拒绝。[修前](04-opaque-before.txt)、[修后](04-opaque-after.txt)、[reflow 联测](04-opaque-reflow.txt)。构建通过，18/18 CTest，121 objects 层检查零反向依赖；C/C++ 头检查通过，24 个声明在实际 DLL 全部导出。 |
| 5 | **正确，确有失去 workflow 入口的保留脚本** | 找到 reflog 中 `1130174a -> 1e3b681a`：161 个 tests 全部恢复，最终 #121 与原 main 的 blob 全相同；两份 tools 脚本也恢复。最终只删 133 个 workflow。[161 文件清单](05-restored-files.json)、[删除 workflow 对 tests 的直接引用及剩余入口](05-cleanup.json)。 |
| 6 | **正确** | `python .../audit.py cleanup`：`before=587, after=552, removed=35, exact_filter=true, missing_files=[]`。按已删 workflow 过滤后逐条相等，[证据](06-exceptions.json)。 |
| 7 | **正确** | `python tools/check_ci_hygiene.py` 在 #121 快照中 exit=0，259 条全部仍匹配真实违规；259 条也恰好等于原 531 条按存活文件过滤。计数、259 个规则绑定、分类、checker SHA、baseline SHA 全吻合，[meta 核对](07-hygiene.json)、[完整运行](07-hygiene-run.txt)、[过滤比较](07-filter-comparison.json)。`tests/check_ci_hygiene.py --rule failfast` 正反控制与真实 exit=37 检查通过。 |
| 8 | **正确** | `git diff-tree -r -M --name-status 4d14e5eb`：91 个 `R100`，内容未变；活动代码按目录名搜索无旧目录读写。[移动清单检查](08-moves.json)、[活动代码搜索](08-code-paths.txt)。`collect_cfi_acceptance.py` 写的同名前缀 `.json` 是目录之外仍存在的文件。 |
| 9 | **有问题，已修** | 原生 `wmain` + 实际 `Start-Process`：414 参数中原版有 5 个内容错误，修后 0 个；原版完整调度子进程 7 / 脚本 0，修后两者 7；Claude `-Out` 空文件改为完整输出。原生子进程确认 BelowNormal、2 核 mask=12、jobs=2、SW_HIDE。[参数修前](09-args-before.json)、[参数修后](09-args-after.json)、[运行修前](09-runtime-before.json)、[运行修后](09-runtime-after.json)。 |

第 1 项实际类型测量（`sizeof / alignof`，MSVC 19.44）：

| 类型 | x64 | x86 |
|---|---:|---:|
| `exr_edit_block` | 112 / 8 | 96 / 8 |
| `exr_edit_run` | 200 / 8 | 176 / 8 |
| `exr_edit_section` | 816 / 8 | 816 / 8 |
| `exr_edit_part` | 32 / 8 | 24 / 8 |
| `long double` | 8 / 8 | 8 / 8 |
| 原 `edit_allocation` | 16 / 16 | 16 / 16 |
| 修后 `edit_allocation` | 16 / 16 | 8 / 8 |

这些模型类型只含普通整数、指针、字符数组及其聚合，没有 SIMD 或显式过度对齐成员。回归用例还静态检查了内部 `edit_block`、`edit_change`、事务及文档类型。x86 失配发生在分配头自身：模型载荷虽仍满足 8 字节，`calloc` 的地址不保证满足头类型要求的 16 字节。修补将 MSVC x64/x86 分开，不改变非 MSVC 分支。微软的 [CRT 堆对齐说明](https://learn.microsoft.com/en-us/cpp/build/stack-usage?view=msvc-170)与实测吻合。

第 2 项两次恢复后的 SHA-256 都是 `6eb22a304686b2160d1f283a709936bfdfd65c3b0f5e10bb060f457c4faffb2b`。因此“恢复字节”本身做对了，但丢掉了必要的连接关闭修复。版本守卫检查当前行的 SHA，再核对历史 fixture 的行与整文件 SHA；它不要求当前整文件始终等于历史 fixture。这里只移动三条当前行号，历史 commit、fixture 行号、全部 SHA 与拒绝断言保持不变，[精确核对](02-exception-changes.json)。Python [连接上下文说明](https://docs.python.org/3/library/sqlite3.html#how-to-use-the-connection-context-manager)也明确上下文管理不会关闭连接。

第 3 项 `raster_cache` 在 `fonts.c` 中创建、查找、插入、释放，`raster.c` 调用缓存；`manager_required` 在 `font_manager.c` 记录必需字体前缀，`layout.c` 按它保留必需字体、驱逐自动发现的尾部，并复制到嵌入字体链。`exr_font` 在公开头文件里是不透明类型，字段偏移不是公开 ABI；全部内部使用点由同一头文件构建。不能混用不同内部布局编译的对象文件。原生缓存探针输出 `PASS: raster_cache initialized by raster.c, retained on second render`，manager integration 包括自动尾部为嵌入字体腾位的行为。

第 4 项修补保留已有 enum 数值，只把校验上限扩到已声明的 `EXR_EDIT_OPAQUE_BLOCK`，要求它携带非空 XML；reflow 继续按现有接口合同对 opaque 内容返回 `EXR_UNSUPPORTED`。`layers.json` 删掉同名同值的重复 header 登记。`cmake/modules.cmake` 的并集本身正确，编辑头和 reflow 头产生的 24 个声明都进入导出表，[导出清单](04-export-inventory.json)。

构建使用固定 #124 原始树，命令及配置见 [04-configure.txt](04-configure.txt) 与 [04-build.txt](04-build.txt)；`cmake --build C:/tmp/exr-r1-review-20261110/build --parallel 2 --target exreader exreader-reflow-test exreader-font-manager-test exreader-font-test exreader-page-cache-test` 返回 0。`ctest` 选择 12 个 reflow 场景、4 个字体管理组、font、page-cache，共 18/18，通过时间 31.38 秒。`python tools/check_layers.py C:/tmp/exr-r1-review-20261110/build` 返回 0：121 objects、1387 symbol references、1065 source/header dependencies、0 inverse。修后模型另经 MSVC x64/x86 语义及故障测试，并直接链接同一未改动的 reflow DLL 做 opaque 用例；其输出为 `create status=0`、`reflow status=11`（预期 `EXR_UNSUPPORTED`）。

第 5 项初版的 296 个删除实际是 **133 workflow +161 tests +2 tools**；两个 tools 是 `tools/check_reader_product_integration.py` 和 `tools/check_reader_webdav_interop.py`。最终它们都与原 main 同字节。161 个 tests 分布在 21 个顶层 tests 子目录；这 21 个目录和两个 tools 在余下 123 个 workflow 中都没有直接路径引用，[完整入口核对](05-restored-entrypoints.json)。失去自动入口的例子包括 `tests/android_font_reader`、`tests/apple_android_relay`、`tests/reader_next_s15` 等。保留它们不会重新启用 CI；静态无引用也不能证明永远无手工用途。部分历史 guard 会读取已删 workflow，保留不等于当前可直接独立运行。

第 7 项修后 baseline SHA 为 `7ae06de8a29ebf74af833120c4f6581a9635afe37d1b466aedc3374359991bef`，checker SHA 为 `b813482180561351a45dbb25fbc358933389bdb1edb1eb8f4e617d54fc88dba2`；分类为 failfast=242、negative=9、diagnostic=4、packaging=4。`source_commit=5787dda9...` 存在，且其中 checker 的 SHA 也吻合。当前复核分支没有合入 #121，所以本分支例外表仍为 587 条；552/259 的结论针对固定的 #121 快照。

第 9 项最小反例可写为三个字符：空格、反斜杠、LF，即 JSON `" \\\n"`。原来第二次正则替换用 `$`，.NET 允许它匹配末尾 LF 之前；因此错误地复制了 LF 前的反斜杠。改成绝对末尾 `\z` 后恢复正确。引号前 `2n+1` 个反斜杠、闭引号前 `2n` 个反斜杠的处理仍遵循 [Windows CRT 参数规则](https://learn.microsoft.com/en-us/cpp/c-language/parsing-c-command-line-arguments?view=msvc-170)。测试通过 AST 提取被测脚本中的真实函数，没有复制一份待测算法。

调度补丁同时正确透传退出码、捕获并回放隐藏进程的 stdout/stderr、将 Claude stdout 直接写到 `-Out`，并给 Claude 加 `--no-chrome` 与已配置的 windows-mcp 等 CUA 工具 deny。安装的 Claude `--help` 确认两个 CLI 参数存在；[官方 CLI 说明](https://code.claude.com/docs/en/cli-reference)和[工具名规则](https://code.claude.com/docs/en/permissions)支持这些参数。运行检查解析了送达 Codex 的 TOML 参数，核对三个插件为 false、两项 pipe 环境配置为字符串 0；Claude 检查禁用参数。没有通过真实模型会话枚举最终可用工具，CUA 结论限于配置和参数送达。

可复跑的参数回归命令（先在 MSVC Developer Shell 编译 echo）：

```powershell
cl /nologo /W4 tests/dispatch_argv_echo.c /FeC:\tmp\exr-r1-review-20261110\argv-echo.exe
pwsh -NoProfile -File tests/check_dispatch_args.ps1 -DispatchPath ops/dispatch.ps1 -EchoExe C:/tmp/exr-r1-review-20261110/argv-echo.exe -OutputPath C:/tmp/dispatch-args.json
# PASS: CRT argc=414; all argument boundaries and UTF-16 code units match
python tests/check_dispatch_runtime.py ops/dispatch.ps1 C:/tmp/exr-r1-review-20261110/argv-echo.exe C:/tmp/dispatch-runtime.json --require-fixed
# 两引擎 exit=7、prompt_matches/priority_ok/affinity_ok/hidden_ok 全为 true；测试进程 exit=0。
```

静态/历史检查入口为 `python evidence/r1-orchestrator-20261110/audit.py release cleanup moves`；模型 MSVC 原始探针命令及逐次输出保存在 `01-*.txt`，修补后的不透明块回归源为 `tests/check_edit_opaque_block.c`。所有负例证据先于对应源码修补保留；既有测试断言没有改动。仓库 `.github/` 没有修改。
