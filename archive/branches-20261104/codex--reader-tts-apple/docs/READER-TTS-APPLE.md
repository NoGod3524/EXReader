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

## 平台发现（实测，含本包修掉的缺陷）

1. **未知语音 ID 会被系统“接受”**：`+[AVSpeechSynthesisVoice voiceWithIdentifier:]`
   在 runner 上对 `com.example.absent` 也返回了非空对象，导致未知声音不是
   `ARGUMENT`，而是先通过校验、再在真正朗读时失败。后端改为只认**identifier 与
   请求逐字相等**的已安装声音（`ResolveVoice`），查找与朗读共用同一判定；
   `probe.rejects-unknown-voice` 覆盖这条。
2. **取消后的下一句可能被系统丢掉**：`stopSpeakingAtBoundary:Immediate` 之后
   立刻 `speakUtterance:` 的新请求可能拿到 `STARTED` 与一个 `RANGE` 后不再推进。
   host 要在取消终态之后过一个 run-loop turn（本 probe 用 1 s）再提交下一块；
   该行为单独登记为 `probe.post-cancel-utterance`，与“迟到回调不污染新请求”
   （`probe.late-callback-isolation`，按 request id 判定）分开记。
3. **无音频路由的 runner 不产出回调**：headless 机器上 `speakUtterance:` 只让
   `isSpeaking` 变真，delegate 一个都不投递，`writeUtterance:toBufferCallback:`
   也拿不到任何 buffer。Actions 里为此临时装一个 BlackHole 回环设备当默认输出
   （best-effort，不作为门；失败只会让相关用例记 pending）；iOS Simulator 即使
   host 有该设备仍然不产声，故 Simulator 的朗读/PCM 用例记为 pending。

## 当前状态

受测源码 `ecc51101c130502da59b0ffe5eca78dc80138e54`，
[run 40129088735](https://github.com/NoGod3524/EXReader/actions/runs/40129088735) attempt 1
的四个作业全部成功，`accepted=true`。

| 执行平台 | 同次具名结果 | 工件 |
| --- | --- | --- |
| macOS 15.7.9 arm64（BlackHole 回环输出设备） | 逻辑 65 + 安装消费者 39 = **104 通过 / 0 失败 / 0 pending**；真实 PCM 75,456 B、37,706 帧、22,050 Hz、1.71 s、RMS 0.1356 | `reader-tts-apple-macos-40129088735-1` id 12573932041，73,611 B，`sha256:352b8f3b…e51c` |
| iPhone 16 Pro / iPad (A16)，iOS 26.2 arm64 Simulator | 26 通过 / 0 失败 / 13 pending（朗读回调与 PCM：该运行时完全不产声）；iPad 25 通过 / 13 pending | `reader-tts-apple-ios-40129088735-1` id 12574162912，15,682 B，`sha256:1e7eb9ac…947a` |

两个工件有效期至 2027-01-22T20:17:08Z；严格汇总作业（120978693849）重新下载两个
ZIP、重算 SHA-256、核对 API 的 id/大小/digest/有效期/head_sha，并解包核对报告内的
source/run/attempt/平台、失败用例数与 WAV 摘要，`problems=[]`。完整身份见
[验收记录](validation/reader-tts-apple.json)。

失败原件全部保留：首次 push 的 workflow 因作业名带裸冒号无效（run 40123553063）；
此后依次暴露并修掉假引擎未用字段、跨 sysroot 的 `find_package`、两条错误的逻辑
预期、占位语音、同步索要 CLOSED、暂停后 stop 竞速、取消后下一句、`-Werror` 未用
变量、Simulator 的应用内 source 身份，以及“无 buffer 该记 pending 而非失败”
（run 40124481498 / 40125616017 / 40126409617 / 40126868252 / 40127571458 /
40128098065）。另有两次为被后续提交取代而取消（40123743856 / 40128919501），以及
一次只差 iOS 的同源运行（40128493769，macOS 104/0/0），均不拼接进最终结论。
