# J24：Unix 可重定位分发候选

本包从固定起点 `f43baf9182d75907c0cb5d6f77048f27bca8c950` 独立实现，只改本包白名单：
`tools/reader_distribution_unix/**`、`tests/reader_distribution_unix/**`、
`.github/workflows/reader-distribution-unix.yml`、本文件与
`docs/validation/reader-distribution-unix.json`。SDK 冻结树（`src/`、`include/`、`cmake/`、
顶层 `CMakeLists.txt`、`tests/fixtures/`、`bindings/`、`native.yml`、`reliability.yml`）
与产品 schema（`apps/reader/store`）逐字不变；R6 已验收的六份原包及其散列不被改写或冒用。

## 解决的三件事

1. **Linux/macOS 构建路径**：候选不使用 CMake preset，而由工作流显式传入与 `reading-core`
   preset 相同的 20 个开关与 `CMAKE_INSTALL_PREFIX`，安装到短路径 `build/install-a`，再整体搬到
   另一条更长绝对路径下重建、重跑；搬动后的前缀不再依赖构建目录或安装目录。
2. **上游 pkg-config 绝对 prefix**：安装布局本身没有 pkg-config 单元。候选新增唯一的
   `lib/pkgconfig/exreader.pc`，其 `prefix=${pcfiledir}/../..`，其余变量（`libdir`、`includedir`、
   `vendordir`）都由 `prefix` 派生；`Libs`、`Libs.private`、`Cflags` 中不允许出现绝对安装路径或
   `-Wl,` 包装参数。审计同时用 `pkg-config --cflags --libs --static exreader` 反查：所有
   `-I`/`-L` 必须落在搬动后的前缀内，组件归档、私有归档、`-pthread -lm` 与安装包导出的编译
   定义齐全。上游依赖构建（libwebp、aom、sharpyuv）还会把私有静态库的 `*.pc` 一并装进
   `lib/pkgconfig`，其 `prefix=` 是构建机的绝对路径。候选把这些私有单元移除并记录路径/字节/
   SHA-256/原 prefix 作为缺陷证据，只保留公共的 `exreader.pc`；私有归档已由 `Libs.private`
   覆盖，消费者不需要这些单元。移除前先判定：**已经可重定位的上游单元一律拒绝删除**（改报缺陷、
   候选失败），不做“先删后判”。
3. **重复归档材料**：安装会同时写入 `LICENSE`、`THIRD_PARTY_NOTICES.md`（根与 `share/exreader/`）
   等字节相同的材料。候选按内容散列规划去重，只对 `docs/`、`share/`、`examples/`、`bindings/`
   与根许可/自述文件生效；组件归档、私有归档与公开头一律不参与。硬链接共享同一 inode 也共享同一
   权限位，因此**字节相同但可执行位不同的副本不视为重复**（否则去重会静默改掉安装权限）。
   去重使用 `os.link` 保留每个路径，删除前后分别构建并运行消费者与九格式 smoke，再比对 PNG
   摘要、逐项计数器与九条 smoke 结果；封包时重复成员以 tar 硬链接条目只存一份，并在清单里记录
   每个成员（含硬链接成员）的权限位，解包后逐项复核。

## 公开契约

~~~pkgconfig
prefix=${pcfiledir}/../..        # 任何前缀长度下都成立
libdir=${prefix}/lib            # 组件归档 libexr_<layer>.a
vendordir=${libdir}/exreader     # 私有静态依赖 libexr_vendor_<name>.a
includedir=${prefix}/include
Name: EXReader / Version: 3.40.0
Cflags: -I${includedir} -DEXR_STATIC        # 与安装包 INTERFACE_COMPILE_DEFINITIONS 一致
Libs: -L${libdir} -lexr_<layer>...            # 依赖者在前，顺序取自安装后的 CMake 导出
Libs.private: -L${vendordir} -lexr_vendor_<name>... -pthread -lm [-ldl]
~~~

- **输入/输出**：`pkg-config --cflags/--libs/--static exreader` 的输入只有
  `PKG_CONFIG_PATH=<prefix>/lib/pkgconfig`，输出只有 `-I`/`-D`/`-L`/`-l` 与系统线程/数学
  标志；不写出前缀以外的路径，不引入 rpath 或包装器参数。
- **编译接口一致性**：`Cflags` 必须逐字携带安装包导出的 `INTERFACE_COMPILE_DEFINITIONS`
  （本 SDK 为 `EXR_STATIC`），既不多也不少。少了这一条，pkg-config 消费者的编译接口就与
  `EXReaderTargets.cmake` 描述的包不同（Windows 上缺 `EXR_STATIC` 会改变每一个声明）。
- **链接顺序**：组件归档按 `EXReaderTargets.cmake` 的 `INTERFACE_LINK_LIBRARIES` 做拓扑排序，
  依赖者在前；经由导出的 interface 目标（`EXReader::exr_core`）间接到达的依赖同样展开，不会被
  丢掉。私有归档按 `EXReaderDependencies.cmake` 的声明顺序（上游即按依赖先声明）。
- **内存归属**：pkg-config 查询是一次性进程，字符串随进程退出释放；SDK 侧内存归属仍是
  `include/exr/*.h` 已冻结的借用/拥有规则，本包不改动。消费者显式调用
  `exr_document_free`/`exr_layout_free`/`exr_font_free`/`exr_bitmap_free`。
- **线程/重入**：候选构建、去重、封包均为单线程一次性步骤；SDK 线程规则未变，消费者只在主线程调用。
- **错误**：`stage.py`/`transform.py`/`audit.py`/`seal.py` 以非零退出（stage.json 仍保留 `problems`），
  审计把每条判据写进具名 `checks`；`release_ready` 只在没有失败判据时为真。
- **取消**：无长驻服务；工作流超时（150/45 分钟）即整体取消，已上传工件保留。
- **提交边界**：候选只写入 `build/`，从不写源码树；封包只读候选树，输出目录已存在即拒绝。
- **平台归属**：候选只对自己实际构建的 runner 成立。`stage.py` 要求 `linux` 只能来自
  `RUNNER_OS=Linux`/`RUNNER_ARCH=X64`、`macos` 只能来自 `macOS`/`ARM64`，`aggregate.py`
  再按同样三元组复核，标错平台的候选直接被拒。
- **硬上限**：文本扫描单文件 ≤4 MiB；`walk` 拒绝符号链接与越界/绝对成员名；归档只允许一个根目录；
  硬链接组必须指向已存在的同根成员；重复规划只接受字节与权限位都相同的材料。

## 复核轮（`codex/reader-distribution-unix-review`）修复的缺陷

原交付（run 40130016878）的两平台构建、搬迁、去重、封包、解包与消费者都真实跑通，但复核对实现
本身发现下列具体缺陷，均在本包白名单内修复：

1. `exreader.pc` 的 `Cflags` 缺少安装包导出的编译定义，pkg-config 消费者拿到与 CMake 消费者
   不同的编译接口。现在 `Cflags` 逐字携带 `-DEXR_STATIC`，并由 `pkg-config --cflags` 与契约
   校验双向复核。
2. 公共 pkg-config 单元此前只被当作**文本**校验，从未真正用来构建任何程序。现在用
   `cc + pkg-config --cflags/--libs --static` 单独编译**同一个公开 C 消费者源码**，在搬动后的
   前缀与解包后的树上各跑一次真实阅读（打开 `layout.epub`、排版、渲染、写 PNG），并要求与
   CMake 构建的同一程序输出逐项相等、渲染 PNG 摘要相同。
3. 权限位只被记录、从未被复核：去重会把字节相同但可执行位不同的副本链成同 inode，从而静默改掉
   权限；封包清单也不记录硬链接成员的模式。现在规划阶段拒绝跨模式去重、清单记录每个成员的
   模式、解包后逐项比对，`audit` 增列具名判据 `executable_modes`。
4. 归档清单里 `identity`、`stage_sha256`、`dedupe_sha256`、重复节省字节、根目录名与成员权限位
   都被写入但从未被读回校验；同源代码汇总从未检查 `runner_os`/`architecture`，也从未打开过
   protocol 工件的内容。现在 `aggregate.py` 逐项重算：清单必须属于本次上传的 `stage.json` 与
   `dedupe.json` 字节、identity 必须绑定同一 source/run/attempt/平台/ABI/pkg-config 摘要，
   protocol 日志必须逐条列出具名用例且汇总计数与实际行数一致、失败数为 0。
5. `check_scope.sh` 只对部分文件做 `py_compile`（不含同源汇总工具）；现在编译本包全部
   `*.py`，语法错误在建两台机器之前就失败。
6. `seal.py` 的 `gzip.GzipFile` 未显式声明写模式，会向 protocol 日志插入两行 `FutureWarning`；
   已显式声明 `mode='wb'`（与当前默认行为逐字节一致）。

复核轮新增协议判据 5 条（`link-order-through-interface`、`stage-refuses-foreign-runner`、
`compile-definitions`、`dedupe-plan-keeps-modes`、`seal-records-modes`），`selfcheck` 从 11 条
增至 16 条；`audit` 从 13 条增至 14 条。

## 云端验收矩阵（命名结果）

- 守卫：`check_scope.sh`（HEAD==GITHUB_SHA、起点为祖先、冻结 SDK 树相等、产品 schema 相等、
  改动全在白名单、本包全部 python 文件可编译）。
- 协议：`selfcheck.py` 在合成夹具上跑 16 条判据（链接顺序、interface 目标穿透、私有归档顺序、
  pkg-config 往返、编译定义一致性、私有 pkg-config 绝对 prefix 识别、绝对 prefix/绝对库路径拒绝、
  组件覆盖、去重规划、权限位感知去重、树扫描、路径安全、封包/解包硬链接、权限位记录与篡改拒绝、
  runner/架构错配拒绝）。
- 两平台（ubuntu-22.04、macos-15）：真实构建安装（外部参数，608 个构建目标）→ 许可材料 →
  候选 → 搬迁 → C/C++ 消费者与九格式 smoke → **pkg-config 单独构建的 C 消费者** → `audit before`
  → 去重 → 重建重跑 → `audit after` → 前后一致 → 封包 → 解包校验 → 从解包树再建再跑（含
  pkg-config 消费者）→ `audit extracted` → 解包与去重后一致。
- 汇总：`aggregate.py` 用 `gh api` 读回 run/attempt/jobs/artifacts，重算 ZIP 摘要，解包归档，
  重算逐文件身份与权限位，读回 protocol 日志，并从上传字节再跑一次静态审计；任一缺项、跨源码、
  跨 attempt、跨 runner、摘要或身份不符即拒绝。

## 范围与未覆盖

授予范围仅限 Linux/x64 与 macOS/ARM64 的 `reading-core` 候选：可重定位安装、pkg-config 契约
（含编译定义与静态链接可用性）、重复材料去重与解包往返、安装后 C/C++/pkg-config 消费者与九格式
smoke 的真实行为。

不授予：Windows 分发、`reading-library`/可选组件 profile、性能/无障碍/真机/音频范围、
产品宿主接线（由 root 统一完成）、任何 tag/Release/正式签名或公证。候选不含可运行阅读器
（`EXR_BUILD_TOOLS=OFF`、`EXR_ENABLE_AUDIO=OFF`、消费者 CMake 拒绝 `audio`/`textindex`/
`library`/`pdf_edit` 目标），不声称任何朗读/音频/签名产物。

## 复现

~~~bash
git push origin codex/reader-distribution-unix-review
gh run list --workflow=reader-distribution-unix.yml --branch codex/reader-distribution-unix-review --limit 1
~~~

受测源码、run/attempt、工件 ID/字节/digest/有效期与逐项结果记录在
[validation/reader-distribution-unix.json](validation/reader-distribution-unix.json)。

## 本轮结果（2026-10-25，复核分支 run 40169400495 attempt 1）

受测源码 `8975fa6c0ed21b9357b80394a9474491adb8dc1e`（review 分支），四作业全部成功：
`rejection protocol`（16/16 协议判据）、`unix (linux)`、`unix (macos)`、
`same-source report`（accepted=true、problems=[]）。

| 平台 | runner | 安装文件/字节 | pkg-config SHA-256 | 去重 | 归档字节 | 归档 SHA-256 |
| --- | --- | --- | --- | --- | ---: | --- |
| Linux | Linux/X64 | 257 / 18,540,403 | `65416246…` | 4 组 / 46,583 B | 6,426,212 | `8ac844d7…` |
| macOS | macOS/ARM64 | 257 / 14,858,515 | `0755d45c…` | 4 组 / 46,583 B | 5,661,567 | `f15a3c4a…` |

- 搬迁目标：`…/build/relocated-prefix/reading-core-sdk-relocated-to-another-directory`
  （Linux `/home/runner/work/EXReader/EXReader/…`，macOS `/Users/runner/work/EXReader/EXReader/…`），
  与安装路径 `build/install-a` 既不同长也不同前缀。
- 上游私有 pkg-config 单元（libwebp/aom/sharpyuv 系列）逐条记录路径/字节/SHA-256/原 prefix，全部
  经判定为绝对 prefix 后才移除；若某个上游单元本就可重定位，`stage.py` 现在改为直接拒绝候选。
- `pkg-config --cflags` 输出 `-DEXR_STATIC -I<prefix>/lib/pkgconfig/../../include`（`-DEXR_STATIC`
  来自安装包导出的 `INTERFACE_COMPILE_DEFINITIONS`）；
  `--libs --static` 输出 8 个组件归档、13 个私有归档与 `-pthread -lm`（macOS 无 `-ldl`）。
- 用该输出单独 `cc` 链接同一 C 消费者源码：`layout.epub` 1 页、291 字节正文、720×1040 RGBA
  → PNG 18,974 字节，与 CMake 构建逐项相等，`rendered_png_sha256_equal=true`（搬动后与解包后
  各一次）。
- 九格式 smoke 在去重前、去重后、解包后均 9/9；三份审计各 14 条判据全部通过（新增
  `executable_modes`）；去重前后与解包前后的 PNG 摘要、逐项计数器与 smoke 结果完全一致。

工件（均同 run/attempt，Actions API 读回，Actions 内下载并重算）：

| 工件 | ID | 字节 | digest | 有效期 |
| --- | ---: | ---: | --- | --- |
| linux | 12590111026 | 6,553,688 | `sha256:e8be5b50…` | 2027-01-23T06:31:43Z |
| macos | 12589797947 | 5,780,029 | `sha256:82c3266f…` | 2027-01-23T06:31:43Z |
| protocol | 12589727804 | 365 | `sha256:d007f871…` | 2027-01-23T06:31:43Z |
| report | 12589623138 | 24,623,181 | `sha256:c8ebd7f3…` | 2027-01-23T06:31:43Z |

## 保留的历史

- 原交付 run 40130016878 attempt 1（源码 `2f5677f1…`）此前以 11 条协议判据、13 条审计判据
  通过；本轮复核在其基础上发现并修复上节 6 项缺陷，未删除其记录。
- 原交付的 7 次失败 run 原样保留在验证 JSON 的 `failures_preserved`。
- 复核轮自身的 2 次失败也原样保留：run 40168866092（`audit` 的权限位循环变量遮蔽了内部判据
  记录函数，两平台在 `audit before` 处 TypeError）、run 40169161316（两平台与协议全绿，
  同源汇总因“归档根目录名与上传成员路径比较”和 protocol 日志里的两行 `FutureWarning` 拒绝），
  未用旧绿拼新源码。
- 证据文档之后仅剩 `[skip ci]` 文档提交：受测 SHA 与最终 HEAD 之间没有源码/测试/工作流差异。
