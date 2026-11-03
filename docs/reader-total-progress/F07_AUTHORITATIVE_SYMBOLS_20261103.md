# F07 authoritative symbol observations — 2026-11-03

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
