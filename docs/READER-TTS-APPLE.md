# Apple 原生朗读适配（J17）

独立可选的 Apple 朗读组件：在冻结的公共 C ABI 后面接入 AVFoundation
`AVSpeechSynthesizer`，实现声音选择、速度、暂停/继续/停止和带请求身份的
生命周期通知。它不读书籍、不持有 SDK、不下载语音、不接云端 TTS，默认构建
不会加入，任何宿主目标都不会意外链接它。

- 实现：`extras/reader-tts-apple`（`include/reader_tts.h`、`src/core.cpp`、
  `src/apple_engine.mm`、`examples/`）
- 测试：`tests/reader_tts_apple`（逻辑套件、安装后消费者 probe、iOS app 宿主、驱动与严格汇总）
- 出口：`.github/workflows/reader-tts-apple.yml`
- 契约：[tts-contract.md](handoffs/reader-next-wave/tts-contract.md)（四个平台共用的冻结接口）

## 接口语义（本实现如何落地）

- `reader_tts_create` 只在主线程成功；其它线程返回 `OWNER` 且不分配句柄。
  `AVSpeechSynthesizer` 在主线程创建，之后所有控制调用也在主线程。
  没有安装语音时返回 `OK` + `SERVICE_UNAVAILABLE`，此时 `speak` 返回
  `UNAVAILABLE`，`voices` 也返回 `UNAVAILABLE`。
- 每次调用必须来自创建句柄的 owner 线程，`observe/poll/destroy` 也一样；
  其它线程得到 `OWNER`，句柄状态不变。`reader_tts_voice_list_free` 与句柄无关。
- 系统回调（delegate）只把纯值写入内部 128 事件环形队列，从不回调宿主。
  `speak` 前预留三个槽位（`STARTED`、一条合并后的 `RANGE`、一个终态），
  队列满时返回 `LIMIT`，因此终态永不丢失；宿主不 poll 只会看到 `LIMIT`。
- `RANGE` 的 `start/end` 是**本次输入 UTF-8 字节边界**。系统给的是 UTF-16
  偏移，落在代理对内部或越过末尾的偏移被丢弃，不猜时钟位置。
- `request_id` 非零、宿主分配、按句柄严格递增；重用已接受的 id 返回
  `ARGUMENT`。同一时刻只允许一个活动请求，未停止就替换返回 `BUSY`。
- `max_utf8_bytes` 默认 16 KiB、只能下调（>16 KiB 返回 `LIMIT`），超长文本
  由宿主分块。严格 UTF-8：拒绝过长编码、代理区、>U+10FFFF、截断和嵌入 NUL；
  `speak` 复制输入，不借用调用者缓冲。
- `rate` 是 0.5..2.0 的相对速率，映射到 AVFoundation 的 0..1（1.0→0.5，
  0.5→0.25，2.0→0.75，分段线性）。这是语速提示，不是精确时长比例。
- `stop` 对当前请求明确停止，每个成功启动的请求恰好一个
  `FINISHED/STOPPED/FAILED`；后端拒绝取消时由核心立即补终态。系统迟迟不确认
  停止或关闭时，2 秒 steady-clock 期限在下一次 owner 调用上结算（库不会自己起
  定时器或线程）。
- `request_close` 非阻塞且幂等；活动请求的终态在 close 之后仍可 poll 到。
  `destroy` 在 `CLOSED` 之前返回 `BUSY` 并保留指针，成功后置 `NULL`。
- 所有非 `OK` 返回都不改变状态；`native_code` 见头文件（1001 错线程、
  1002 未知/不可用语音、1003 文本或后端不可用、1004 系统拒绝控制调用）。

## 线程、音频会话与后台

`reader_tts_create` 必须在主线程（`AVSpeechSynthesizer` 由主 run loop 驱动）。
库不配置也不打开 `AVAudioSession`：iOS 的类别、后台音频策略和“失去朗读权时
停止”都由宿主决定；macOS 由系统默认输出设备决定。库不新增常驻服务器、插件
框架、WebView 或 JS UI。

安装包只有`reader_tts.h`、静态库 `libreader_tts.a`、CMake 包
`EXReaderTTSApple`（target `EXReaderTTSApple::reader_tts`）和许可证/文档。
消费者：

```cmake
find_package(EXReaderTTSApple 0.1.0 CONFIG REQUIRED)
target_link_libraries(app PRIVATE EXReaderTTSApple::reader_tts)
```

`extras/reader-tts-apple/examples` 就是这样的安装后接入范例（`voices` /
`speak --text ... --pause-ms N`），它只 include 安装后的头，只链安装后的库。

## 复现（全部在 GitHub Actions）

本地只改源码/文档/Git；构建、测试、安装、夹具、benchmark、工件下载与解析都在
Actions。分支 `codex/reader-tts-apple` 的 push 或 `workflow_dispatch` 会运行：

1. `guard`：`HEAD == GITHUB_SHA`、固定起点 `f43baf91` 是祖先、SDK 冻结
   `9854061b` 的 `src include cmake CMakeLists.txt tests/fixtures bindings` 与
   两个保护 workflow 逐字不变、产品 SQL `apps/reader/store/001_catalog.sql`
   与起点相同、`git diff --name-only` 全在白名单内（每个生产作业再自查一遍）。
2. `macos`：构建并安装模块 → 从源码编平台中立的 65 项逻辑套件（伪引擎，
   `-DREADER_TTS_TESTING`，不进安装包）→ 用 `find_package` 的安装前缀编
   真实 probe（真实 `AVSpeechSynthesizer`、真实主 run loop 回调、暂停/继续/
   停止/队列替换/迟到回调/关闭销毁）→ 安装后范例 `voices`。
3. `ios`：同一源码交叉编到 arm64 iOS Simulator，装进真实 UIKit app，由 app 的
   主 run loop 驱动同一 probe（`simctl` 启动、私有目录回传结果）。
4. `evidence`：只读 token 重新列出本次 run 的两个 producer 工件，重新下载 ZIP、
   重算 SHA-256、与 API 的 id/大小/digest/有效期/head_sha 逐项核对，解包后
   再核对报告内的 source/run/attempt/平台、失败用例数和 WAV 摘要。缺项、跨源码、
   跨 attempt 或篡改一律拒绝。

```
本地零构建。证据文件名：reader-tts-apple-macos-<run>-<attempt>、
reader-tts-apple-ios-<run>-<attempt>、reader-tts-apple-evidence-<run>-<attempt>。
```

## 真实音频证据与范围

冻结 ABI 没有音频输出钩子，因此“真实 PCM/WAV”由 probe 用同一安装平台上的
第二个 `AVSpeechSynthesizer` 走 `writeUtterance:toBufferCallback:` 采集：
报告记录帧数、采样率、时长、RMS、WAV 字节数和 SHA-256，驱动再重算摘要。这证明
该平台语音引擎对同一段中文/表情文本真的产生了采样，但它不是对库自身输出的录音
（库按契约直接 `speakUtterance:` 到系统输出设备）。

## 当前状态

首次云端验收进行中，`docs/validation/reader-tts-apple.json` 的
`accepted=false`。真实跑通后按范围填写受测 SHA、run/attempt/job、具名结果、
工件 id/字节/digest/有效期、失败原件与未覆盖范围。

## 未覆盖范围（明确登记）

- 物理 iPhone/iPad/Mac 真机执行：未覆盖（只有 macOS runner 与 iOS Simulator）。
- 听感质量、发音正确性、音量/音色主观判断：自动化无法授予，未覆盖。
- 宿主接线（`Host*.swift` 的 UI、`AVAudioSession` 类别、后台策略、锁屏控制、
  分块调度）：由 root 统一做，本包不改宿主。
- 平台中立逻辑套件只在 macOS runner 运行；iOS 上跑的是真实后端 probe（同一个
  `core.cpp` 但由真实 AVFoundation 驱动），未在 Simulator 里重跑伪引擎套件。
- 语音下载/增强语音（premium/enhanced voices）：本包只用系统已安装的声音，
  不触发下载。
- 无音频输出设备的 runner 上，系统可能不投递 delegate 回调；此时相关具名用例
  记为 `pending` 并记录原因（`speech_available=false`），不会以“API 调用成功”
  冒充朗读成功。
