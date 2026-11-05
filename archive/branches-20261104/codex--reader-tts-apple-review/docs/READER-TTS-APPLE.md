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
系统回调同样只在主线程（= owner 线）上处理：delegate 本来就在主线程被调用，其它
线程递来的投递会先投到主队列再进入内部队列，因此句柄状态永不跨线程修改，
`reader_tts_destroy` 之后也不可能有回调再摸到句柄。
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
Actions。分支 `codex/reader-tts-apple`（交付）与 `codex/reader-tts-apple-review`
（独立复审）的 push 或 `workflow_dispatch` 会运行同一套作业：

1. `guard`：`HEAD == GITHUB_SHA`、固定起点 `f43baf91` 是祖先、SDK 冻结
   `9854061b` 的 `src include cmake CMakeLists.txt tests/fixtures bindings` 与
   两个保护 workflow 逐字不变、产品 SQL `apps/reader/store/001_catalog.sql`
   与起点相同、`git diff --name-only` 全在白名单内（每个生产作业再自查一遍）。
2. `macos`：构建并安装模块 → 从源码编平台中立的 66 项逻辑套件（伪引擎，
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

## 独立复审（branch `codex/reader-tts-apple-review`）

从交付 HEAD `24c498c6c69e382b1ff4dfaa50401a4031df400a` 起步，逐行复核
`AVSpeechSynthesizer` 适配层、delegate/owner/线程/run-loop 寿命、停止/取消/关闭/
重入、UTF-16→UTF-8 边界、语音与设备缺席、显式输入上限与内存归属。冻结的
`reader_tts.h` ABI、共享契约、其它平台包与保护树逐字未动。

**结论：C ABI 状态机、UTF-16 边界转换、取消/迟到回调按 request id 隔离、限额与
内存归属均与契约一致**（`utf16_to_utf8` 对代理对内部与越界偏移一律丢弃；
`push` 的 3 槽预留使终态不可能被顶掉；`speak` 复制输入后不再借用调用者缓冲）。
本轮修掉的是 5 处证据/寿命缺陷：

1. **证据 probe 的 PCM 采集有 use-after-free 与数据竞争**（`probe.mm`）。buffer
   block 被 synthesizer 持有，超时后主线程仍会 `delete capture`，而迟到 buffer
   继续写已释放对象；同时 `samples/sample_rate/buffers` 在回调线程写、主线程读，
   无同步。改为 `shared_ptr` 由 block 共同持有 + `mu` 保护全部可变字段，超时后先
   `stopSpeakingAtBoundary:` 再取快照，迟到 buffer 只会写进活对象。
2. **“任何线程”的 delegate 承诺与实际保证不符**（`apple_engine.mm`/`engine.hpp`）。
   旧实现只在 atomic 指针上做门，非主线程的投递若已取到 sink，仍可能与 destroy
   竞争。现在每个 delegate 投递都经 `deliverOnMain:` 落到主线程（=owner）：主线程
   投递行为完全不变，其它线程投递先入主队列，因此不再有跨线程触碰 sink 的路径。
   头注释与 `engine.hpp` 的线程说明同步改成这条真实保证。
3. **逻辑套件里有一个永远不可能失败的具名用例**
   （`memory.speak-fails-without-state-change`）。`speak` 只有一个分配点，而用例
   设置的是“第 2 次失败”，于是它永远走不到 MEMORY 分支还照样 PASS。改为第 1 次，
   并把断言从“MEMORY 或 OK”收紧成必须 MEMORY、必须没到引擎、状态与 id 不变。
4. **iOS 报告从未被应用内身份校验**（`run_ios.py`/`run_macos.py`）。汇总报告的
   `source_sha/run_id/attempt` 一直来自驱动进程的环境变量，而 probe 自己写下的
   身份（以及 04f02638 专门加的 `SIMCTL_CHILD_*` 转发）没有任何地方核对。现在
   每台设备、以及 macOS 的安装消费者报告，都在合并前先跑
   `verify_identity/verify_checks/verify_consumer`：来源必须是运行中的消费者
   自己写下的，二进制摘要必须是驱动实测的那一份。逻辑套件报告也改为用同一套
   检查单独校验（因此它开始输出 `"pending": 0`）。
5. **无语音机器上的范例回退字符串写错了**（`run_macos.py`）。`Fail()` 输出的是
   `{"error":"voices",...}`（无空格），断言找的是带空格的版本，所以“没有安装
   语音时合法返回 UNAVAILABLE”的兜底实际不成立。

新增回归：`close.while-stopping-closes-after-the-cancel`——停止尚未确认时收到
`request_close`，CLOSING 必须保住待终态、再让后端停一次、由取消回调收尾成
CLOSED，且 detach 恰好一次（这条转换此前没有被任何用例覆盖）。

## 本轮证据（review 分支）

受测源码 **`0cea18bfcd77465f81ee13dc3beb8065c772f57d`**，
[run 40168798871](https://github.com/NoGod3524/EXReader/actions/runs/40168798871) attempt 1
四个作业全部成功，严格汇总 `accepted=true`、`problems=[]`（一次通过，本轮没有
失败原件）。

| 执行平台 | 同次具名结果 | 工件 |
| --- | --- | --- |
| macOS 15.7.9 arm64（BlackHole 2ch 回环输出设备） | 逻辑 66 + 安装消费者 39 = **105 通过 / 0 失败 / 0 pending**；真实 PCM 75,456 B、37,706 帧、22,050 Hz、1.71 s、RMS 0.1356 | `reader-tts-apple-macos-40168798871-1` id 12589526192，73,700 B，`sha256:6a52abe3…56e9` |
| iPhone 16 Pro / iPad (A16)，iOS 26.2 arm64 Simulator | 26 通过 / 0 失败 / 13 pending（朗读回调与 PCM：该运行时完全不产声）；iPad 25 通过 / 13 pending | `reader-tts-apple-ios-40168798871-1` id 12589417148，16,040 B，`sha256:3938e981…9885` |
| 严格汇总（本分支） | 重新下载两个 producer ZIP、重算 SHA-256、核对 API 的 id/大小/digest/有效期/head_sha，解包核对报告身份与 WAV 摘要 | `reader-tts-apple-evidence-40168798871-1` id 12589358402，1,192 B，`sha256:eca8e7b8…a09f` |

三个工件有效期至 2027-01-23T06:21:27Z。作业 id：guard 121095243510、macOS
121095264212（48 s）、iOS 121095264230（12 m 25 s）、evidence 121097410263。
安装消费者二进制：macOS `9771e4149ce04fd7af3f8d738b5145e07d457cab84f014980987813bbefe88f9`、
Simulator `6d15db6462f7808e01dd37a47727dd8a77dfd29f5c9b8779567638ff27b38f75`。

本轮新增的可验证身份：**报告里的 source/run/attempt 现在来自运行中的消费者自己**
（macOS 进程环境、Simulator 应用经 `SIMCTL_CHILD_*` 转发），并由驱动在合并前
核对其 `consumer_sha256` 与实测二进制摘要；两台模拟器设备各自通过同一套检查。

范围仍分开登记：Simulator 只有 API/状态机/错误与限额被授予，真实朗读与音频记
pending；宿主接线、真机、听感、性能均未授予（见
[验收记录](validation/reader-tts-apple.json) 的 `capsule`）。

## 上一轮交付（本包原交付分支，历史记录）

下表是**交付分支**在复审前的证据（当时逻辑套件为 65 项、尚无本轮修复），保留原件
不作改写，也不与本轮结论拼接。

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
