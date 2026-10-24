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

## 速度与声音

- `rate` 为 0.5..2.0 的有限值（NaN/±inf → ARGUMENT）。Windows 映射到 SAPI 的 -10..10：
  `round(log2(rate) * 10)`。这是引擎偏好，不是精确时长比例，头文件不作时长承诺。
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
