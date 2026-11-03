# 限时构建验证第 2/2 次：构建和四项测试通过，作业红

候选 `e0c1c4586013910fcb4bd5c884b9a56dd07a9491`，SDK 基线 `95100501eeef9c6325be8b3882aa400c99cf000f`。
[Run 41708081512](https://github.com/NoGod3524/EXReader/actions/runs/41708081512)，job `126168622894`，macos-14，单作业，20 分钟上限。
本次为用户授权轮次 **2/2**；新候选触发的新 run，其 GitHub `run_attempt` 为 **1**，两者不混用。
整体结论 failure。未重试、不再申请下一轮；Apple build-only 项整体仍 open，不写成 Apple 验收通过。

## 已实际通过的构建与测试

准入检查成功，固定基线对象可读；公开 provider、SDK、ProductCatalog、`reader-original-import-check` 均构建成功。
C++17 测试目标的编译修复已获 Apple 原生构建验证。

| 类型 | 测试名 | 实际数量 |
|---|---|---|
| 原产品测试 | `product-originals` | 1/1 passed |
| 原产品测试 | `native-product-catalog` | 1/1 passed |
| FTS5 | `sqlite-provider-check` | 1/1 passed |
| FTS5 | `shared-sqlite-sdk-product` | 1/1 passed |

原始 JUnit 为 `product-tests.xml`、`fts5-provider.xml`、`fts5-integration.xml`；FTS5 合计 **2/2**，原产品测试合计 **2/2**，不是断言数量。

**C++17 仅测试目标需要，对外契约未变，SDK 消费者不需要 C++17。**

历史状态原文：**两项仍待 CI**。此句作为前序快照保留；其中两项原产品测试现已在本 run 实际通过，不再是本 run 的 pending 项。

## 新原因红：open item CI-CONTROLS-001

首条 error 原文：

```text
2026-11-03T19:58:38.2066960Z ##[error]Process completed with exit code 1.
```

发生于 `Reject actual Apple main and SDK binaries with embedded SQLite` 步骤。
该步骤先从 provider CMakeCache 读取 SQLite 源目录，再检查其非空，然后调用 Python 检查器；日志没有更具体的诊断。
工件没有 `apple-positive.json` 或真实负例结果，也没有远端 stage 扫描输出。现有日志不足以确认具体子命令及根因，不将其写成 SQLite 行为失败。
状态：open；本次仅记录首条 error，不实施新修复、不重跑、不再申请。

## 四项验收证据状态

| 要求 | 当前状态 |
|---|---|
| 所有应用受控映像只有一份 SQLite 实现 | 尚未闭合；本次没有生成完整的三映像符号输出，不能由构建成功替代。 |
| FTS5 名称及数量 | 本次真实执行 2/2 passed，原始 JUnit 已保留。 |
| stage 下 sqlite 扫描 | 远端 find 未到达；下载的已安装 stage 重新扫描为 15 项，路径、大小和 SHA-256 见 `stage-sqlite-scan-from-artifact.json` / `.txt`，明确是工件只读复核。 |
| Apple 故意内嵌负例必须报错 | 未取得结果，不计通过。 |

## 产物与来源

工件 `13266086992`，9,058,366 bytes，SHA-256 `d3a0a4c4c8b9436489600cfc2d75970f932e5dbc20f517d92969ae445a153294`。
原始下载 ZIP 保留于候选工作树 `build/sdk-ci-41708081512.zip`，其实际哈希与 API metadata、上传日志一致。
本目录保存完整作业日志、run/artifact metadata、原始 source/JUnit、测试摘要和下载 stage 的扫描输出；顶层 manifest 记录文件哈希。
`source.json` 精确绑定候选与 SDK 基线，并保持 `apple_acceptance_assessed=false`。

CI-ADMISSION-001 的准入失败已修复并由本 run 证明，作为 P 包 CI 卫生项单独关闭；新 open item 不归入 F07。
catalog、测试断言、SDK 版本和默认分支均未改变。
