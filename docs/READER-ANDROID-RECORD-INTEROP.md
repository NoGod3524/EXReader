# Android 真实阅读记录转运出口

状态：Android 实际 sender 与完整父图回读已通过；Apple incoming 和双向互通仍待验收。

固定起点 `1b3cfd1413fa5ebade31be6958f835f6de3b5290`，独立分支 `codex/reader-android-record-interop`。生产 policy 只原样接入 `b1a7b7891cd394671842164a07a86c8e316dace3` 的 `ReadingParserPolicy.java`、`NativeReadingSdk.java`、`NativeCbz.java`，Actions 逐 blob 核对；没有合并其 Apple 树。SDK、formatter、wire、schema 和主题实现不改。

根协调器批准的三个显式 review-only 钩子为 Gradle 默认关闭参数/Debug source set、CMake Debug-only define/include、现有 `catalog_jni.cpp` 末尾条件 include。新探针只在现有 `product_jni::call` owner 上调用公开 `reader_revision_get/outbox`，读取已经提交的完整字节，并记录 owner/thread/provider 绑定；不另开 store，不访问产品 SQL，不增加生产通用 Java API。Release 扫描拒绝 probe 类与 JNI 符号。

实际 app 进程用原 `BookStore` 单一 worker，实际可见 TXT、有界 EPUB、PDF、CBZ 页面和 `NativeReadingSdk`/当前 `NativeCbz` renderer 捕获，`NativeReadingProduct` 原公开命令写入进度/书签及非空文本范围的 highlight。每种进度写两版，保留真实父边；通过公开 retained/outbox 导出四份 book wire、十五份 reading wire，共十九份完整原始 revision，以及四份公开 SDK 原件。选定的十一条记录登记真实解码 capture，保留 `exreader-sdk-3.41.0` 写法，不重新编码任何 wire。

转运契约见 [CONTRACT.json](../tests/reader_android_record_interop/CONTRACT.json)：manifest schema1，Android sender 登记实际安装 APK、实际加载唯一 SDK DSO、source/run/attempt、真实 `exr_version`；macOS 使用实际 executable 的 `program_sha256` 与实际加载 `sdk_dso_sha256`，不要求虚构 APK。originals 登记 role/file/format/book_key/bytes/sha256；revisions 登记精确原 wire 文件/id/entity/parents/bytes/sha256；reading_records 登记实际 revision、role/kind/mode/anchor_version 与 numbers/route/base64 selectors。null 与空字节保留区别。

sender 后使用另一个全新实际进程接收同一原始子 wire 但暂缺其真实祖先，要求 public typed record 为 PENDING、不泄露可解析 capture；完整原始祖先到齐后才允许 FOUND。该负例属于协议/原始 Android 数据回读，不授予 Apple 互通。未知 prefix、未来 parser、不同原件另做实际宿主拒绝，公开 resolve 前后核对 SDK 进度/笔记和 outbox 字节不变。

Apple incoming 接口准备接收同结构、真实 macOS sender 的 bare `3.41.0` 包；原字节逐份 `reader_revision_receive`，原 retained 字节逐份核对，然后实际 `NativeReadingProduct` 读取与 SDK/current CBZ resolve/recapture。缺图或 parser 替换夹具不得授予。未获得 root 的真实 Apple bundle/API 工件证明前，incoming 明确 pending，双向互通 false。3.40 原地升级/降级另列，本包不伪造旧 SDK 进程。

原 130 项同源回归与严格原 ZIP/原像素认证全部保留；新增 sender 与真实缺父回读共 8 项。所有构建、语法检查、夹具、运行、工件下载/解包/解析仅 Actions。

## 云端证据

受测源码 `b93b4a2f9ac24d7d0fc4d48c917dae11bec4baf7`，[run 40181402323](https://github.com/NoGod3524/EXReader/actions/runs/40181402323) / attempt 1。Android producer `121133053868` 与 strict summary `121137003411` 同次 success，原 130 项加 sender/缺父补齐 8 项，共 **138/138**。strict 重新下载原 ZIP，核对 API 大小、digest、有效期、source/attempt、成功 producer、实际安装 APK 与实际加载 SDK 字节，再执行原像素验证和完整图/capture 核对。

| 工件 | ID | ZIP 字节 | SHA-256 |
| --- | ---: | ---: | --- |
| 完整 producer | 12594881802 | 133515330 | `73c69ed40adaf122d4cc5e8adc693ead2147befd92c0c0d98a8dd3aac3e61af0` |
| 实际转运 packet | 12594712144 | 16615 | `08ce264db1a6e6083e15ddd20a60f6f088b7d82afe24e4d44aa8681e6551cac3` |
| strict summary | 12593694660 | 1658 | `db82485a4f3a1055a33fbf94e9ffa48a19361b43e13bfc7de62f0847ec9c133a` |

三份工件有效期均为 `2027-01-23T09:37:20Z`。完整 producer 沿用 `reader-android-page-theme-40181402323-1` 名称以原样复用旧 strict；packet 名为 `reader-android-record-bundle-40181402323-1`，ZIP 根为 `manifest.json`、`originals/`、`revisions/`。manifest SHA-256 为 `7628affd6e5ec37e748c9d09c57d5f50090c4060bbdd080b9800b45930829bbf`。

实际 packet 含四份 SDK 原件、十九份原 wire（4 book、8 progress、4 bookmark、3 highlight）和十一条选定 reading records；四种格式均有真实 progress/bookmark point，TXT、EPUB 和有公开文本的 PDF 有非空 range/highlight。全新第二 app 进程实测缺真实父时 PENDING/capture null，原始父图补齐后 SAFE/FOUND，outbox 不增加。

实际 APK SHA-256 为 `eea5de2867e147f0a3a9418c0bfbf2e574bdaa18226ffa02340ed94fb549476e`；实际 SDK DSO SHA-256 为 `a345ab4c1def2e864a76b9e879da8a372e8821ad09b7991c8fe4e04626b2e8ac`。进程报告 SDK `3.41.0`、parser `exreader-sdk-3.41.0`，owner `1`、native thread `128492123438320`、Java thread `exr-host-worker`。SDK 实际加载自安装 APK 的 `lib/x86_64/libexreader.so`，revision 与 command provider 均为同 APK 的 `lib/x86_64/libexreader_product.so`。

授予范围为 API34 `default` x86_64 模拟器上的 Android sender export、真实缺父/补图回读与原 130 项同源回归。`sender_export_accepted=true`、`inherited_130_accepted=true`；完整互通顶层 `accepted=false`、`incoming_apple_status=pending`、`bidirectional_interoperability_accepted=false`。真机、性能、3.40 原地升级/降级与完整产品未授予。
