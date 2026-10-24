# Windows 无构建路径的分发准备（J25）

本页记录 `codex/reader-distribution-windows` 分支上 Windows 归档分发准备的实际实现、公开契约、硬上限、复现方式与未覆盖范围。固定实现起点 `f43baf9182d75907c0cb5d6f77048f27bca8c950`，SDK 冻结 `9854061be331fe603a1822d9b2b36ee357154927`（3.40.0 / ABI 1）。本包不改 `src/`、`include/`、`cmake/`、顶层 `CMakeLists.txt`、`tests/fixtures/`、`bindings/`、原生与可靠性工作流，也不改产品 schema1 与既有 wire/anchor；只新增 `tools/reader_distribution_windows/**`、`tests/reader_distribution_windows/**`、本工作流、本文件与 `docs/validation/reader-distribution-windows.json`。

## 目标

Windows 归档里不应存在构建机路径（runner 工作区、自托管 runner、工具缓存、构建用户主目录）。本包做三件事，且三件事分别可验证：

1. **追查**：扫描安装前缀与归档的每一个文件，把路径命中分到文本面或二进制面，并把 COFF/PE 容器事实（归档成员名、`.debug$*` 段、`.drective` 绝对指令、PE 导入名）逐条记录。
2. **消除**：文本面用可逆、幂等的重写收敛为 `<path:键>` 占位符并留审计；二进制面永不改写字节——有泄漏就如实阻断发布，交回具体面。
3. **可重定位消费**：把归档解包到工作区之外的另一个绝对路径，只用解包出来的前缀编译并运行 C、C++ 消费者与原生 probe，跑原九格式 smoke，核导入闭包与导出 vendor 闭包。

## 外置参数与三个面的证明

冻结的 Release 预算不变（`cmake --preset reading-core`），因此发行构建没有 `/Zi`、源码不使用 `__FILE__`、没有 `#pragma comment(lib, ...)`。这条结论不能靠推断，工作流用同一份控制源在不同外置参数下真编一次来证明每个面：

| 面 | 控制 A（泄漏） | 控制 B（干净） | 具名结果 |
| --- | --- | --- | --- |
| COFF 调试段 | `cl /c /Z7 <绝对源路径>`，目标文件 `.debug$S` 记录绝对源路径 | `cl /c /Z7 path_surface.c`（cwd 内裸文件名），调试段存在但无构建根 | `coff-debug-control-records-absolute-path`、`coff-debug-relative-spelling-avoids-root` |
| `__FILE__` 宏 | 同一 exe 运行时打印绝对源路径 | 打印 `path_surface.c` | `file-macro-control-is-absolute`、`file-macro-relative-spelling-preserved` |
| 归档成员/指令 | `lib.exe` 用不同子目录的绝对 .obj 归档，成员名仍是 basename；带 `#pragma comment(lib, "<绝对路径>")` 的成员在 `.drective` 里保留绝对路径 | 发行归档里成员名无分隔符、无绝对指令 | `archive-member-names-are-basenames`、`archive-drective-absolute-detected`、`control-surfaces-would-block-shipping` |

结论只按实测写：发行 stage 的扫描结果必须为 0 命中，且 `.debug$*` 段数、绝对 `.drective` 数、带分隔符的成员名数都必须是 0（`no-debug-sections`、`no-absolute-drective`、`archive-member-names-relative`）。扫描器对控制组必须报错，否则“发行组干净”不算证据。

## 工具契约

全部工具只读产物、不联网、不改 SDK 源码；除 `aggregate_artifacts.py`（只在 Actions 里经 `gh` 读本次运行工件）外没有网络访问。

### `scan_paths.py`

- 输入：`--root`（可重复，目录）或 `--zip`（可重复，归档）、`--root-arg`（可重复，必须禁止出现的绝对路径）、`--source-sha`、`--limit`。
- 输出：`reader-distribution-windows-scan-v1` JSON，含每文件 `path/bytes/sha256/kind/text/category/hits`，容器 `kind` 为 `file|archive|pe`，以及 `summary`（files/bytes/text_hits/binary_hits/archives/pe_files/debug_section_count/drective_absolute/member_names_with_separator/accepted）。
- 退出码：`0` 无命中；`2` 有二进制命中（阻断）；`3` 仅 `--require-clean` 时的任意命中。
- 上限：单文件 256 MiB（`--limit` 可调）、单文件命中 4096 条即拒绝继续（不产出无界报告）。
- 线程：单线程确定性遍历，按路径排序。

### `sanitize_stage.py`

- 输入：`--source`（安装 stage）、`--destination`（新目录，必须不存在）、`--scan`（同源扫描报告）、`--text-limit`。
- 行为：复制整树；只对“文本 + 可重写后缀”文件把命中 needle 换成 `<path:键>`；每个文件记录 `sha256_before/after`、`patterns`、`tokens`。写完后重扫目的树，要求文本与二进制残留均为 0。
- 结构证明：`restore(new) == old`（可逆）、`rewrite(new) == new`（幂等）、行数不变；任一不成立即报错。
- 输出：`reader-distribution-windows-sanitize-v1` JSON，`accepted` 仅当无 refused 且残留为 0。
- 退出码：`0` 通过；`2` 存在二进制/不可重写面（阻断）；`3` 重写后仍有残留。
- 上限：树内文件 20000；单文件重写 8 MiB；目的目录已存在或位于源内即拒绝。

### `seal_distribution.py`

- 输入：`--stage`、`--scan`（同源净化后扫描）、`--sanitize`、`--archive-out`、`--report`、`--source-sha`（40 位）、可选 `--epoch`、`--skip-determinism-check`。
- 行为：重新盘点 stage、按类别聚合摘要、独立重扫、用固定时间戳与排序条目封 ZIP；再封第二份到临时目录比对 sha256；最后用 `read_zip` 证明归档内容与 stage 逐文件一致。
- 输出：`reader-distribution-windows-archive-v1` JSON，含 `entries`、`categories`、`archive{name,bytes,sha256,entries,content_digest}`、`stage.digest`、`reproducibility`、`published: false`。
- 拒绝：`sanitize.accepted` 非真、stage 摘要与审计值不一致、封后发现任何命中、归档已存在、类别缺失（header/config/license/library/doc）。

### `verify_distribution.py`

单一出口：把归档、stage、扫描、净化、身份、重定位、九格式 smoke、依赖闭包、probe 与负例绑定到同一 `source_sha` 与同一 `GITHUB_RUN_ID/GITHUB_RUN_ATTEMPT`，重新计算而不采信报告。必需具名结果：`source-identity-bound`、`archive-matches-stage`、`archive-tamper-evident`、`archive-content-scanned-clean`、`stage-scanned-clean`、`headers-config-licenses-hashed`、`sanitization-audited`、`relocation-prefix-distinct`、`relocated-consumers-pass`、`nine-format-smoke-complete`、`installed-identity-matches-headers`、`dependency-closure-system-only`、`probe-prefix-bound`、`no-debug-sections`、`no-absolute-drective`、`archive-member-names-relative`、`deterministic-seal`。缺项、任一项 fail、或负例少于 4 条且未全过，都抛错且不写 `accepted: true`。

### `check_surfaces.py` / `check_dependencies.py`

前者按上表逐面核控制组与发行组；后者解析刚构建的消费者 PE 导入名（不允许路径型导入），并核对 `lib/cmake/EXReader/EXReaderDependencies.cmake` 里声明的静态 vendor 库都在 `lib/exreader/` 里。

### `aggregate_artifacts.py`

只在上传成功的云端运行：`gh api` 读 run 的 `head_sha`、`run_attempt`，要求同名工件恰好一个、未过期、非空、`digest` 为 sha256；下载原始 ZIP 重算摘要；解包后重算内层发行 ZIP 的 sha256 与条目数，核对 `summary.json` 的 `source_sha`、`ci` 与全部具名结果。任一不符即失败。

## 并发、内存与错误

测试里的原生组件不引入新的常驻状态：`relocation_probe.c` 只用 Win32 `GetModuleFileNameW/EnumProcessModules/GetModuleFileNameExW` 与已安装的公开 C ABI，进程内单线程，缓冲区为固定栈数组（4 KiB 路径、256 模块），无堆分配、无回调、无取消语义——一次执行、一次退出码（0 通过 / 1 面不符 / 2 参数错 / 3 取自身路径失败）。`consumer.c` 与 `consumer.cpp` 同样一次执行：字体与出版物的所有权归 SDK（`exr_font_free`、`exr_publication_free`、`exr_document_free`、`exr_pager_free`、`exr_layout_free`、`exr_bitmap_free`），消费者不释放 SDK 内部对象；渲染页数硬上限 3 页，版面 720×1040，无后台线程。

## 复现

全部步骤只在 GitHub Actions 里执行（本地只做源码/文档/Git）：

    python tools/reader_distribution_windows/scan_paths.py --root <stage> --root-arg <workspace> --output scan.json
    python tools/reader_distribution_windows/sanitize_stage.py --source <stage> --destination <copy> --scan scan.json --output sanitize.json
    python tools/reader_distribution_windows/scan_paths.py --root <copy> --root-arg <workspace> --require-clean --output scan-clean.json
    python tools/reader_distribution_windows/seal_distribution.py --stage <copy> --scan scan-clean.json --sanitize sanitize.json --archive-out dist.zip --report distribution.json --source-sha <sha>

工作流 `.github/workflows/reader-distribution-windows.yml`：`protocol`（守卫 + 合成正反例）、`windows`（windows-2022、真实 MSVC/Ninja、安装、扫描、净化、封装、控制面、解包重定位、消费者、九格式 smoke、依赖、负例、具名门）、`aggregate`（下载并用 `gh` 重算同次工件）。守卫在 `protocol` 与 `windows` 都跑：`HEAD == GITHUB_SHA`、固定起点为祖先、SDK 保护树与起点相等、产品 SQL 与起点相等、`git diff --name-only <start> HEAD` 全在白名单内。

## 硬上限

| 项 | 值 |
| --- | --- |
| 单文件扫描 | 256 MiB |
| 单文件命中 | 4096 条 |
| 可重写文本文件 | 8 MiB |
| 树内文件数 | 20000 |
| 归档解包总量 | 1 GiB |
| 归档条目 | 20000 |
| 封装时间戳 | 2000-01-01T00:00:00Z（`--epoch` 可改） |
| 消费者渲染页数 | 3 |

## 未覆盖与边界

- 本包不给 Windows 生产宿主接线；root 负责宿主接线与共同源码复验。
- 只准备 `reading-core` 发行形态；`reading-library`、共享兼容 DLL、音频/文本索引组件不在本包范围。
- 不做正式签名、tag、Release、PR 合并；归档标记 `published: false`。
- 二进制面若出现构建机路径，本包不改字节、也不“擦 JSON 清单”，而是阻断并交回具体段与成员，交 root 决定编译参数或源码面修正。
- 本地只写源码/文档/Git；任何构建、扫描、夹具生成、smoke、benchmark、工件下载都在 Actions。
