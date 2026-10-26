# Team24 Apple 原生交付记录

工作树：`C:/Users/Oscar/exreader-team24-20261026/apple`。分支：`codex/team24-apple`。起点：`d263ce5228838ac90c0a0dc13a5193d4a7739681`。

本队交付 macOS、iPhone Simulator、iPad Simulator 上的五模块原生接入；真机签名、真机启动、VoiceOver 读屏尚未验收。默认阅读界面通过 More 中的阅读详情进入低频操作。

## 构建与验收入口

仅父代理提交功能分支后启动 `.github/workflows/team24-apple.yml`；新增完整轮次最多两次，attempt 重跑也计入。禁止本地构建、语法检查、测试、夹具生成、截图、工件下载、解包、解析。

该工作流在 GitHub Actions 内执行：

1. `tests/reader_team24_apple/guard.py` 冻结 seed 之外的 SDK、原测试、原工具和归属目录。
2. `tests/reader_team24_apple/build.py --target macos|iphonesimulator` 复用原 SDK 构建器，安装独立 raw-products，安装标注导入/导出、字体库、原件导出、位置历史、只读同步视图。
3. `tests/reader_team24_apple/run_ui.py --platform macos|iphone|ipad` 分别选择实际 Mac/模拟器，运行新增业务流程，以及未经修改的原始基础 13 例、阅读/导航/搜索/主题 21 例。三个阶段均启用新模块。D10 大字体、D11 取消以及 test01 导入去重错误处理保留原断言。
4. `tests/reader_team24_apple/verify.py` 在 Actions 内认证同 source/run/attempt 原始 ZIP，保留失败 job，并核对 ZIP 与实际程序身份。

每个平台工件包含原始 xcresult、命令日志、link map、原始测试文件哈希、程序 hash，以及保留执行权限的 `program-wave3/EXReaderHost-<platform>.zip`。解压后的 macOS `.app` 可启动；iPhone/iPad `.app` 仅供对应模拟器，未签名真机部署不在该范围。

## 旧轮次保留

旧 D15 run `40273780484`，attempt 1，source `4b0d44977c571efa3de2d7f73b6999343e08e438`：本队开工读取时 SDK 两任务通过，macOS 原生任务失败，iPhone/iPad 仍在运行。它不是本队新源码的验收证据。

S20 原 iPad 问题归于 `test01ImportDeduplicateAndErrors`，原 run `40248648454` / job `121335559096`，定位日志 `01:02:28.467692Z`。原 test13 实际通过，保留该结论。

## 本队新完整轮次

第一轮：source `560eba3f84ab6c7e0d51de3ed0cf765c6e850c66`，run [40276666182](https://github.com/NoGod3524/EXReader/actions/runs/40276666182)，attempt 1，最终 failure。Mac 与 iOS SDK/已安装模块构建成功；三个原生作业均在编译时因 `HostAccount.swift:4:8: no such module 'CReaderProduct'` 失败，三个阶段均为 0 个已执行 UI 用例，没有可启动程序。

首次失败来自新增项目生成器：读回的 `SWIFT_INCLUDE_PATHS` 是字符串，使用 `.insert` 和 `<<` 后把原模块路径与新增路径拼成同一个无效路径。第二轮修复改为显式数组，保留原 SDK 路径和原 `examples/apple/product` 路径。

同批源码复核修复：字体获取失败的 owner 自等待死锁；NULL/冲突夹具接收时缺失真实 wire SHA；标注定位误引用禁止链接的静态 resolver（改用现有动态 SDK 接口）；取消导入保留部分回执；仅 control 阶段启用额外阅读夹具按钮。原预算与原断言未改。

第一轮原 ZIP 由同 run/attempt 的认证 job `121427980184` 在 Actions 内下载并核对，认证结论因原生任务失败而保持 failure：

| 平台 | Artifact ID | 原 ZIP 字节 | SHA-256 | 到期 UTC |
| --- | --- | ---: | --- | --- |
| macOS | 12631575462 | 102233 | `8c9b2c2003ad2cbac44b731074b829fc9744c326bc4a6895e86d012234b62024` | 2026-11-25 06:17:09 |
| iPhone Simulator | 12630863401 | 101015 | `e87b5434f6f25154e0d7225a76441ea9986ce33d0a3b1860b82bf4a269cc0e02` | 2026-11-25 06:17:59 |
| iPad Simulator | 12631675261 | 101475 | `2a98ce5e866d075158afe79e8790a2c9746ead1a97ec7c6eaad288c66e814967` | 2026-11-25 06:13:24 |

第二轮尚未启动；下一次功能提交启动第二轮。受测 source、run、attempt、最终原 ZIP 身份和实际程序 hash 在结束后追加，文档提交使用 `[skip ci]`。
