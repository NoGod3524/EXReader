# Android team24 接手与验收

团队工作树：`C:/Users/Oscar/exreader-team24-20261026/android`，分支 `codex/team24-android`。
接手起点 `28f49ee0399d48518cc2afb0048009b6c38edcfa`；原 C11 目录保持只读。
当前代码提交 `1a4c5d5207d079a45a725dd2d560b31f9ab49593`，把必填 JSON 字段读取移出不能抛受检异常的 UI 谓词，尚未受测。
其父提交 `6edb2ed9e9f33e923091ff43d108ddd40507de28` 修复 candidate 早接线。
追加轮受测提交 `ac2c6973204860a7c5a5a32967421e5fea3622c3`，含 `6edb2ed9` 的早接线修复及封存文档。
本包承担 Android 主线，六平台组合与全局 1710/CPU 验收由原协调者负责。

## 实现与最小合入范围

从接手起点沿本分支合入；保留全部原实现与历史。主要业务修复在 MainActivity 与两份 wave3 JNI
include：预先验证书籍身份，FOUND callback 只进入 SDK owner；标注逐条取消，不屏蔽整个批次；
JNI 分配收据前处理取消异常，保留普通异常与已提交项。Java 面板和 stage 对接失败、关闭、旋转、
陈旧回调及导航失败时清理临时文件/peek，字体确认框随父面板关闭。

公共 workflow 仅补齐原模块 opt-in 与 sync 调试证书夹具、导航 runner 接线。
专用 Actions candidate 精确核对去扩展名标题及格式，原 UI driver 不变；不以进程 exit 0 计为业务成功。
无 SDK/bindings、原 1710、CPU 限制、其它平台或默认分支修改；未创建 PR/tag/Release。

三个子代理实际名称及职责：`/root/jni`（cpp），`/root/panels`（MainActivity 以外宿主 Java），
`/root/acceptance`（专用验收）；父代理负责 MainActivity、工作流、审阅、统一提交与运行跟踪。

## 完整轮次原样保留

| 轮次 | source / run / attempt | 实际结果 |
| --- | --- | --- |
| 接手前旧 C11 | `28f49ee0399d48518cc2afb0048009b6c38edcfa` / [40274139390](https://github.com/NoGod3524/EXReader/actions/runs/40274139390) / 1 | 失败；annotation-import 默认 OFF，`ninja: unknown target install`，无 APK、未跑 UI |
| team24 新增 1 | `0415b8b39d8f9025126b8f90ed17c206da17d787` / [40276105096](https://github.com/NoGod3524/EXReader/actions/runs/40276105096) / 1 | 失败；已构建 SDK/全部模块，AAPT 缺 `raw/host_sync_fixture_ca`，无 APK、未跑 UI |
| team24 新增 2 | `0fe1bcb593b307eb85ebc63b5ed09990952e9402` / [40276608248](https://github.com/NoGod3524/EXReader/actions/runs/40276608248) / 1 | 失败；已补齐 sync CA，AGP 同时捕获原 driver 和晚接线 candidate，4 个 duplicate class；无打包 APK、未跑 UI |
| team24 新增 3，root 特批唯一追加轮 | `ac2c6973204860a7c5a5a32967421e5fea3622c3` / [40277306694](https://github.com/NoGod3524/EXReader/actions/runs/40277306694) / 1 | 失败；candidate 不再重复类，uitest 编译和 assemble 通过，宿主 Java 与 buildCMakeDebug[x86_64] 步骤通过；Wave3UiTest 的 6 处受检 JSONException 编译错误阻断整包，无打包交付 APK、未跑 UI |

旧 S20 run 40248648454 的 Android 3/45 继续保留为失败。未拼接旧 source 的成功项。

## 已保留的原 ZIP 身份

GitHub API 返回的 archive digest；本地没有下载、解包或解析工件。

| run | artifact ID / bytes | ZIP SHA-256 | 有效期 UTC |
| --- | --- | --- | --- |
| 40274139390 | 12630150203 / 25457998 | `445f6112c0f6d27ea3f290c0aef03333a4fa383f9b0642972cf4cae1fd4b51f7` | 2027-01-24 05:25:32 |
| 40276105096 | 12629938255 / 40588841 | `d3dd444f9dcbee1fab763ccf479362c329bd7cfd7aba775ff35c74bdbb94fc60` | 2027-01-24 05:47:12 |
| 40276608248 | 12629714423 / 40597428 | `9840901e43710c245bc420397fea23279495afaeb4e00e17ad06767026f3b592` | 2027-01-24 05:52:38 |
| 40277306694 | 12630538712 / 40598003 | `cf81bdfa116f8467d97730a296bf937052cf35e36173d27b1344a7575e333c7b` | 2027-01-24 06:00:14 |

## 本轮要求与未测边界

尚无完整 APK 或业务/UI 通过结果；源码修复不能替代验收。完整验收要求实际 APK 的哈希等于设备安装字节，API34/x86_64 emulator 启用 CheckJNI；
走查 45、review 10、bounded 11、原导航 16+2 全部逐项成功；wave3 三阶段覆盖五模块，
真实非 NULL FOUND 预览/明确确认提交、标注/原件批次取消保留前缀收据、stage 两个取消边界、
关闭面板后 owner 释放真实 peek、字体 lease 与旋转、进程退出。失败必须保留在同 run 报告。
当前 workflow 未接入独立 `tests/reader_android_reading/ReadingUiTest` 16 项验收；
wave3 的阅读功能检查不能替代它。当前没有可交付 APK 的实际程序 SHA-256 或安装身份。

尚无真机、TalkBack 人工读屏或性能通过主张。Wave3 文件选择使用 framework ActivityResult
stub 返回私有文件 URI；旧走查才驱动系统 DocumentsUI。原件通过 SAF 保存；冻结 manifest
未声明分享 provider，系统分享不可用。本包没有完成六平台产品验收。

本地仅源码、文档、Git 与必要状态查询；所有构建、语法检查、夹具、截图及工件处理只在 Actions。
原协调者在收到第 2 轮 AGP 接线根因后，明确批准且仅批准追加 1 次完整 Actions；第 3 轮已启动。
前两轮失败不重置；第 3 轮已失败，未启动第 4 轮。编译修复已推送，所有 runtime 结论仍未测。

若获准，接入命令是 `gh workflow run reader-wave3-c11.yml --ref codex/team24-android`；
仅在确认同源码没有在跑的任务后启动。完整代码差异可用
`git diff 28f49ee0399d48518cc2afb0048009b6c38edcfa..1a4c5d5207d079a45a725dd2d560b31f9ab49593 --stat` 查看。
