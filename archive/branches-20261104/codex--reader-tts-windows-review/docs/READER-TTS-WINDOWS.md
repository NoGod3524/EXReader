# Windows 原生朗读（SAPI 5）

`extras/reader-tts-windows` 是独立、可选的静态模块（C11），把 Windows SAPI 5 的朗读能力
包成冻结的 `reader_tts` 0.1.0 C ABI：枚举声音、开始／暂停／继续／停止、速度、完成与失败通知。
它不解析书籍、不碰 SDK 音频开关、不联网、不下载声音；文本由宿主按已验证的块交给它。
宿主（Windows 宿主、UI、朗读调度）由 root 统一接线，本包只提供组件、安装包与安装后消费者。

公开头 `reader_tts.h`（与 Apple/Android/Linux 三个包同名同 ABI）和 Windows 专有的
`reader_tts_windows.h`（WAV 输出与包内测试用 debug 钩子）。CMake 包
`EXReaderTTSWindows 0.1.0`（SameMajorVersion），目标 `EXReaderTTSWindows::reader_tts`。

## 线程与归属

| 项 | 规则 |
| --- | --- |
| owner | 除 `reader_tts_voice_list_free` 外，所有函数只在调用 `reader_tts_create` 的线程上有效；其它线程得到 `READER_TTS_OWNER`，句柄状态不变 |
| 后端线程 | 包内一条 worker 线程独占全部 COM／SAPI 对象（`ISpVoice`、voice token 枚举、WAV sink），用 MTA 初始化；宿主不需要消息循环 |
| 回调 | 不存在回调通道。SAPI 事件只写有界内部队列，宿主用 `reader_tts_poll` 取纯值；worker 从不调用宿主 |
| 文本 | `reader_tts_speak` 复制输入，返回后调用者缓冲可释放；副本保留到该请求终态 |
| 声音列表 | `reader_tts_voice_list` 里的字符串归列表所有，`reader_tts_voice_list_free` 释放；不需要句柄存活，且可重复调用（含 NULL） |

## 状态机

```
create -> INITIALIZING -> READY | SERVICE_UNAVAILABLE
READY -> SPEAKING -> PAUSED -> SPEAKING ...
SPEAKING/PAUSED -> READY            （收到该请求终态）
任意状态 -> CLOSING -> CLOSED        （reader_tts_request_close）
```

| 调用 | 前置状态 | 结果 |
| --- | --- | --- |
| `reader_tts_voices` | READY/SPEAKING/PAUSED | OK；INITIALIZING/SERVICE_UNAVAILABLE → UNAVAILABLE；CLOSING/CLOSED → ARGUMENT |
| `reader_tts_speak` | READY 且无活动请求 | OK；有活动请求 → BUSY；未就绪 → UNAVAILABLE；CLOSING/CLOSED → ARGUMENT |
| `reader_tts_pause` / `resume` | 活动请求且状态匹配 | OK；请求 id 不匹配或状态不符 → ARGUMENT |
| `reader_tts_stop` | 活动请求 | OK，并恰好产生一个 STOPPED；否则 ARGUMENT |
| `reader_tts_observe` / `poll` | 任意 | OK；poll 无事件时 `available=0` 并清空 event |
| `reader_tts_request_close` | 任意 | OK，非阻塞、幂等；活动请求得到 STOPPED |
| `reader_tts_destroy` | CLOSED | OK 并置 NULL；之前 → BUSY 且保留指针；空指针 → ARGUMENT |

## 请求、错误与取消

- `request_id` 非零且在同一句柄上严格递增；被拒绝的调用不消耗 id。同一时刻只允许一个活动请求，
  未停止就替换返回 `BUSY`，不静默打断。
- start/终态：每个被接受的请求恰好一个 `READER_TTS_STARTED` 与一个终态
  （`FINISHED`／`STOPPED`／`FAILED`）。stop 或 close 被接受后，队列里只会有该请求那一个
  `STOPPED`；迟到事件没有路径污染新请求。
- 暂停中的 stop：`ISpVoice::Pause` 是**持续的声音状态**，`Speak` 与 purge 都不会清除它，
  所以在 PAUSED 上被接受的 stop 会先 `Resume` 再 purge，把引擎留在可朗读状态；否则下一个
  请求会被送进一个仍然暂停的引擎，永远到不了终态（接真实音频端点时表现为挂住）。
- `speak` 返回错误表示请求没有启动，因此不产生事件。
- `reader_tts_error.native_code` 在失败来自 SAPI/COM 时是原始 HRESULT，否则为 0。

## 文本、范围与硬上限

| 项 | 规则 |
| --- | --- |
| `max_utf8_bytes` | 0 表示默认 16384；硬上限 16384，之上 → ARGUMENT；更小的值只降低本句柄上限 |
| 超长文本 | `READER_TTS_LIMIT`，由宿主分块、每块用新 request id；不静默截断 |
| UTF-8 | 严格校验：拒绝嵌入 NUL、不完整 scalar、过长编码、代理区、U+10FFFF 以上 → ARGUMENT |
| RANGE | `start/end` 是本次输入文本的 **UTF-8 字节偏移**：引擎当前词位置（`ISpVoice::GetStatus` 的 `ulInputWordPos`/`ulInputWordLen`，即它正在朗读的 UTF-16 码元区间）经每请求映射表严格换算，即使落在代理对中间也只会得到字节边界。位置是采样来的、不是时钟推算：短于轮询间隔的词可能被跳过，相邻范围可能被合并。范围单调、落在 `[0, bytes)` 内；越界位置直接 `FAILED`+`IO`，不钳位成"看起来合理"的值 |
| 队列 | 最多 128 事件，其中 RANGE 最多 112；相邻（间隔 ≤1 字节空白）范围合并而不是增长队列；容量耗尽时 `poll`/`speak` 返回 `LIMIT`，句柄须关闭 |
| 事件来源 | worker 用 `ISpEventSource::GetEvents` 取引擎事件；该 vtable 逐条写入 **`SPEVENT`**（扩展的 `SPEVENTEX` 只属于 `ISpEventSource2::GetEventsEx`），包内按同一 stride 读取，批量取回的第 2 条及之后不会被错位解读 |

## 速度与声音

- `rate` 为 0.5..2.0 的有限值（NaN/±inf → ARGUMENT）。Windows 映射到 SAPI 的 -10..10：
  `round(log2(rate) * 10)`，每个请求在选好声音之后用 `ISpVoice::SetRate` 下发给引擎
  （换 token 会把速率重置成该 token 的默认值，所以顺序不能反）；`SetRate` 失败即
  `READER_TTS_IO` + 原始 HRESULT，请求不启动。这是引擎偏好，不是精确时长比例，头文件不作
  时长承诺；实测同一段 200 字节文本 0.5 → 40 032 ms、2.0 → 4 353 ms（约 9.2 倍）。
- `voice_id` 为 NULL 或空串使用系统默认；非空 id 必须是 `reader_tts_voices` 返回的 id 之一，
  否则 ARGUMENT。id 是 SAPI token id 的 UTF-8 形式，`language` 尽量给出 BCP-47 标签
  （token 的 `Language` 是十六进制 LCID 时用 `LOCALE_SNAME` 换算）。
- 能力位按实际能力动态给出：`READER_TTS_CAN_PAUSE` 在 READY 后始终可用；`READER_TTS_CAN_REPORT_RANGE`
  **只在该句柄真的收到过引擎词位置之后**才置位。Windows Server 2022 上把 SAPI 输出到 WAV 文件
  （无音频端点）时，引擎既不产生 word-boundary 事件（`GetEvents` 返回 S_FALSE），也不更新
  `GetStatus` 的 `ulInputWordPos/ulInputWordLen`，因此这条路下 RANGE 不置位、也不伪造进度；
  UTF-16→UTF-8 的字节换算由包内 `reader_tts_windows_debug_map_utf16` 覆盖（见验收）。

## 构建、安装与消费

```
cmake -S extras/reader-tts-windows -B build/module -G Ninja -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_INSTALL_PREFIX=<prefix>
cmake --build build/module
cmake --install build/module
# 消费者只依赖安装前缀
cmake -S tests/reader_tts_windows/consumer -B build/consumer -G Ninja \
      -DCMAKE_PREFIX_PATH=<prefix>
```

安装产物：`include/reader_tts.h`、`include/reader_tts_windows.h`、`lib/reader_tts.lib`、
`lib/cmake/EXReaderTTSWindows/*`、`share/exreader-tts-windows/LICENSE.txt`。
默认 SDK／reading-core 构建永远不加入本组件；SAPI 只通过安装后的包暴露。

## Windows 专有附加（`reader_tts_windows.h`）

- `reader_tts_windows_set_wav_output(handle, path)`：把后续请求的合成结果写到 WAV，
  走同一条 SAPI speak 路径，因此没有声卡的机器也能验证"真的合成了语音"。状态必须 READY
  （有活动请求 → BUSY）；文件在该请求终态之前已完整关闭。
- `reader_tts_windows_debug_*`：包内验收用的分配失败注入、活分配计数、无服务模拟与初始化延迟。
  宿主不得调用。

## 限制与未覆盖范围

- 自动化只能验到"真实 SAPI 语音渲染出的 PCM WAV 非空、时长与格式正确、事件流正确"；
  **听感判断**与**物理音频设备播放**不在本包证据内（runner 无音频端点）。
- 机器上没有任何 SAPI voice token 时句柄停在 `SERVICE_UNAVAILABLE`，不会用 mock 冒充朗读成功；
  Actions 里 `evidence/sapi-voices.txt` 记录了 runner 的真实声音清单。
- 宿主接线、朗读 UI、分块策略（何时切块、块大小）由 root 在共同源码里做。
- 共享实现缺陷（若有）只交最小复现与建议补丁，不越界修改 SDK、宿主或其它包。
## 云端验收（审阅轮同源工件，2026-10-25）

| 项 | 值 |
| --- | --- |
| 受测源码 | `a83540121859594f8d6a83b58f68064919bcd394`（分支 `codex/reader-tts-windows-review`；交付起点 HEAD `242f07c9`，原始受测源 `62fd2967`） |
| 运行 | run `40169432864` attempt 1（push）结论 success；作业 `tts (windows-2022)` #121097093329、`same-source report` #121097267373 |
| 运行器 | windows-2022 · Windows Server 2022 Datacenter x64 · ImageOS win22 · ImageVersion 20261022.344.1 · CMake 3.31.6 · 编译器取自 runner 的 vcvars64（`logs/compiler.log`） |
| 逐项检查 | 222 / 222 通过（basic 45、speak 30、unicode 18、limits 27、control 33、chunks 25、overflow 9、service 7、memory 17、close 11），逐项具名 pass/fail 见 `evidence/logs/*.stdout.log` |
| 夹具正反例 | 21 个（1 正例 strict + 1 同运行正例 + 19 个反例，含新增 `reject.report_capability_range`） |
| 生产者工件 | id 12589298424 · 6 660 681 B · `sha256:85ac766ecf5b30e7748564e0ba5bdbd707976ab73b27719cd07458cb61618ccb` · 有效至 2027-01-23T06:32:14Z |
| 汇总工件 | id 12589063763 · 1 940 B · `sha256:38375b7e1577b4ef7d46095fa2ecb7269de699bcf658e10d78768d3f7d84e536` · 有效至 2027-01-23T06:32:14Z |
| 严格复核 | dispatch run `40169574507`（作业 `retrospective verification` #121097506639，checkout `a8354012`）：在 Actions 内重新下载两个 ZIP、重算摘要、绑定生产者日志（`709de5d6…3384`，汇总作业日志 `43d2a143…0028`）、复核 10 个 WAV 容器（9 条 wavfile 声明 + probe.wav）、8 个安装文件与消费者/探针摘要，accepted=true；复核工件 id 12589093822 · 6 689 947 B · `sha256:b2ddc5edf42b855b20524fe899875a5e8edc68c06ad0e051aab414a890d75a7a` · 有效至 2027-01-23T06:34:36Z |
| 报告身份 | `evidence/report.json` `sha256:8f11e194…d8a689`；同运行汇总 `aggregate.json` `sha256:248145a8…3c7ac2085` |
| 消费者 | C `tts-consumer.exe` `sha256:ab5970f77d042dc0392951ec06cec066084c2b60ad78043d5692cf533f21264b`；C++ `tts-probe.exe` `sha256:8477ad0b1baa6d18b33d0805ba6fa4735e9d5959e6d6c835577de0f5e9fa66ca`（两者均只链接安装后的包；MSVC 每次构建嵌入时间戳，故逐运行绑定） |
| 安装树 | 8 个文件：两个头、`lib/reader_tts.lib`、四个 CMake 包文件、许可证 |

真实合成（同一条 SAPI 路径写出 16 bit/22 050 Hz/单声道 PCM，10 个文件全部由验收器重算容器）：

| 文件 | 字节 | 时长 | 说明 |
| --- | ---: | ---: | --- |
| speak.wav | 1 092 808 | 24 779 ms | 400 B 文本，rate 1.0 |
| unicode.wav | 248 934 | 5 643 ms | CJK+emoji+组合符+RTL |
| chunk0/1/2.wav | 1 366 494 / 1 371 266 / 1 364 864 | 30 985 / 31 093 / 30 948 ms | 各 1 000 B，rate 1.5（速率生效后比原交付的 62.5 s 快约 2 倍） |
| rate-slow.wav | 1 765 460 | 40 032 ms | 200 B，rate 0.5（SAPI -10） |
| rate-fast.wav | 192 040 | 4 353 ms | 同一 200 B，rate 2.0（SAPI +10） |
| voice.wav | 188 076 | 4 263 ms | 60 B，显式选择 `reader_tts_voices` 里的真实 token |
| control-after-paused.wav | 578 936 | 13 126 ms | 在 PAUSED 上 stop 之后的下一请求，rate 1.0 |
| probe.wav | 529 252 | 12 000 ms | 独立 C++ probe，rate 1.25 |

同一段 200 B 文本 0.5 与 2.0 的实测比约 9.2 倍，与 `round(log2(rate) * 10)` 的 ±10 档一致；
`speak.rate.applied` 用这两个文件的字节数直接比较（慢 ≥ 1.5 × 快）。

运行器上真实存在两个 SAPI 声音（Microsoft David/Zira Desktop），清单见工件 `evidence/sapi-voices.txt`。

### 本轮审阅修复（全部有实现依据，逐条注明可观测性）

1. **`rate` 从不下发到引擎**（真实缺陷，已被具名反例抓住）：`reader_tts_speak` 校验并保存了
   `rate`，worker 从未调用 `ISpVoice::SetRate`，所有请求都以声音默认速率朗读。未修复的 worker
   在 run `40169117214` 上让 `speak.rate.applied` 失败（speak 阶段 29/30）；修复后在 run
   `40169432864` 上 30/30。
2. **`GetEvents` 步长错位**：缓冲区声明为 `SPEVENTEX[8]` 却按 `SPEVENT` 的 vtable 语义接收、
   又以 `SPEVENTEX` 的下标读取，批量取回的第 2 条及之后事件的 id/wParam/lParam 全部错位。
   已改为 `SPEVENT[8]`。本 runner 的 SAPI 文件输出只返回很少的事件，报告里 `engine_event_total`
   仅作诊断，因此这一条**不声称在本 runner 上被批量路径执行**。
3. **PAUSED 状态下的 stop 会把引擎留在暂停**：`ISpVoice::Pause` 是持续状态，`Speak`/purge 都不清除，
   于是下一个请求会进入一个暂停的引擎、永远到不了终态（真实音频端点上的挂住）。现在 stop 在
   purge 前先 `Resume`。文件 sink 下 `Pause` 不产生可观察的推进差，因此本 runner 只能验证
   状态机与"stop 之后的下一个请求仍能到达终态"（`control.after_paused.*`），**不声称已验证挂起复现**。
4. **证据不得超前于观测**：`evidence/report.json` 里的 `capabilities` 原先硬写
   `{"pause": true, "range": true}`，而同一份报告实测 `range_events=0`、能力位为 0 并在
   `not_exercised` 里自认没有词位置。现在按实测给出（本 runner：`pause=true, range=false`），
   严格复核新增 `report_capability_range` 规则与对应反例。
5. **新增覆盖**：引擎事件源确实被查询（`speak.engine_event_source`）、真实 voice id 被接受并完成
   （`speak.voice.explicit`）、暂停中 stop 的状态机与后续请求、rate 的时长对照。
   失败时 job 日志直接列出失败具名检查（`failing_checks`），不再必须解包工件才知道红在哪。

### 本环境未覆盖

- 听感判断、物理音频设备播放（runner 无音频端点，全部合成走包内 WAV sink）。
- 引擎 RANGE 事件：该 runner 上 SAPI 把语音写到文件时既不产生 word-boundary 事件
  （`GetEvents` 返回 S_FALSE），也不更新 `GetStatus` 的词位置，因此能力位按设计保持清除，
  报告里的 `capabilities.range` 也如实为 false；UTF-16→UTF-8 的字节换算由
  `reader_tts_windows_debug_map_utf16` 的 6 个具名用例覆盖（ASCII、双字节、CJK、代理对、
  混合、非法 UTF-8）。接真实音频端点后需重跑 RANGE 覆盖。
- 批量事件读取：见上第 2 条，按 SAPI vtable 语义修复，未在本 runner 上被批量路径执行。
- 暂停期间的音频推进与"暂停中 stop 后引擎是否仍停住"：文件 sink 比实时快得多，观察不到推进差。
- 宿主接线、朗读 UI 与分块策略由 root 在共同源码里做。

### 保留的原始失败

- 原始交付的 22 个失败运行（编译、事件 sink 的 0xC0000005、无声明的词位置、harness/夹具自身缺陷等）
  全部保留在 Actions 历史里，逐条 id 见 `docs/validation/reader-tts-windows.json` 的 `original_failures`。
- 本轮审阅的 3 个失败运行同样保留：`40168657049`（新增检查漏声明 `status`，编译失败）、
  `40168902079`（未修复 worker 上 speak 阶段 29/30，失败项当时未具名）、`40169117214`
  （同一失败被具名成 `speak.rate.applied`）。没有删除断言、换语料或把真实失败改成预期。