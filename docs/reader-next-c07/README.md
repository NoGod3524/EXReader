# C07 同源 Android 与 Apple 双向记录协议联验

状态：未验收（`accepted=false`，待同一 run/attempt 的严格复核）。本文不授予 GUI、六平台、真机、性能或最终产品。

固定目标源码 `e67d87cbeabb2457e0852f681ef0b27b2c0da4d8`，独立分支 `codex/reader-next-c07`。
已有 Android `4a04a9cc` 与 Mac `15dab6b2`/iOS `5ac5e1fa` 的独立成功只作参考，不复用为同源通过。
公共 SDK（`edddc463…`）、raw 七模块（`56793e7c`）、宿主、原 tests、原裁判与其他包均不改，由 `guard.py` 在每个作业内核对。

## 工作流结构（`.github/workflows/reader-next-c07.yml`）

| 作业 | 平台 | 内容 |
| --- | --- | --- |
| `fixtures` | ubuntu | 用原 fixture 生成器一次生成四格式并冻结字节（`common.json`），固定 8845B PDF。 |
| `mac-send` | macos-15 | 同一目标源码构建 SDK 与独立 raw 产品族，编译 C07 驱动（原 `RawRecordInterop.swift` 的有记录副本），真实 `HostSession` 发送、NULL/源版本操作、`HostAccountSession` 经认证 HTTPS 推送 256 分片，保存实际 PUT 的字节。 |
| `android` | ubuntu+API34 模拟器 | 同一目标源码构建 raw 宿主；原样运行 `tests/reader_android_raw3/run_ui.py`，以**同 run** 的 Mac ZIP 作为对端（取代旧的固定 run）；再单独进程导出 Android 的 NULL 表达图。 |
| `mac-receive` | macos-15 | 还原 `mac-send` 的同一可执行文件/SDK/资源；新进程接收 Android 原始包，公共 receive + 新 SDK 对象 FOUND/重捕获、重开；`HostAccountSession` 经认证 HTTPS 从预载的 Android 对象接收 256 分片并重开；Android NULL 另行处理。 |
| `strict` | ubuntu | 实际下载同一 run/attempt 的全部原 ZIP，核大小/摘要/有效期/源、双方完整记录集、节目身份、程序与方向；缺任一端或方向即 pending。 |

## 复用与新增

复用（不改）：`HostCatalog`/`HostReadingRecords`/`HostAccount`/`HostModel`/`HostSDK` 等 Apple owner、`tests/apple_host/raw3/tls_fixture.py`、
`tests/reader_android_raw3/{candidate,run_ui,audit,bundle}.py` 与 Java 用例、`record_interop` 用例、`examples/android` 构建入口。
新增（均在独占路径）：`mac/C07Interop.swift`（原驱动副本，仅增加每条接收记录的 `kind/mode/anchor_version/transport_capture/recapture/reconstruction` 与 `null-receive` 模式）、
`candidate.py`（向生成的 Android 仪器测试增加一个 `c07-null-export` 阶段，并记录补丁前后摘要）、`android_null.py`、`peer.py`、`mac_send.py`、`mac_receive.py`、`strict.py`、`fetch.py`、`guard.py`、`common_fixtures.py`。

## 语义分列

点、范围、含 NUL 的 suffix/exact、分配空串（非 NULL、size 0）与 NULL 分别统计（`strict` 的 `record_classes`）。正例来自真实 SDK capture；NULL 只作 transport 保留，不得得到 typed 位置、capture、FOUND 或导航。
EPUB 章节由 `part_path` 重建，与原 transport 字节分列记录（`transport_vs_reconstruction`）。源 anchor 1/2/3、未知 parser 拒绝、旧 private v1/v2 语义、重试不回退由被复用的原阶段继续执行。

## 范围

只授本包原生 owner 与协议：Android API34 x86_64 模拟器与 macOS。不授 GUI、六平台、真机、性能或最终产品。所有构建、语法、测试与工件解析仅 Actions。
