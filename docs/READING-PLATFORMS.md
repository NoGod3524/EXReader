# 原生阅读 preset：Windows/macOS 构建验证（H1）与证据门禁（H6）

## H6：收紧后的跨平台证据门禁

分支 `handoff/reading-h6-platform-gate`，自 H1 文档 HEAD `2e8e981b6dd44d855a23931480fe5e0d5c791762` 新建。
只改 `tools/reading_platform_evidence.py`、`.github/workflows/reading-platforms.yml`、本文，
新增 `tests/check_reading_platform_evidence.py`；未改 Linux 门禁、消费者 CMake、SDK、preset 或 H2 概述文档。

### 受测源码与结果：4/4 作业成功，含 25/26 项拒绝回归

受测源码 `1c06a0e5ae99bf8213521494e4b283a9e93972ee`，
run [39859122761](https://github.com/NoGod3524/EXReader/actions/runs/39859122761)，push 触发。
结果来自 GitHub 作业日志与工件元数据，未下载工件、未在本地执行任何测试。

| 平台 | profile | attempt | job | ctest | 九格式 smoke | 程序执行 | 门禁 | 拒绝回归 |
| --- | --- | ---: | --- | ---: | ---: | ---: | --- | ---: |
| Windows | reading-core | 1 | 120104936641 | 3/3 | 9/9 | 5/5 | accepted | 25/25 |
| Windows | reading-library | 2 | 120106623146 | 4/4 | 9/9 | 6/6 | accepted | 26/26 |
| macOS | reading-core | 1 | 120104936412 | 3/3 | 9/9 | 5/5 | accepted | 25/25 |
| macOS | reading-library | 1 | 120104936068 | 4/4 | 9/9 | 6/6 | accepted | 26/26 |

失败保留：Windows reading-library attempt 1（job 120104936355）在 `cmake --preset` 阶段失败，
原因是 FetchContent 从 `https://www.sqlite.org/2026/sqlite-amalgamation-3540000.zip` 下载时出错
（“Failure when receiving data from the peer”），尚未进入门禁；只重跑这个失败作业，源码不变，attempt 2 成功。
attempt 1 的工件 `…-39859122761-1`（id 12461530642，9237 字节）只含日志。

同一分支上更早的两次 run 不作为结论，只记作开发过程：
- `39857949179`（源码 `86df54f…`）4/4 失败。Windows 门禁拒绝：linker banner 14.44.35229 与目录版本
  VCToolsVersion 14.44.35207 不一致，检查写错了。macOS 回归中 `benchmark-not-executed`
  用例多要求了一个不会出现的代码。两处都在 `862be39…` 修正。
- `39858465869`（源码 `862be39…`）4/4 成功；随后 `1c06a0e…` 只把逐程序和工具链证据另打到作业日志，
  所以以 `1c06a0e…` 的 run 为准。

### 门禁现在判定什么

`verify` 子命令拒绝以下情况（问题代码见报告 `problems`）：

1. **精确程序集合**：程序名按当前消费者 CMake 冻结，路径相对 `build/reading-consumer`。
   - reading-core：`reading-document`、`reading-benchmark`、`components/core-consumer`、
     `components/chapter-consumer`、`components/convert-consumer`
   - reading-library：上述五个再加 `components/library-consumer`

   空集合、缺少、重复（含不同写法指向同一文件）、未知项、未知 profile 都拒绝。
   workflow 不再跳过不存在的程序，按 profile 原样传入完整列表。
2. **产物身份**：仅文件存在不够。还要求它是本平台原生可执行文件（PE x64 / Mach-O arm64 且类型为 executable），
   并且是消费者 `build.ninja` 中 `*_EXECUTABLE_LINKER*` 规则的输出；编译源码从 Ninja 图反推，记录仓库内路径和 SHA-256。
3. **依赖观测与实际执行分开记录**：
   - `dumpbin /dependents` 只记作“名称观测”（`resolution: names only`），不判定 DLL 能否解析。
   - 工具不存在、退出码非 0、输出中没有依赖段或依赖为空，都拒绝。Windows 还要求 dumpbin 位于 `VCToolsInstallDir`。
   - macOS 保留 `otool -L` 非系统路径存在性检查。
   - 每个程序都必须有一条成功执行记录，并且执行时的散列与检查时一致，否则 `not-executed`：
     - ctest：`--show-only=json-v1` 给出命令路径，JUnit 给出结果，执行前快照提供散列。
     - smoke：`summary.json` 中的 identities。
     - 直接运行记录。
   - 只有全部程序都通过执行记录，`loader_conclusion` 才写“均由 OS loader 启动并成功退出”；否则写“未确立”。
4. **基准程序的安全实际调用**：H1 中 `reading-benchmark` 从未执行。现在用现有程序在已有 fixture 上真实跑一次：
   `reading-benchmark tests/fixtures/table-fragments-12.epub tests/fixtures/fonts/primary.ttf --max-pages 1`，
   记录退出码、前后散列与 stdout 散列（`benchmark-run.json`）。仅作加载与运行证据，不作性能结论。
5. **CMake 实际选用的工具链**（SDK 与消费者两个构建树）：
   - 来源：`CMakeCache.txt` 的 `CMAKE_{C,CXX}_COMPILER/LINKER/AR`、
     `CMake{C,CXX}Compiler.cmake` 的编译器与 `COMPILER_LINKER{,_ID,_VERSION}`、`rules.ninja` 的链接命令原文；
     每个链接器按解析后的真实路径实际探测一次版本。
   - Windows 要求：编译器为 MSVC x64；编译器、链接器、lib 都位于 `VCToolsInstallDir\bin\Hostx64\x64`；
     cl 和 link 的 major.minor 与 VCToolsVersion 一致；link banner 的 build 号与 cl 相同。
   - PATH 上所有 `link.exe` 按顺序列为观测，不据此推断，也不作判定。
   - macOS 要求编译器为 AppleClang，`ld -v` 能给出版本。
6. **平台与来源**：`--platform` 必须同时匹配主机和 `RUNNER_OS`；checkout HEAD 必须等于 `GITHUB_SHA`；
   preset 缓存变量逐项比对。

### 拒绝回归（云端，每作业一次）

`tests/check_reading_platform_evidence.py` 读取同一作业已接受报告中的 `invocation`，先原样重放一次作为正对照（必须 accepted 且无问题），
再每次只改一个输入，要求报告被拒且包含指定问题代码。用例如下：
- 逐一缺少每个必需程序
- 空集合
- 重复（同一路径、绝对路径写法）
- 未知程序
- 错误 profile、未知 profile
- 错误平台、不支持的平台
- 依赖工具失败（PATH 首位放置退出码 3 的替身）
- 依赖输出为空、输出不可识别
- 分别去掉 ctest JUnit、ctest 列表、smoke 汇总、执行前快照
- 基准程序未执行
- 非原生文件冒充程序、程序不在 Ninja 图中

另有一项独立核对：报告中的程序集合必须等于 `ninja -t targets all` 列出的全部可执行链接输出。
这一项由 Ninja 自己给出，不经过门禁的解析器。四作业中 core 25 项、library 26 项全部通过，
结果在工件 `rejection-regression.json`。

### 逐程序执行与散列（run 39859122761）

来源散列在四作业中一致：

| 程序 | 源码 | SHA-256 |
| --- | --- | --- |
| reading-document | `tools/check_document.c` | `70b5adacf285321ed18c5c52f51864939205bafe61a5fd3cc89b0402ec9ecd1b` |
| reading-benchmark | `tools/benchmark.c` | `ede3d88f5b6235549b5290406d7e31fd0e1f69d0ca94eb1cbf3d5663f9ea1145` |
| core-consumer | `tests/test_core_component.c` | `7e9f4cbdf23b7addedf9af67d1c2b6904f4af30d35f96330fed9c001aa257d03` |
| chapter-consumer | `examples/window.c` | `8ddf53337a7b3f6ce9a22378626d6ea28c4d8548e3840b73ef36dbf81c88f00e` |
| convert-consumer | `tests/test_convert_component.c` | `0041329f848dbd50a98d7500af6bf33e00bd7c168e87b3052a738a58eb34838a` |
| library-consumer | `tests/test_library_component.c` | `c821e670b40662f767a863118ce0f6b5af8b08a188d898bc6ab6c45a7a4eed4a` |

执行方式：
- reading-document：九格式 smoke（`passed` 9/9）
- reading-benchmark：直接运行一次，退出码 0
- core / chapter / convert / library consumer：ctest `installed-core` / `installed-chapter` / `installed-convert` / `installed-library`，均 passed

各作业程序二进制 SHA-256：

| 程序 | Windows core | Windows library | macOS core | macOS library |
| --- | --- | --- | --- | --- |
| reading-document | `dfcac5df6f2e47e7134c00f92d815572438abd5ebdd82f44f0cae463e1333f6d` | `d20fe5145da58d0f37cf20931dd438adb14c4af08199d2bad99de0a9bb61526d` | `6ffd997f74a3b8530987886106c0af0ea6f34d3e77917dbfe498331c7f419bf8` | `5b6a460f1dcae6d8abf5155bcf5943680691db6868fa1b2ada9ec24a40393408` |
| reading-benchmark | `00a44e67b0de1048ec9526830565a04f0958e48d5d66c5c44aec064a6a3d15d2` | `3fb971247e5cb1ab31d069a42b69aa78b2f9253746a2f9fee8a9757fab5212b4` | `76149139b71e1117c91ce671cef507dbb77bddfdddc5666b0248f37ed97b3cd3` | `d440badb3f0d80e20a68f6c271692e3c1fe8ba18b2dd76229e8728e391d4c1d3` |
| core-consumer | `9e14a5a8947d4454a059e8c62e8131a90449a70436b6a5ba74202de8d48966f7` | `6ae91bfa1029f14f1c196359aa0b97dde92d129fec15fdf775f3343c2fdfd537` | `ca7e42e546fa620c5d1161c8a6e96b3a410b84e86ddf4c483d3e8f0bac36611c` | `cc09eba97eb1be8cde80988f9ac5fc9c0a078ff5f89ac69c35dbb0edc5432b43` |
| chapter-consumer | `8b13318a342711c0e8c76c9b866ba692cca02dcdaa26cce62dbe36f01de9b6fd` | `260016e9ae0cf90fcdc12b6b6edd10dabca2421f7f388d3147271689a6074583` | `d4492581185a504ec82f1cc71ba5d22e45a377ade6240286587b427d98cdbc7d` | `d91a69fdf8177ae720897380d7e2e368b60614160bda097974b9c058540d7e25` |
| convert-consumer | `abb315e223d3ab246dd119b670faec6563552d1eb07eec4ba5f852d0af174140` | `9c21da0cb5fb3467059ba8692086169096716f941d352d5911f663cbe88b74d2` | `0ca8bbd7ac95c53e6dab6b42ca0f7f3eb3d54af6c22bb3f9dc2d12df403e19d7` | `0ca8bbd7ac95c53e6dab6b42ca0f7f3eb3d54af6c22bb3f9dc2d12df403e19d7` |
| library-consumer | — | `f15b200e1f9787b630784ba0311a44270079f97bf1f067921445ff929a436089` | — | `4fafda4fb99704941999336861acfdc8ad297cb2d6ec4259008a91b9e4bc03cc` |

原始依赖输出已嵌入报告，也打印在 verify 步骤日志中，摘要如下：
- Windows `dumpbin /dependents`：reading-document 与 reading-benchmark 为 `SHELL32.dll`、`KERNEL32.dll`，
  其余程序只有 `KERNEL32.dll`。这只是名称观测；“可由 loader 加载”的依据是上表的实际执行。
- macOS `otool -L`：每个程序只有 `/usr/lib/libSystem.B.dylib`。
- 两平台都没有 webview/webkit/chromium/electron/faad/minimp3（core 另查 sqlite）字样。

### CMake 实际选用的工具链（SDK 与消费者构建一致）

| 平台 | 编译器 | 链接器（CMake 记录 → 实测版本） |
| --- | --- | --- |
| Windows | MSVC `cl` 19.44.35229.0 x64，`…/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/cl.exe` | `CMAKE_LINKER` 为同目录 `link.exe`；`CMAKE_C_COMPILER_LINKER` 为同一文件的 8.3 写法（`C:/PROGRA~1/…/1444~1.352/…/link.exe`），ID MSVC，版本 14.44.35229.0；banner `Incremental Linker Version 14.44.35229.0`；`CMAKE_AR` 为同目录 `lib.exe` |
| macOS | AppleClang 17.0.0.17000013 arm64（`/usr/bin/cc`、`/usr/bin/c++`），Xcode 16.4 | `CMAKE_LINKER=/usr/bin/ld`，`CMAKE_C_COMPILER_LINKER=…/Xcode_16.4.app/…/XcodeDefault.xctoolchain/usr/bin/ld`（ID AppleClang，1167.5），两者 `ld -v` 均为 `ld-1167.5`；`clang -print-prog-name=ld` 指向同一 Xcode ld |

MSVC 环境：VCToolsInstallDir 为 `C:\Program Files\Microsoft Visual Studio\2022\Enterprise\VC\Tools\MSVC\14.44.35207\`，
VCToolsVersion 14.44.35207，Windows SDK 10.0.26100.0，`VSCMD_ARG_TGT_ARCH=x64`；dumpbin 位于同一工具目录。
VCToolsVersion 是工具集目录版本，cl/link 的 build 号为 35229，两者不同属正常，门禁只对 major.minor 与 build 号一致性作判定。
PATH 观测中 `C:\Program Files\Git\usr\bin\link.exe` 排在 MSVC `link.exe` 之前，并且出现两次。
CMake 记录并实际使用的是 MSVC 链接器，门禁据 CMake 记录判定，不依据 PATH 顺序。

### 工件（run 39859122761）

| 工件 | ID | 压缩字节 | digest | 到期 |
| --- | --- | ---: | --- | --- |
| reading-platform-Windows-reading-core-39859122761-1 | 12459809769 | 8451920 | `sha256:ef4a5f8b896408d2daa44e56a5533472b4603b1c5631f08a28da11c4bdbb7528` | 2027-01-20 |
| reading-platform-Windows-reading-library-39859122761-2 | 12460394767 | 9666442 | `sha256:0e97e75432394296efc1d66ac219c178fa61fddab652dfb9563044f87e3cda62` | 2027-01-20 |
| reading-platform-macOS-reading-core-39859122761-1 | 12460313103 | 5734782 | `sha256:e6aa249d42ecc4346f94126c190c96f53b2d8eb48f59bfb148fb09abd419f4e1` | 2027-01-20 |
| reading-platform-macOS-reading-library-39859122761-1 | 12460043836 | 6540510 | `sha256:f835b076d78b8108cdcc95340fb9509d5f89a37087da5de5de9661ae67d9b917` | 2027-01-20 |

保留的失败工件：`reading-platform-Windows-reading-library-39859122761-1`，id 12461530642，9237 字节，
`sha256:8c5d474caaa68cc8046e5b0487047ab6a942a4b2c4bf1f68384cdabc1bb7d990`。

每个工件除 H1 已有内容外，新增：
- `program-snapshot.json`（执行前散列）
- `ctest-tests.json`
- `benchmark-run.json`
- schema 2 的 `platform-evidence.json`（逐程序身份/源码/执行/原始依赖输出、两构建树工具链）
- `rejection-regression.json`

### 限制

- 依赖观测之外的“可加载”结论，只覆盖这些程序在本次记录的参数下实际运行的情况，
  不覆盖未走到的代码路径或延迟加载 DLL（报告中记录了是否存在 delay-load 段）。
- 基准程序只跑 1 页采样的一次调用，不产生任何性能数值结论；也没有体积或性能预算。
- 门禁冻结的是当前消费者 CMake 的程序集合；消费者 CMake 改动后，门禁与回归中的 Ninja 独立核对会拒绝，需要同步更新本文件与脚本。
- 本地只读写源码与 Git。开发中有两次例外，需如实说明：
  - 一次本地 `ast.parse` 语法检查，违背了“语法解析在云端执行”的约束；
  - 汇总本文时用本地 Python 解析过 `gh` 取回的作业日志文本（未下载工件）。
  所有构建、测试和门禁判定都只在 GitHub Actions 执行。
- 未设置 required checks、未推默认分支、未合并 PR；`reading-platforms.yml` 现只在本分支 push 或手动触发。

## H1 结果（旧门禁范围，保留原样）

主线 `codex/r1-reading-core` 的 `b529513b7e8e8992786f8c679c0ec6c92110b035` 上新建分支
`claude/reading-h1-platforms`，保留已联合验收祖先 S=`686ce2fe6c3463ef1b917569677ee9933e22faa9`
（工作流首步再次校验）。只新增 `.github/workflows/reading-platforms.yml`、
`tools/reading_platform_evidence.py` 与本文；未改 Linux 工作流、preset、消费者、性能工具、引擎或公开头。

Linux 结果（源码 `54d8c592…`，run `39853356309`）与原失败 run `39852907619` 保持原样，不代替本包平台验收。

**旧门禁范围说明**：以下 4/4 成功表示受测源码 `9b968a1…` 上的平台构建、安装、消费者 ctest 与九格式 smoke 成功。
当时的门禁有几处缺口：
- 程序参数允许为空，workflow 会跳过不存在的程序；
- Windows 的 `unresolved=[]` 是硬编码，不是解析结果；
- `reading-benchmark` 未被执行；
- 链接器没有单独判定。

新门禁不追认旧源码通过，H6 的结论只适用于 `1c06a0e…`。

### 结果：4/4 作业成功

受测源码 `9b968a16fc47596725e849e56ee98e4c4c210b74`，
run [39854485070](https://github.com/NoGod3524/EXReader/actions/runs/39854485070)，attempt 1，push 触发。
结果来自 GitHub 作业日志与工件元数据；未下载工件或在本地执行任何测试。

| 平台 | profile | job | 安装消费者 ctest | 九格式 smoke | 依赖/配置判定（旧门禁） | 安装文件合计（字节） |
| --- | --- | --- | ---: | ---: | --- | ---: |
| Windows | reading-core | 120088990745 | 3/3 | 9/9 | accepted | 23955586 |
| Windows | reading-library | 120088990595 | 4/4 | 9/9 | accepted | 27383744 |
| macOS | reading-core | 120088990657 | 3/3 | 9/9 | accepted | 13781718 |
| macOS | reading-library | 120088990411 | 4/4 | 9/9 | accepted | 15547919 |

ctest 项：`installed-core`、`installed-chapter`、`installed-convert`，library 另加 `installed-library`；
所有导出头的 C++ 编译目标随消费者构建完成。消费者 CMake 判定 core/pdf 存在、音频/PDF 编辑/索引未导出，
且书库组件与 profile 一致。九格式 smoke 为 `check_corpus.py` 整本执行冻结清单
`reading-core-synthetic-smoke-v1`，全部 `passed`、`accepted: true`；它是合成 fixture，不计真实语料。

### 工具链

| 平台 | 镜像 | 编译器 | 其他 |
| --- | --- | --- | --- |
| Windows | `windows-2022`，ImageOS win22 / 20261012.333.1，X64 | MSVC `cl` 19.44.35229（VC Tools 14.44.35207），Windows SDK 10.0.26100.0，VS 2022 Enterprise vcvars64 | CMake 3.31.6，Ninja 1.11.1（pip `ninja==1.11.1.1`），Python 3.12.10 |
| macOS | `macos-15`（15.7.9），ImageOS macos15 / 20260907.0337.1，ARM64 | Xcode 16.4（16F6），Apple clang 17.0.0（clang-1700.0.13.5） | CMake 4.4.3，Ninja 1.11.1，Python 3.12.10 |

Windows 先用 vswhere 定位 vcvars64 并导出环境，`CC=cl`/`CXX=cl`，preset 原样使用 Ninja 生成器。

### 工件

| 工件 | ID | 压缩字节 | digest |
| --- | --- | ---: | --- |
| reading-platform-Windows-reading-core-39854485070-1 | 12458373465 | 8442552 | `sha256:be4e6f7c7abc935c9f1a3c8231c1c59dfabb20c914f2d9099ec7b33dcf28234c` |
| reading-platform-Windows-reading-library-39854485070-1 | 12459196985 | 9656903 | `sha256:08d68fdc5908e53e95816a05241c32a0a20edb78ca6d12852913bd06b151bc0e` |
| reading-platform-macOS-reading-core-39854485070-1 | 12459077056 | 5727637 | `sha256:26ed1646d098853cb9736ca77f8bdb8431134ca2f0c048c5f8dc98df6851914a` |
| reading-platform-macOS-reading-library-39854485070-1 | 12458773358 | 6533197 | `sha256:ad9b0b44dd0553712fa3cdff00863ab542d980f8a5caca140a4e08adf3395225` |

### H1 时的限制（原文）

- 运行依赖检查：拒绝 webview/webkit/chromium/electron/faad/minimp3（core 另拒 sqlite）。
  macOS 还拒绝 `/usr/lib`、`/System/Library` 以外不存在或 `@rpath` 引用；Windows 不另做解析判定。
  静态链接时 sqlite 不会以 DLL 出现，书库组件的有无由消费者 CMake 导出目标检查负责。
- 安装文件合计含头文件、文档、示例与静态归档，不是阅读可执行体积；消费者程序是测试宿主。
- Windows 的 Git bash PATH 中 `C:\Program Files\Git\usr\bin\link.exe` 排在 MSVC `link.exe` 之前；
  H6 已据 CMake 记录确认实际使用 MSVC 链接器（见上）。
