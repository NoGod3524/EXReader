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

第二轮：source `b9b923f558012fe98ea265ec8f832cad71729653`，run [40279184530](https://github.com/NoGod3524/EXReader/actions/runs/40279184530)，attempt 1，最终 failure。三个原生作业都正确找到 `CReaderProduct` 后，在 `reader_apple_features.h:5` 因缺少 `reader_font_library.h` 编译失败；所有 UI 阶段为 0 个已执行用例，没有可启动程序。构建脚本漏开原模块默认 OFF 的 `READER_FONT_LIBRARY_BUILD` 与 `READER_ANNOTATION_IMPORT_BUILD`，导致两模块为空构建。修复显式开启两个选项、指定每个模块真实 target，并在写安装清单前要求库与头文件实际存在且非空。

第二轮原 ZIP 经同 run 的认证 job `121431686055` 在 Actions 内核对，认证结论保持 failure：

| 平台 | Artifact ID | 原 ZIP 字节 | SHA-256 | 到期 UTC |
| --- | --- | ---: | --- | --- |
| macOS | 12631393008 | 103003 | `eeb6d7ee67fd6bb0d4061c8c2808859622d71dd95d07385b837c73e7e7eb9579` | 2026-11-25 06:26:03 |
| iPhone Simulator | 12631867741 | 103501 | `f2e2a27a4701d33ec0e4430662115f3380081e81f1fc7a0f367648e52ce78247` | 2026-11-25 06:30:17 |
| iPad Simulator | 12631103178 | 103719 | `8faa0e930db47353e81e501361d479ae40dabe9a615b196b6b2ab7cce72c07d4` | 2026-11-25 06:29:39 |

协调者在收到精确根因和修复差异后批准额外一次完整第 3 轮；前两失败不删除、不重置额度。

第三轮：source `02dbb1a7cb0fa80920ad89dcdeec76bf3af5c6b0`，run [40280431991](https://github.com/NoGod3524/EXReader/actions/runs/40280431991)，attempt 1，最终 failure。两套 SDK/真实模块 target/安装库与头检查通过。三个 wave3 应用均编译链接并被脚本打包，但原 embed 检查阶段的 `tools/check_apple_product.py:30` 严格按 UTF-8 读取原始 link map 失败：Mac 字节位置 2259028–2259029、iPhone 2259196–2259197、iPad 2259152–2259153。随后本队脚本调用原 `inspect` 再次遇到相同错误，未进入 base/control 阶段。

本轮没有执行 UI 用例，没有启动成功证明，不能把已链接工件称为可启动验收通过；签名/最终 embed 检查也未完成。原断言、预算与共享检查器都未修改。最小解码修复提案见 `team24-apple-linkmap-owner-proposal.md`，尚未应用；额外完整轮次也尚未批准。

同 run/attempt 认证 job `121435998748` 在 Actions 内核对原 ZIP、其中所有记录文件与程序身份，认证结论因原生失败而保持 failure：

| 平台 | Artifact ID（含已链接 review app ZIP） | 原 ZIP 字节 | 原 ZIP SHA-256 | 到期 UTC |
| --- | --- | ---: | --- | --- |
| macOS | [12631692990](https://github.com/NoGod3524/EXReader/actions/runs/40280431991/artifacts/12631692990) | 56412472 | `109c522511504742c15def49b1263a9e3da29890f7d11a1a97c70a056c515a1c` | 2026-11-25 06:37:55 |
| iPhone Simulator | [12632265908](https://github.com/NoGod3524/EXReader/actions/runs/40280431991/artifacts/12632265908) | 56580842 | `437956bd8c2589c9e76f44a562f2e54020dd242bf25183a9af9b464f217fce03` | 2026-11-25 06:41:36 |
| iPad Simulator | [12632250994](https://github.com/NoGod3524/EXReader/actions/runs/40280431991/artifacts/12632250994) | 56580730 | `fc5a693db231c94742784becadd37151a9416d5e514964e00fbeb5be1bde2165` | 2026-11-25 06:44:29 |

| 平台 | 实际 executable 字节 | 实际 executable SHA-256 |
| --- | ---: | --- |
| macOS | 8241064 | `69004589efd300704e5aa93112dffd100438028ed1aebf7ce98ab8504dda2b58` |
| iPhone Simulator | 8311872 | `c29158a90e86dbc9d800b3bf2de4600197e78417aaa120cd7a284d57e2a2e039` |
| iPad Simulator | 8311824 | `62dc4eea1824e39a8613b5321a326a747f44fc094c5b4727f3e2a21e258cc496` |

## 最小合入范围

三个功能提交依次为 `560eba3f`、`b9b923f5`、`02dbb1a7`，基于 `d263ce5228838ac90c0a0dc13a5193d4a7739681`。只涉及 `examples/apple/`、新增 `apps/reader/apple-feature-integration/`、本队 `tests/reader_team24_apple/`、`.github/workflows/team24-apple.yml` 与本队 handoff 文档；原 SDK、其他平台、原测试和 canonical 工具未改。[功能源码差异](https://github.com/NoGod3524/EXReader/compare/d263ce5228838ac90c0a0dc13a5193d4a7739681...02dbb1a7cb0fa80920ad89dcdeec76bf3af5c6b0)。该差异仍受第三轮检查器失败阻断，不建议把它当作已验收产品合入。

## 本队 review 应用与生产组合边界

三个 phase 的 app 都定义 `DEBUG`、`EXR_APPLE_PAGE_THEME`、`EXR_APPLE_HOST_REVIEW`、`EXR_APPLE_RAW3`、`EXR_APPLE_WAVE3`；仅 control 额外定义 `EXR_APPLE_READING_REVIEW`。Clang 定义 `EXR_READER_SELECTOR_BYTES_CANDIDATE=1` 和 `EXR_APPLE_WAVE3=1`。不定义 `EXR_APPLE_RAW3_REVIEW`。本队工件是该配置的 review 应用，不冒称无 review 宏的生产打包；生产 flags/package 绑定由根协调 composition 入口承担，本队不修改原 canonical tools。

实际构建 app：`build/team24-apple/<platform>/derived-<phase>/Build/Products/Debug/EXReaderHost.app`（Mac），或 `Debug-iphonesimulator/EXReaderHost.app`（iPhone/iPad）。实际 executable 为 Mac 的 `Contents/MacOS/EXReaderHost` 或模拟器的 `EXReaderHost`。工件内保存为 `program-<phase>/EXReaderHost.app`，可启动 ZIP 为 `program-<phase>/EXReaderHost-<platform>.zip`。最终文档提交使用 `[skip ci]`，不把文字提交冒充受测源码。
