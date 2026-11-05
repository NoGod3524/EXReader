# J16–J19：朗读共同行为与接口

四个平台包独立实现同一组C ABI；宿主按平台只链接一个后端。**不创建统一动态插件框架**。各包安装同名 `reader_tts.h`，宏 `READER_TTS_VERSION "0.1.0"`；包/target分别命名 `EXReaderTTSWindows::reader_tts`、`EXReaderTTSApple::reader_tts`、`EXReaderTTSAndroid::reader_tts`、`EXReaderTTSLinux::reader_tts`。Android可加Java外观，但C/JNI契约不能另造一套状态语义。

## 共同C ABI

下面是必须采用的接口形状；实现可在自有头补注释和include guard，不增改这些字段/枚举含义。独立错误/能力状态不依赖SDK版本。

```c
#include <stddef.h>
#include <stdint.h>
#define READER_TTS_VERSION "0.1.0"
typedef struct reader_tts reader_tts;
typedef enum {
  READER_TTS_OK=0, READER_TTS_ARGUMENT, READER_TTS_OWNER,
  READER_TTS_BUSY, READER_TTS_UNAVAILABLE, READER_TTS_UNSUPPORTED,
  READER_TTS_IO, READER_TTS_MEMORY, READER_TTS_LIMIT
} reader_tts_status;
typedef enum {
  READER_TTS_INITIALIZING=0, READER_TTS_READY, READER_TTS_SPEAKING,
  READER_TTS_PAUSED, READER_TTS_STOPPING, READER_TTS_CLOSING,
  READER_TTS_CLOSED, READER_TTS_SERVICE_UNAVAILABLE
} reader_tts_state;
typedef struct { size_t struct_size, max_utf8_bytes; } reader_tts_config;
typedef struct { reader_tts_status code; int native_code; } reader_tts_error;
typedef struct { char *id, *name, *language; } reader_tts_voice;
typedef struct { reader_tts_voice *voices; size_t count; } reader_tts_voice_list;
enum { READER_TTS_CAN_PAUSE=1, READER_TTS_CAN_REPORT_RANGE=2 };
typedef struct {
  reader_tts_state state;
  reader_tts_status last_status;
  uint64_t request_id;
  unsigned capabilities;
} reader_tts_snapshot;
typedef enum {
  READER_TTS_STARTED=0, READER_TTS_RANGE, READER_TTS_FINISHED,
  READER_TTS_STOPPED, READER_TTS_FAILED
} reader_tts_event_kind;
typedef struct {
  uint64_t request_id;
  reader_tts_event_kind kind;
  reader_tts_status status;
  size_t start, end;
  int has_range;
} reader_tts_event;
reader_tts_status reader_tts_create(const reader_tts_config *, reader_tts **, reader_tts_error *);
reader_tts_status reader_tts_voices(reader_tts *, reader_tts_voice_list *, reader_tts_error *);
void reader_tts_voice_list_free(reader_tts_voice_list *);
reader_tts_status reader_tts_speak(reader_tts *, uint64_t request_id,
  const char *utf8, size_t bytes, const char *voice_id, double rate, reader_tts_error *);
reader_tts_status reader_tts_pause(reader_tts *, uint64_t request_id, reader_tts_error *);
reader_tts_status reader_tts_resume(reader_tts *, uint64_t request_id, reader_tts_error *);
reader_tts_status reader_tts_stop(reader_tts *, uint64_t request_id, reader_tts_error *);
reader_tts_status reader_tts_observe(reader_tts *, reader_tts_snapshot *, reader_tts_error *);
reader_tts_status reader_tts_poll(reader_tts *, reader_tts_event *, int *available, reader_tts_error *);
reader_tts_status reader_tts_request_close(reader_tts *, reader_tts_error *);
reader_tts_status reader_tts_destroy(reader_tts **, reader_tts_error *);
```

## 必须一致的语义

- `create`可返回INITIALIZING，不代表语音已就绪；初始化失败进入SERVICE_UNAVAILABLE。只有实际后端就绪才能开始。所有操作在创建owner上使用，平台要求主线程时明确写在头注释；宿主负责运行对应原生event loop。
- `max_utf8_bytes=0`使用16KiB，上限16KiB；参数仅能降低。严格UTF-8、拒绝嵌入NUL和不完整scalar；`speak`复制输入，不借用调用者缓冲。超长文本由宿主分块，不能静默截断；各块使用新request_id。
- request_id非零，由宿主分配；同handle生命周期不得重用。一次只允许一个活动请求；未停止就替换返回BUSY，不能静默打断。voice_id为空使用系统当前可用默认声音，未知ID明确拒绝；rate为有限的0.5..2.0相对速率，平台映射写明，不能声称精确音频时长比例。
- 不在系统回调里调用宿主。回调只写有界内部队列；宿主用`poll`取拥有纯值的事件。最多128事件，连续RANGE可合并，STARTED和终态不能丢；无可用事件令available=0并清空event。容量不足要显式失败，不能泄漏或无界排队。
- RANGE可用才设能力位，start/end为**本次输入的UTF-8字节边界**；系统UTF-16偏移须严格转换。不能用猜测的时钟位置伪造range。缺少原生pause能力返回UNSUPPORTED且状态不变。
- stop对当前请求明确停止；每个成功启动的请求恰好一个FINISHED/STOPPED/FAILED终态。迟到回调仍须保留原ID，不能污染新请求。回调不能包含原文或秘密错误字符串。
- request_close非阻塞且幂等；关闭停止活动请求，真正解除回调/系统资源后才为CLOSED。destroy在CLOSED前返回BUSY并保留指针；成功后置NULL。释放voices不要求保持原handle存活。
- 输出、内存失败、错owner、关闭时及未知voice的规则必须测试。每个平台回交真实能力位；连接或初始化成功不等于朗读成功。自动化没有听感判断，音频输出/回调/真实设备分别写范围。

若本冻结接口与原生能力存在不可实现冲突，交root具体调用证据与最小建议，不私自改成另一个ABI；可继续完成其它不依赖的部分。

