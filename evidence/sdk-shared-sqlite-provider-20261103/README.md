## CI 准入修复：用户批准第 2/2 次限时构建验证

原失败重分类为 **CI-ADMISSION-001**，归属 **P 包 CI 卫生**，不进入 F07 已知问题清单。
workflow 已显式设置 `fetch-depth: 0`；本地普通浅克隆补齐历史后 `git cat-file -e 95100501` 成功。
单独卫生项、P 复用说明和原始先验日志见 [CI-ADMISSION-001](ci-hygiene-CI-ADMISSION-001/review.md)。

**C++17 仅测试目标需要，对外契约未变，SDK 消费者不需要 C++17。**

本次仅 Apple build-only 验证：macOS-14、单作业、20 分钟、不自动重试；结果另记，原始历史保留如下。

## 最新状态：限时构建验证红，转已知问题

候选 `64e514ae396ee73d37c72d732c21e99d1dc3b816` 已提交并推送。
[Run 41706981519](https://github.com/NoGod3524/EXReader/actions/runs/41706981519) 在源码准入阶段失败：`fatal: bad object 95100501…`。
原因是 checkout 仅取得两层历史，漏取 SDK 基线对象。已记为 **CI-ADMISSION-001**，不重跑、不再申请下一轮。
本次为“限时构建验证”，构建配置失败，非行为失败；没有执行构建或测试，不计入共享 provider / Apple 验收。
本次没有生成工件；已保留完整日志和元数据，见 [复核记录](ci-41706981519/review.md)。

C++17 定性与逐文件受保护路径标记见 [前置核对](limited-build-preflight/review.md)：新增要求仅测试目标需要，安装后消费者 C++98 编译、链接、执行成功；四个受保护文件均标为“进入 R 候选”。
**两项仍待 CI**。构建项未关闭，catalog 未改。以下为原始历史记录。

## 首次 Apple CI 的实际结果（2026-11-03）

候选 `40ac811b0a872587641e01ff0cfc33a376e93abc` 已提交并推送。
[run 41705105811](https://github.com/NoGod3524/EXReader/actions/runs/41705105811)，attempt 1，失败于 ProductCatalog C++ 测试编译。
首次失败分类为“构建配置失败，非行为失败”，不计入共享 provider 验收。
公开 provider 的 FTS5 测试 1/1 通过；两个原产品测试、联合 FTS5 和真实内嵌负例均未执行。
**两项仍待 CI**。已授权的一次额度已用完，没有重跑。

复核、原始日志、JUnit、工件来源/哈希、部分符号表与 stage 扫描见 [ci-41705105811/review.md](ci-41705105811/review.md)。
本地已补测试目标的 C++17 声明，显式 C++98 默认下验证目标以 C++17 编译通过；后续修复尚未提交或推送。
以下 Windows 结果和首次运行前的方案保留其原有范围。

# SDK 共享 SQLite 核心契约：候选与证据

本包按用户确认的契约实施：**整个应用的 SDK／产品映像共用一个 SQLite 实现**。
它是 SDK 核心契约工作，不作为 F07 的产品回归修复，不改 catalog 的 state。
当前只有本地证据；`acceptance_assessed=false`，尚未验收。

## 触发证据与归属

- 已实证的静态事实：原 `ec11cf86` 产品构建的 Apple 主程序和 SDK dylib 各有 288 个 SQLite 定义、277 个导出；SDK vendor archive 有 FTS5，产品 archive 的构建配置没有 FTS5。
- **未发现实证运行回归。** 符号绑定冲突、两份实现的生命周期问题属于推测风险，不挂 F07 名下。
- 实施依据是用户确认的 SDK 共享核心契约。双定义事实说明旧构建不满足这个新契约，不能将它写成已观测产品故障。
- 原始取证来自 run `41306566948` attempt 1、macOS peer artifact `13083986989` 及 SDK build artifact `13083581922`；触发摘录与输入 hash 见 `trigger-apple-static.txt`。

## 落点与重放

| 项目 | 当前事实 |
|---|---|
| 最初实现/本地验证基线 | `ec11cf862ca3b44483d7e8c4726ae748ab438337`，SDK 3.42.0；仅保留为早期诊断记录 |
| 本次 SDK 落点 | `95100501eeef9c6325be8b3882aa400c99cf000f`，SDK **3.41.0** |
| 独立候选分支 | `codex/sdk-shared-sqlite-provider-20261103` |
| 重放状态 | 已重放；公共 provider、SDK 导出、ProductCatalog、Apple 链接及检查器已适配到 SDK 线，并重新构建取证 |
| 历史差异 | `git rev-list --left-right --count 95100501...ec11cf86` = **97 / 239**；共同祖先 `f34a4f27161061d08ecc40f5cebfb6f5018aa77f` |
| 未带入的 ec11 内容 | `src/library.c` 的 3.42 迁移改动、SDK 3.42 版本/header 改动、该分支专属 `tests/apple_sdk342_host/build.py` |
| catalog | 未改；HEAD blob 仍为 `a651be85af940dfa35d633e44d39cdda5e63e4b5` |

没有把两条分叉历史整体合并，也没有直接搬运 ec11 的 SDK 二进制。
本包 `sdk-configure.log`、`sdk-build.log`、安装日志和 `windows-local.json` 均来自重放后的 3.41 候选。
第三方源码缓存沿用已核对固定上游 ZIP hash 的缓存；SDK 与产品对象在新工作树重新编译。

## 四项验收证据的当前状态

### 1. 符号表与唯一实现

原始 `*-nm.stdout.txt`、`*-coff.stdout.txt` 全部保留。当前 Windows 本地结果：

| 映像 | 原始 sqlite3_ 定义记录 | 已逐条反汇编确认的 IAT 跳板 | 实现定义 | SQLite 导出 |
|---|---:|---:|---:|---:|
| 公开 provider DLL | 288 | 0 | **288** | **288** |
| SDK DLL | 38（T） | 38 | **0** | **0** |
| 联合消费者 | 21（T） | 21 | **0** | **0** |

实现定义只在 provider 出现。SDK/消费者的原始 T 记录没有删除或剥离：
`sdk-sqlite-thunks.stdout.txt` 和 `consumer-sqlite-thunks.stdout.txt` 逐项证明它们是
跳转到对应 `__imp_sqlite3_*` 的导入跳板，导入描述符全部选择同一 `libreader_sqlite3.dll`。
导入库 `.dll.a` 不作为第二个实现；它和 DLL 都在 stage 扫描中列出。
这是 Windows 本地实现归属证据，不能代替 Apple/其他产品映像的验收。

### 2. FTS5 测试名与数量

两项都在重放后的 SDK 线上实际执行，标签为 `FTS5;SDKContract`：

| 测试 | 结果 | 原始证据 |
|---|---|---|
| `sqlite-provider-check` | **1/1 passed** | `fts5-provider.log`、`fts5-provider.xml` |
| `shared-sqlite-sdk-product` | **1/1 passed** | `fts5-integration.log`、`fts5-integration.xml` |
| 合计 | **2/2 passed** | 不是断言条数，也不是完整产品测试总数 |

前者实际创建/查询 FTS5 表，并核对所需编译选项；后者同时使用安装后的 SDK、ProductCatalog
和公开 SQLite，关闭 SDK/产品连接后继续查询 FTS5，并核对实际 DLL 入口与 SDK header/runtime 版本。
本地 SDK 配置包含 library/textindex，关闭 PDF/audio/可选图像编解码器；未冒充完整六端产品回归。

原产品测试 `product-originals`、`native-product-catalog` 保留 Actions 环境要求，未伪装环境、未改断言。

**两项仍待 CI**

### 3. stage 的 sqlite 文件扫描

完整路径、字节数和 SHA-256 输出在 `stage-sqlite-scan.txt`，对应 `build/sdk-stage`。
目前 14 个条目：一个实现 DLL、一个导入库，其他为公开头、CMake 配置、元数据和许可证。
没有 `libreader_catalog_sqlite.a` 或 `libexr_vendor_exr_sqlite.a` 实现副本。
完整文件清单在 `windows-local.json` 的 `stage_scan`，不只搜索外层包。

### 4. Apple 检查器的故意内嵌负例

- `apple-checker-local.log`：本地直接调用检查器，用符号/依赖表结构控制；其中
  `main_embedded` 必须报 `main embeds a second SQLite implementation`，
  `sdk_embedded` 必须报 `sdk embeds a second SQLite implementation`。共 1 个正例、6 个负例。
- 这不是实际 Mach-O 负例。`extras/sqlite-provider/apple-negative/` 已准备真实 native 控制：
  从与 provider 相同、hash 相等的完整 `sqlite3.c` 编译一个对象，再分别故意内嵌到主程序和 SDK dylib。
  `check.py` 必须捕获上述精确错误；因缺依赖等其他原因失败不算该负例通过。
- 真实 Apple 二进制负例在首次 CI 中因前序编译失败而跳过。workflow `sdk-shared-sqlite-contract.yml` 已准备，
  首次仅由指定候选分支新增该 workflow 文件的 push 触发；拟一次 `macos-14` 作业、上限 20 分钟，
  首次已获授权并执行；该次额度已用完，后续已获一次有条件的“限时构建验证”授权，前置核对见 `limited-build-preflight/review.md`。
  它也会执行上面仍待 CI 的两个原产品测试，保留 JUnit、原始符号、MAP、stage 与失败输出。
  首次注册采用受限分支 push，后续才有手动入口；这与 [GitHub 的 workflow_dispatch 规则](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch)一致。
  当前所有 push 规则已按候选分支和变更路径核对，只有该 SDK 作业匹配，记录在 `push-trigger-audit.json`。

## 当前实现与复验入口

公开包在 `extras/sqlite-provider/`，导出 `EXReaderSQLiteProvider::sqlite3`。
SDK 与 ProductCatalog 显式启用 `EXR_USE_SHARED_SQLITE_PROVIDER=ON` 后引用该目标，
不再各编一份 SQLite；动态 SDK、公有接口与 SDK 私有边界保留。
共享配置包含所需 FTS5、THREADSAFE、DQS、FOREIGN_KEYS、OMIT_LOAD_EXTENSION 与 MAX_LENGTH。
旧 profile 保留，新的联合检查要求 SDK 与产品同时声明共享 profile。

Windows 证据可由 `collect_windows_local.py --llvm-bin <同版 LLVM 工具目录>` 重读当前本地构建产物。
Apple 结构负例：`python tools/check_apple_product.py --self-test-shared`。
workflow 已执行一次并在 ProductCatalog C++ 测试编译阶段失败；真实 Apple 控制未执行。

本地通过不等于验收通过。已提交并推送候选 `40ac811b`，首次 CI 失败；本地后续修复未提交、未推送。catalog 未修改。
