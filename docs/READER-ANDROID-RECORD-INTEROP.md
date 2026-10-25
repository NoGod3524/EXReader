# Android 真实阅读记录转运出口

状态：首轮云端验收待执行。尚未授予 Android sender 或 Android⇄Apple 互通。

固定起点 `1b3cfd1413fa5ebade31be6958f835f6de3b5290`，独立分支 `codex/reader-android-record-interop`。生产 policy 只原样接入 `b1a7b7891cd394671842164a07a86c8e316dace3` 的 `ReadingParserPolicy.java`、`NativeReadingSdk.java`、`NativeCbz.java`，Actions 逐 blob 核对；没有合并其 Apple 树。SDK、formatter、wire、schema 和主题实现不改。

根协调器批准的三个显式 review-only 钩子为 Gradle 默认关闭参数/Debug source set、CMake Debug-only define/include、现有 `catalog_jni.cpp` 末尾条件 include。新探针只在现有 `product_jni::call` owner 上调用公开 `reader_revision_get/outbox`，读取已经提交的完整字节，并记录 owner/thread/provider 绑定；不另开 store，不访问产品 SQL，不增加生产通用 Java API。Release 扫描拒绝 probe 类与 JNI 符号。

实际 app 进程用原 `BookStore` 单一 worker，实际可见 TXT、有界 EPUB、PDF、CBZ 页面和 `NativeReadingSdk`/当前 `NativeCbz` renderer 捕获，`NativeReadingProduct` 原公开命令写入进度/书签及非空文本范围的 highlight。每种进度写两版，保留真实父边；通过公开 retained/outbox 导出四份 book wire、十五份 reading wire，共十九份完整原始 revision，以及四份公开 SDK 原件。选定的十一条记录登记真实解码 capture，保留 `exreader-sdk-3.41.0` 写法，不重新编码任何 wire。

转运契约见 [CONTRACT.json](../tests/reader_android_record_interop/CONTRACT.json)：manifest schema1，Android sender 登记实际安装 APK、实际加载唯一 SDK DSO、source/run/attempt、真实 `exr_version`；macOS 使用实际 executable 的 `program_sha256` 与实际加载 `sdk_dso_sha256`，不要求虚构 APK。originals 登记 role/file/format/book_key/bytes/sha256；revisions 登记精确原 wire 文件/id/entity/parents/bytes/sha256；reading_records 登记实际 revision、role/kind/mode/anchor_version 与 numbers/route/base64 selectors。null 与空字节保留区别。

sender 后使用另一个全新实际进程接收同一原始子 wire 但暂缺其真实祖先，要求 public typed record 为 PENDING、不泄露可解析 capture；完整原始祖先到齐后才允许 FOUND。该负例属于协议/原始 Android 数据回读，不授予 Apple 互通。未知 prefix、未来 parser、不同原件另做实际宿主拒绝，公开 resolve 前后核对 SDK 进度/笔记和 outbox 字节不变。

Apple incoming 接口准备接收同结构、真实 macOS sender 的 bare `3.41.0` 包；原字节逐份 `reader_revision_receive`，原 retained 字节逐份核对，然后实际 `NativeReadingProduct` 读取与 SDK/current CBZ resolve/recapture。缺图或 parser 替换夹具不得授予。未获得 root 的真实 Apple bundle/API 工件证明前，incoming 明确 pending，双向互通 false。3.40 原地升级/降级另列，本包不伪造旧 SDK 进程。

原 130 项同源回归与严格原 ZIP/原像素认证全部保留；新增 sender 与真实缺父回读共 8 项。所有构建、语法检查、夹具、运行、工件下载/解包/解析仅 Actions。
