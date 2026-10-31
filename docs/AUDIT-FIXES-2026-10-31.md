# EXReader 2026年10月31日审计修复

[本次审计](AUDIT-2026-10-31.md)的 F01–F04 已全部修复，并加入回归测试。修改基于 `codex/reliability-convert-memory` 分支的 HEAD `9dfb155a1e42a5ee82fabc4beea41db575a309fa` 和原有未提交修改；SDK 3.39.0、ABI 1、书库 schema 6 不变。

PR #27 与主分支 `cdfe48231853d6e70fba2c41b42bdd187155901a` 集成时，沿用主分支已有的 `exr_library_source`：每次范围读取创建短期 blob 游标，由源对象持有书库引用，删除时使旧源失效。F02 的新增回归与主分支短读回归全部保留；不重新引入旧的长期 blob 游标实现。下表及本文件的运行数字记录原始修复，集成结果以 PR 的 `reading-required` 检查和评审为准。

集成后的 Windows GCC 专项通过：转换 CLI **46/46** 场景、流式书库 **123** 项检查。此处的 CLI 数量不包含原工作区里未提交的其他审计回归；本次新增的 9 个转换场景全部保留。

## 修复与回归

| 发现 | 修复后的行为 | 新增验证 |
| --- | --- | --- |
| F01 P1：路径比较错误重复释放 | 错误对象只释放一次；非法输出被拒绝后，独立正常任务继续执行并生成报告。 | 非法路径与正常任务混合批处理，检查退出码、逐项状态、输出内容与临时文件。 |
| F02 P1：保存进度后 CBZ 读取失效 | 每次范围读取前重新定位 SQLite blob，校验原长度，并在数据库互斥锁内读取。删除书籍会使其旧阅读器失效，避免行 ID 重用后读到新书。 | 两个已打开阅读器连续保存进度、收藏和封面后，渲染像素保持相同；另测删除后重导入，以及关闭书库后继续读取。 |
| F03 P2：Unicode 文件名漏检 | Windows 以 UTF-16 `CompareStringOrdinal` 比较路径，移除 UTF-8 字节长度相等的前提。 | 拒绝 `É/é`、UTF-8 长度不同的 `Ⱥ/ⱥ` 重名目标；保留 Windows 上不同名的 `ſ/S` 对照。 |
| F04 P2：报告覆盖批处理清单 | 清单及其文件别名纳入输入保护。报告冲突在转换前拒绝整个调用；输出冲突拒绝对应任务，独立任务继续执行。 | 清单路径与硬链接保护；报告显式使用 `--overwrite` 仍被拒绝；清单散列不变。 |

实现位于 `tools/convert.c`、`tools/convert_io.c`、`src/library.c`，回归位于 `tests/check_convert_cli.py` 和 `tests/test_library_stream.c`。转换契约及读取生命周期同步写入 `docs/CONVERSION.md`、`docs/WP12A-STREAMING.md`。

## 验证结果

Windows x64 Release，本轮最终源码对应的结果如下：

| 验证 | 结果 | 证据（相对 `build/audit-fixes-20261031/`） |
| --- | --- | --- |
| GCC 全量构建 | 通过 | `build-r2.log` |
| GCC CTest | 161/161 | `ctest.log` |
| GCC 完整转换 CLI | 61/61 | `gcc-cli.json` |
| GCC 流式书库专项 | 115 项检查通过 | `library-final.log` |
| MSVC 转换器与流式书库目标构建 | 通过 | `msvc-build.log` |
| MSVC 完整转换 CLI | 61/61 | `msvc-cli-final.json` |
| MSVC 流式书库专项 | 115 项检查通过 | `msvc-library.log` |
| GCC 转换基准 | 100/100，失败、未完成项、残留临时文件均为 0 | `benchmark.json` |

CTest 排除了 `native-convert-cli` 和 `native-convert-benchmark`，这两项以原测试驱动、绝对路径参数和独立工作目录单独执行，对应上表 CLI 与基准结果。

基准单项峰值 **27,516,928 B**，100 项批处理峰值 **29,978,624 B**，增加 **2,461,696 B（约 2.35 MiB）**，低于 **33,554,432 B（32 MiB）**预算；批处理耗时 **13.363256 s**。

新增 9 个 Windows CLI 场景在修复前的 MSVC 转换器上有 8 个缺陷场景失败、1 个不同文件名对照通过；修复后全部通过。修复前的 GCC 流式书库回归在保存元数据后渲染处得到 `EXR_IO`，修复后 115 项检查通过。对应证据为 `cli-msvc-before.json`、`library-before.log`。

本轮运行范围为 Windows GCC 与 MSVC；Linux sanitizer、macOS 与移动设备未运行。机器可读结果、源码及程序散列见 [验证索引](validation/2026-10-31-audit-fixes.json)。
