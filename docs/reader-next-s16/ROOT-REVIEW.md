# S16 root source review / S15 integration note

## Root evidence repair pending

Update: root round 1 passed. Source
`28df223d1df2aa3e551ad4796d5e7615bd706d8e`, run `40236387400/1`, both
producers and strict completed/success. Each platform retained all three
149-check original suites and the 162-check raw suite, six wire cases and
three moves. The strict log independently reports both compatibility verdicts
true, nine program roles and three archives authenticated, with no problems.
The 15 actual artifact mutation controls per platform rejected all changes.
Full job/artifact identities are in `root-review-validation.json`.
This supersedes the pending verification status below, not the original
failure/round-limit history. Host integration and product grants remain absent.

The root review now uploads all nine actual C/C++ consumer programs and all
three installed jump-history archives. Its strict job recomputes each native
program's bytes/digest, all three original-suite source/run/attempt identities,
raw report/program/install bindings, baseline/default projections, bounded
header insertions and default/raw archive symbols. Duplicate JSON keys and
unsafe/duplicate ZIP members are refused. Actual artifact mutation controls
cover all nine programs, three archives and three original-suite identities.

These changes do not alter the module or original tests. Root review has its
own maximum of three full Actions rounds; the original worker's excess rounds
remain disclosed. Verification is pending; no local checks were run.

2026-10-25。只读 Git、源码、原验证器及 GitHub run/job 元数据；没有本地构建、测试、语法检查或工件处理，没有启动新的运行。

## S16 可接入的候选源码

- 完整受测 source：`1f588ca880e8dde7c8293a2769e3663194194acd`。
- 文档封存：`777c56b33c2a9c01f38cc2cbd2a064220b7525a0`，相对 source 只有 `HANDOFF-RESULT-S16.md`。
- run `40229935121/1` 的实际 head 是上述 source，Linux `121279276994`、Windows `121279276596`、strict `121280188346` 元数据均 completed/success。
- 相对固定起点 `e67d87cbeabb2457e0852f681ef0b27b2c0da4d8`，产品模块改动精确限定为 `apps/reader/jump-history/{CMakeLists.txt,EXReaderJumpHistoryConfig.cmake.in,include/reader_jump_history.h,src/jump_history.cpp}`。另外新增 `tests/reader_next_s16/`、`.github/workflows/reader-next-s16.yml`、`docs/reader-next-s16/` 与封存文档。
- 安全取回方式：从 source 取这四个模块文件及独占测试/文档路径；若保留原提交历史，取 `123124fe4bd85f3196dec4c30563e2e7d97ee32f` 至 `1f588ca880e8dde7c8293a2769e3663194194acd` 的八个连续提交，再单独取 `777c56b3` 文档。不要用整个旧起点树替换共同源码。

## ABI 与旧行为

原公开结构、枚举、函数声明、`READER_JH_VERSION="0.1.0"`、`READER_JH_STRUCT_VERSION=1` 均保留。头文件只有插入；新增 `READER_JH_INSTALL_VERSION` 区分默认 0.1.0 与显式 raw 安装 0.2.0，新增两个 raw 函数被 capability 宏包住。旧二进制 C ABI 没有改名或布局变化；CMake 的 0.2.0 则有意不是 `find_package(... 0.1.0 EXACT)` 的替代包。

`reader_jh_commit` 仍调用 `reader_rs_encode_v2`，旧 `reader_jh_commit_wire` 给内部 helper 传 `raw=false`，仍调用 `reader_rs_decode`。只有新增函数传 `raw=true`，进入 `reader_rs_decode_raw_v3`；fixed capture 入口只调用 `reader_rs_encode_fixed_v3`。共享 reading-state/revisions 与原 `tests/reader_jump_history` 在 S16 分支未改。默认编译中的 v3 identity 分支对旧 decoder 不可达；v1/v2 的 key 字节路径保持原样。

新 v3 key 对 exact/prefix/suffix 增加存在位，再按显式长度追加字节，因此 NUL 后内容参与身份，NULL 与 allocated-empty 不合并；非空 exact 指针仍是共同 commit 条件，NULL exact 被拒绝，textless 的 allocated-empty point 可保留。共用的线程检查、限额、forward truncation、PAGE 合并、复制、ticket 与错误前不变逻辑没有替换。该实现只保存 wire，不解析导航、不写 revision、SDK 笔记或进度。

安装族通过版本、codec compile definition 和已有 `_exr_raw_guard_target` 拒绝混配；raw 安装 Config 会检查 adapter/JH 头文件与归档来源。该 guard 来自 revisions raw Config，不把它引入默认包。raw header 的曝光依赖消费安装 target 带出的 `EXR_READER_SELECTOR_BYTES_CANDIDATE=1`，不能手工给默认归档定义宏后假装具备 raw ABI。

## 验证器实际覆盖与缺口

producer driver 确实从安装前缀构建 baseline/default/raw 三族，原套三次调用使用同一原测试；raw 的消费者副本仅调整请求包版本。default 与 baseline 比较 cases/lifecycle/checks/no-write/books/版本，默认归档检查不含新增 raw 符号；新 raw 探针实际构建 PDF NUL、TXT/EPUB/CBZ、v1/v2 replay、v3、限额与 no-write 的检查。

strict 认证两个真实同 run 的 ZIP 字节/散列，并绑定 raw summary 的 source/run/attempt、原始 probe/report，比较两平台 cases/lifecycle/语义/版本/no-write。其完整性仍有边界：default-baseline 等价和 default 无 raw 符号依赖 producer 的 result 标志，strict 未再次重算原两份 projection/归档；只有 raw probe 的上传程序被独立重新散列，其他消费者和 module archive 没有同等级绑定。JSON 用普通 loads，未做 S15 那种 duplicate-key 负例。这些不改变源码 ABI 审查结论，接入共同 strict 时应补齐所需绑定。

当前授予范围仅 Linux/Windows 独立模块候选。macOS、Android、Apple、Linux 图形宿主均未据此接线；back/forward UI、键盘、持久化/同步、性能预算及共同源码重新验收仍待 root。原 S16 workflow 的 ownership 固定从 e67 比较，不能直接对已合并多个包的共同树启动而声称原 guard 通过；需保留原判定、加显式共同来源 wrapper。

## S15 阻止直接授予 EXACT 图完整性的缺口

S15 source `c1737e2a599d7d2cfc6d87569ab5e65093206a54`、docs `6e64ecd5f913b1242067818f7acd84936a6628e7`；run `40227960455/1` 的 head/source 和五个成功 job 已核实。`original-export/include` 与 `src` 相对 `25cd7b4b15d952e3f7a10e39ed80ae16a3d9a3ee` 无差异，旧 C ABI/导出行为保持；模块 CMake 与安装 Config 加了 3.40 默认、3.41 显式 EXACT。

但源码 `find_package(EXReader ... EXACT)` 和安装 `find_dependency` 后，都未核验已有 `EXReader::exr_library` 来源。SDK Config 直接 include CMake 生成的 Targets；完整旧 SDK targets 若已存在，后续新包元数据成功并不能证明链接目标来自新前缀。已有四个 graph negatives 全为新进程 configure，没有“先预载旧 targets，再切到新 SDK Config”的路径。因此 S15 不能直接授予已有-target 完整隔离。root 已授权在独立 S15 review 分支做云端复现与 provenance gate 修复；本记录不声称已经复现或修复。
