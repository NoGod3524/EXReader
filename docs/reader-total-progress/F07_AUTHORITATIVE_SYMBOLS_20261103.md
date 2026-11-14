# F07 authoritative symbol observations — 2026-11-03

## 续接复核：旧结论更正与尚未闭合项

本节记录 2026-11-03 的本地复核。下文原始四轮 CI 及其报告保留为历史；
旧表中的 Apple 0、weak 已评估和“无 version 段”不能继续作为验收证明。
catalog 在 `95100501eeef9c6325be8b3882aa400c99cf000f` 将 F07 记为 verified 的事实保留，
本次未修改 catalog、提交、推送或启动 CI。完整 F07 尚未得到本次复核证明。

### 原始工件复验

通过 GitHub 连接器取得 run `41674663275` 的 artifact `13248959179`，
ZIP 为 3,098 bytes，SHA-256
`d3227b9eb8caf178b3fdb31f83e32882328d57d95a5c7d366ab7babb807964b6`，
与 GitHub 的 artifact digest 相等。未压缩 `summary.json` 为 25,634 bytes，SHA-256
`5367fce54ba8f835994cd0d43af0067617cc5bec128aa10c9951424c176ccbf2`。

该文件确认工具是 `/usr/bin/llvm-nm-21` 和 `/usr/bin/llvm-readobj-21`，均为 21.1.8。
三个 Apple `--macho-dsymtab` 命令实际均 rc=1，错误提示为 `--macho-dysymtab`；
汇总仍写 `weak_version_assessed=true`。`nm --format=posix -m` 的实际输出格式与旧解析器也不一致。
旧版本段检测把命令字符串逐字符 join，因此不能证明版本段不存在。

### 独立本地工具观测

六个原 peer ZIP 的 run/source/仓库及 GitHub digest 均重新核对，构建收据中的 run/source/attempt
与固定生产轮 `41306566948` / `ec11cf862ca3b44483d7e8c4726ae748ab438337` / 1 一致。
所有程序仅交给符号工具读取，未执行。

本地工具为 Rust 官方分发的同版 LLVM 23.1.1 工具对，独立于原 CI 21.1.8。
工具包来自安装的 Rust manifest 指定 URL，下载包 SHA-256
`6b02bf162f4c29007655f989092949458b0433e61da411ee246b60d602367c39` 与该 manifest 相等；
仅解包工具，未安装或更改系统工具链。

| 输入 | SQLite 观测 | 覆盖限制 |
|---|---|---|
| Windows | 导入/导出中 0 | 无完整本地符号表，不能证明定义/weak 为零 |
| Android `libexreader.so` | 动态定义 277，观测到的 undefined/weak 为 0 | 完整本地符号表被剥离 |
| Android 其余三个 .so | 动态 SQLite 计数 0 | 完整本地符号表被剥离 |
| GTK | 定义 291，undefined/weak 为 0 | 只覆盖该程序，归档归属另列 |
| macOS / iPhone / iPad 主程序 | 各定义 288，undefined/weak 为 0 | linked dylib 不能由主程序计数代替 |

五个 ELF 二进制均实际存在 GNU version 节；观测到的 SQLite 符号名没有 `@` 版本后缀。
“ELF 存在版本节”与“SQLite 符号是否版本化”是两个不同问题，不能再互换。
后续直接解析 `VersionSymbols`：Android `libexreader.so` 的 277 个 SQLite 条目均为索引 1；
其余 Android 库及 GTK 的版本表没有 SQLite 条目。
[LLVM 的 ELF 常量定义](https://github.com/llvm/llvm-project/blob/main/llvm/include/llvm/BinaryFormat/ELF.h)
将索引 0/1 定义为未版本化，隐藏位单独解码；
不能只凭名称没有 `@` 就判定未版本化。解析器现保留 SQLite 的版本索引，并对缺失索引 fail closed。

### Apple 进程闭包尚未闭合

读取同一 producer 的原始构建工件：macOS `13083581922`、iPhone simulator `13083354773`。
两个 ZIP 各含 74 个 `.a`。主程序的 288 个 SQLite 名称同时与
`libreader_catalog_sqlite.a`、SDK 的 `libexr_vendor_exr_sqlite.a` 及 `libexreader.1.dylib` 的定义集相等。
符号集合相等本身不能在这些输入之间唯一定位 provider。

两个 SDK dylib 的实际 SHA-256 分别为：

- macOS：`04797d8b35ae483333efc25514f2e2bdfd8ddef83585429aae801738efa4f2d4`；
- iPhone simulator：`96594670aefc8da7cf98f0df7c14fbc873958ba5c5e4576ec42e0b2a4293cf73`。

这些实际字节与 Apple peer 的 `installed-identity.json` 对应条目相等；iPad 条目与 iPhone 相同。
主程序依赖列表包含 `@rpath/libexreader.1.dylib`，主程序与该 SDK dylib 都各有 288 个 SQLite 定义，
其中各有 274 条 nm 类型 T 记录。尚未证明实际加载路径、二级命名空间绑定及运行时符号解析的完整闭包，
因此不能宣称整个进程只有一个 SQLite 提供者。修复是否涉及生产/SDK，需要所有者确定验收要求和授权。

补读三个主程序及两个不同 SDK dylib 的 Mach-O 导出 trie：每个镜像各有 **277 个 SQLite 导出**，
与 nm 的 274 条 T 加 3 条 S 记录相符，其余定义为本地符号。
这些输入含 `LC_DYLD_CHAINED_FIXUPS`；旧式 bind/lazy-bind/weak-bind 空表不能证明没有绑定。
已另行保存 `llvm-objdump --macho --dyld-info` 的 chained-fixup 结果，五个镜像均未出现
SQLite 的外部绑定条目。三个主程序的 `_dlsym` 明确绑定到 libSystem；这只确定装载函数的归属，
不确定传给 `_dlsym` 的目标。未执行程序，也未将该静态观察当成运行时单 provider 的证明。

### Windows/GTK 包内范围已经核实

原始构建工件 Windows `13082734165`、GTK `13083942264` 的 ZIP digest 与 GitHub 元数据相等。
其中 `program.bin` hash 分别与同轮对应 peer 相等。
已枚举外层包和内层 `EXReader-Windows.zip`、`EXReader-Linux.tar.gz`：
未发现 `.a/.lib/.o/.obj/.map/.rsp`。这次结论覆盖内包；归档 provider 的证明仍缺失。

### 当前修复与验证

修改仅限本工作包脚本、workflow 和本文；回归检查内置于脚本 `--self-test`，未改旧测试。
修复包括：完整 Mach-O 符号表、单一 nm 输出格式、按 Symbol 表边界解析、避免将
`RefType: UndefinedNonLazy` 误判为未定义、按 GNU section 名识别版本节、单列 SQLite 版本后缀、
命令/解析失败与超时 fail closed、输出及 ZIP/APK 字节/数量上限、固定 run/attempt/source/digest 绑定和程序 hash。
PE 或剥离符号表不会被报告为完整 weak 覆盖；非 ELF 的 GNU version 节使用未评估值。

本地自检及六端原 peer 工件复验通过；新 workflow 尚未执行。自检包括摘要错误、source 错误、
POSIX/BSD、Mach-O weak/undefined、PE import/export、版本节正反例、命令失败、超时预算耗尽、输出上限、
坏 ZIP/APK 和主流程失败时不得报告已完整评估。

本地原始证据保存在管理工作区 `.codex/f07-closeout/`，包括连接器返回的 artifact 元数据、原 ZIP、
原 summary、完整命令输出、程序 hash、build 包及其递归清单；不将这些本地文件冒充新 CI artifact。
A4 动态目标数据流、Windows/GTK 归档级归属、Apple linked-image 闭包与正式验收仍未完成。

## SDK 核心契约工作单列

共享 SQLite provider 按用户确认的新 SDK 核心契约独立推进，不作为 F07 的实证运行回归。
潜在绑定或生命周期冲突是推测风险，不计入 F07。进展和验收材料记录在 SDK 候选分支
`codex/sdk-shared-sqlite-provider-20261103` 的 `evidence/sdk-shared-sqlite-provider-20261103/`。
本条 catalog state 未改。

## 授权与范围

用户 2026-11-03 决定：F07 的 A5 采用**方案 b**——一次只读 CI（≤5 分钟）用 CI 预装的 LLVM 工具对
**已验收的**六端程序重新取符号事实。marker `[F07-AUTHORITATIVE-SYMBOLS-ONE-RUN]`。

本作业：

- 读 `run 41306566948` attempt 1 的六个 peer 工件（windows `13083193632`、android `13083881725`、
  gtk `13083892632`、macos `13083986989`、iphone `13084032549`、ipad `13083873210`），
  其 source 为 `ec11cf862ca3b44483d7e8c4726ae748ab438337`；
- 不构建、不安装、不链接、不执行取回的任何字节；Android 的 `program.bin` 是 APK，只取 `lib/<abi>/*.so`（≤64）；
- 总预算 300 秒，单次读取 30 秒；标识符列表封顶 5000 条，超出记 `bounded`；
- 一旦 LLVM 双工具缺失或版本不一致，**在读任何 payload 之前 fail closed**。

## 为什么需要这一轮

2026-11-02 的 `F07 offline sixhost binary evidence`（run `41512362350`）自己写明
`acceptance_assessed=false`、`binary_observations_complete=false`，且 `no_symbols=10`
（windows 与 4 个 Android `.so` 被剥离），Mach-O 的 `object` 表两次 `output_limit_exceeded`。
所以 weak / version / 同口径比较三项从未被权威工具做过，本作业只补这三项。

## 观测口径

| 格式 | 命令 |
|---|---|
| Mach-O | `llvm-readobj --macho-dsymtab`、`--version-info`、`--needed-libs`、`llvm-nm --format=posix -m` |
| ELF | `llvm-readobj --symbols --dyn-syms --version-info --needed-libs`、`llvm-nm --format=posix` |
| PE | `llvm-readobj --coff-imports --coff-exports` |

## 明确不做

- 不做 `dlsym`/`GetProcAddress` 的字面量数据流（summary 固定 `a4_partial=true`）；
- 不给 Windows/GTK 的归档级定义 provider 归属——发布面不含 `.lib/.a/.map`，该项是显式未闭合范围；
- 不主张 F07 通过：summary 固定 `acceptance_assessed=false`，本作业产出观测，不是判定。

## 本地已完成、本作业不重复的部分

- 六端 shipped program：同一 SQLite source-id `2026-10-09 15:46:58 be8d059e…`，每端仅一处；无任何外部 sqlite 依赖；
- Apple 安装 SDK 74 个归档中只有两个定义 `sqlite3_*`，符号集 **288 / 288 完全相同**，两对象字节不同；
- shipped program 与归档定义集**逐个相等（288 = 288，双向差集 0）**。

<!-- dispatch marker [F07-AUTHORITATIVE-SYMBOLS-ONE-RUN] -->

## Runs (all retained; harness defects are not evidence)

| run | attempt | 结论 | 说明 |
|---|---|---|---|
| `41673768227` | 1 | failure | 工具发现缺陷：`ubuntu-22.04` 上既无裸 `llvm-nm`/`llvm-readobj` 也无 `-1x` 后缀；在读任何 payload 前 fail closed。保留 |
| `41674266462` | 1 | success（但不可用） | job 绿，计数全 0：`llvm-readobj` 输出不是 nm 行格式，解析器选错。**不作为证据**，保留 |
| `41674511396` | 1 | success | 加入 readobj 块解析：android `277`、gtk `291` 正确；Apple 仍 0，因为 `--macho-dsymtab` 只列**动态**符号，而程序内的 `sqlite3_*` 是本地符号 |
| `41674663275` | 1 | **success，本文件引用的证据轮** | 容错 nm 解析；artifact `13248959179` |

最终观测（`llvm-nm`/`llvm-readobj` 21.1.8，同一版本对，`tools_ok=true`，`acceptance_assessed=false`）：

| 目标 | 格式 | defined | undefined | weak | version 段 | 运行时装载原语 |
|---|---|---:|---:|---:|---|---|
| windows | PE | 0（已剥离） | 0 | 0 | 无 | `GetProcAddress`+`LoadLibraryExW` |
| android `libexreader.so` | ELF | **277** | 0 | 0 | 无 | 无 |
| android 其余三个 .so | ELF | 0 | 0 | 0 | 无 | 无 |
| gtk | ELF | **291** | 0 | 0 | 无 | 无 |
| macos / iphone / ipad | Mach-O | 动态表 0（仅本地符号） | 0 | 0 | 无 | `_dlsym` |

**计数来源分工（不得混用）**：android 277 与 gtk 291 来自本 run 的权威工具；
Apple 的 288 来自本地 `LC_SYMTAB` 解析与「程序定义集 = 归档定义集」的相等性，
本 run 的动态表读数 0 与之相容（程序不导出这些符号），不是矛盾。

**残余范围**：windows/gtk 归档级定义 provider 未覆盖（发布面不含 `.lib/.a/.map`）；
A4（`dlsym`/`GetProcAddress` 目标）为 `a4_partial=true`，字面量数据流未做。
