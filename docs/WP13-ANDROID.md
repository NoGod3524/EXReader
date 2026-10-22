# WP13 Android 原生宿主

本包交付 Android 原生参考阅读应用、独立的 SDK/JNI/app 云端构建和模拟器验收。
实现基线为 `a2552d7feb786cd2345d2b0b3eb894777b3254db`，分支 `codex/wp13-android`。
只消费安装后的公开 SDK；`bindings/jni/**` 保持只读，书库、选择器和标注由
`examples/android/app/src/main/cpp/exreader_host_jni.c` 这一小型本地桥接提供。

## 范围与边界

- 阅读重排 EPUB（以及 TXT/HTML/FB2/DOCX/RTF/MOBI 的同一重排入口）与固定页 PDF/CBZ。
- 系统文件选择器导入、应用私有副本、SQLite 书库、重复导入复用、32 MiB 宿主上限。
- 重排分页/翻页、字号、PDF 缩放、触摸命中、文字选择与复制、标注增改删和跳转。
- 书库、进度和标注持久化；旋转、Activity 重建、后台/前台、进程终止重启恢复。
- 重排锚点进度与固定页页码分别保存；歧义锚点明确报告并回退到已存偏移。
- 每行文本作为虚拟无障碍节点，控件具有稳定资源 ID 和可访问名称。

不计入本包：OPDS、迁移、TTS、OCR、真机安装/签名、TalkBack 真人验收、其他平台宿主。
`physical_device_execution=false`；全部验收在云端 x86_64 模拟器执行。

## 构建与版本固定

| 项目 | 固定值 |
| --- | --- |
| SDK / core / 书库 schema | 3.40.0 / 3.39.0 / 6 |
| ABI epoch | 1 |
| NDK | 27.0.12077973 |
| CMake | 3.22.1 |
| AGP / Gradle / JDK | 8.6.1 / 8.9 / 17 |
| compileSdk / minSdk / targetSdk | 35 / 26 / 35 |
| 打包 ABI | x86_64（模拟器实际加载的库） |
| 模拟器 | API 34，x86_64，default 镜像 |

`tools/build_android_host.py` 交叉编译并安装 Android x86_64 SDK（书库、PDF、JNI
开启；WebP/TIFF/AVIF/PDF 密码/AAC 关闭），把带 `SOVERSION` 的引擎运行时改写为
`libexreader.so`（patchelf），随后由 Gradle 的 `externalNativeBuild` 用安装后的
`EXReader::exreader` 构建本地桥接，并打包 APK。字体为固定 SHA-256 的
Noto Sans CJK SC（OFL），随 APK 分发。

`tools/check_android_host.py` 做源码/所有权静态检查，并在云端证据目录存在时校验
逐 case JSON、截图、原生日志、APK 散列、ABI/API 与 run 身份。

## 结构与生命周期

- `MainActivity`：单 Activity，书库/阅读/标注三个面板；所有 SDK 句柄只在唯一的
  `exr-host-worker` 线程打开、使用和关闭，UI 线程只接收不可变 `PageSnapshot`。
- `ReflowSession`：`EXReader.Document` + `Pager` + 字体；每次 `next()` 后立即渲染、
  取布局快照并关闭 `ReflowPage`；切书、旋转、取消时由代际计数丢弃旧结果。
- `FixedSession`：固定文档按页渲染，位图与文本快照独立于原生页句柄。
- `NativeLibrary`/`BookStore`：本地 JNI 只封装 `exr_library_*`、`exr_fixed_note`、
  `exr_anchor_create` 等公开接口；失败转换为 Java 异常，UI 层捕获后显示状态。
- 导入：`ACTION_OPEN_DOCUMENT` → 取得持久 URI 权限（尽力）→ 64 KiB 分块复制到
  `files/books/<sha256>.<ext>`，分块间轮询取消 → 打开校验 → `import_file_unique`。
  原书字节同时由 SDK SQLite 保存，重开不依赖临时 URI 授权。
- 进度：重排保存点选择器（`exr_library_progress`）和数值偏移；固定页保存页码。
  非 `FOUND` 状态会显示 `Saved position is not exact (state N)` 并回退。
- 标注：重排用文档偏移，固定页用页内 UTF-8 偏移；SDK 负责捕获稳定选择器，
  列表从 SQLite 回读。标注导航按偏移/页码重新定位。

## 验收矩阵

云端 walkthrough 由独立的自仪器化测试 APK 驱动真实输入（`UiDevice` 点击、滑动、
旋转、Home、force-stop），逐 case 写 JSON 并截图；见
`examples/android/uitest/src/androidTest/java/org/exreader/host/uitest/HostWalkthroughTest.java`。

| # | case | 覆盖 |
| --- | --- | --- |
| 1 | cold_start_shelf | 冷启动空书架、SDK 身份 |
| 2 | picker_cancel | 系统选择器取消 |
| 3 | import_epub | 系统导入 EPUB、书架行 |
| 4 | open_epub | 打开、首屏、状态 |
| 5-6 | page_next / page_prev | 前后翻页 |
| 7-8 | font_increase / font_decrease | 重排字号 |
| 9-10 | touch_select / copy_selection | 触摸选择与复制 |
| 11-14 | note_add / notes_read / note_edit / note_navigate | 标注增、读、改、导航 |
| 15-17 | rotate_landscape / rotate_portrait / activity_rebuild | 旋转与 Activity 重建 |
| 18 | background_resume | 后台/前台 |
| 19-21 | process_restart_reflow / notes_after_restart / note_delete | 进程重启恢复、标注删除 |
| 22-23 | import_txt / open_txt | 其他重排格式 |
| 24-32 | PDF 导入、打开、翻页、缩放、选择复制、标注、重启、删除 | 固定页闭环 |
| 33-35 | bigchapter 导入/打开/翻页 | 单章约 2 MiB 路径 |
| 36-37 | import_ambiguous / ambiguous_restore | 歧义锚点回退 |
| 38-40 | corrupt_import / retry_import / duplicate_import | 格式错误、重试、重复 |
| 41-42 | too_large / cancel_large_import | 32 MiB 上限、导入取消 |
| 43 | book_switch | 切书与旧结果隔离 |
| 44 | accessibility_semantics | 控件/文本行可访问名称 |
| 45 | native_metrics | 页字节/耗时日志、句柄开关 |

## 证据

云端 workflow：`.github/workflows/wp13-android.yml`（仅本分支路径与手动触发）。
运行后证据位于该次 artifact：

- `build/android-host/build.json`：SDK/NDK/CMake/Gradle/AGP 版本、字体与夹具散列、
  APK 散列、ELF 机器与 16 KiB 对齐。
- `evidence/instrumentation.txt`、`evidence/logcat.txt`。
- `evidence/device/validation.json` 与 `evidence/device/cases/*.json`：逐 case 状态、
  时长、截图路径；`evidence/device/shots/*.png`。
- `evidence/artifacts/*.apk`：可安装的 debug APK 与测试 APK。

仓库内汇总：`docs/validation/wp13-android.json`（由 `check_android_host.py` 合并，
仅在全部 case 通过且 ABI/API/散列一致时写出）。

## 已知限制

- 只打包 x86_64，供云端模拟器安装；没有 arm64 真机 APK，也不声明真机结果。
- APK 使用 debug 签名；不请求用户证书、账号或设备。
- TalkBack 真人屏幕阅读器验收未执行；本包只保证每行文本为虚拟无障碍节点。
- 固定页夹具沿用仓库 `pdf-public.pdf`（每页一个可选中字形），PDF 丰富排版选择未覆盖。
- 大章路径用约 2 MiB 单章验证；30 MiB 文件只验证导入取消，不做全文翻页。
- 取消是协作式的：在复制分块、导入返回和渲染边界生效，不会中断单次原生调用。
- 字体回退只用单一 Noto CJK 字体；多字体集合与系统字体回退未覆盖。
- 每页位图字节与渲染毫秒写入 `EXRHost` 日志；没有据此推断“低内存”结论。
