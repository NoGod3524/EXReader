# C11 Android 五模块真实宿主接入

分配包：C11（Android）。固定 seed：`d263ce5228838ac90c0a0dc13a5193d4a7739681`。
当前团队分支：`codex/team24-android`；团队接手起点：`28f49ee0399d48518cc2afb0048009b6c38edcfa`。本目录只记录本包的实现、接入与验收方式；所有构建、测试、
夹具生成、APK 解析与截图都只在 GitHub Actions 内执行，本地只编辑源码、文档与 Git。

## 交付内容

宿主（`examples/android/app/src/main/java/org/exreader/host/`、`cpp/`、`res/`）把五个既有
reviewed 模块接进真实 `MainActivity`，全部经同一个 `HostTask`/owner 串行执行，不新增线程、
SDK、解析器或第二套书库：

| 模块 | 入口 | 真实操作 |
| --- | --- | --- |
| annotation-import / annotation-export | 阅读页「更多 → 标注导入 / 导出」 | 导出先形成私有 JSONL+Markdown，再 SAF 保存；导入先 SAF 复制、完整预览（指纹、将新增/已存在、公共 FOUND 核对），确认后才写入 |
| font-library | 书架「更多 → 本地字体」 | SAF 导入真实字体文件，选择后按 layout/frame 借用 lease，离开阅读即释放；删除前检查 BUSY |
| original-export | 书架长按书目 →「导出原件」 | 先形成完整私有原件并显示逐项回执（字节、SHA-256），再 SAF 保存；清单未声明 content provider，因此不提供系统分享 |
| jump-history | 阅读页「更多 → 位置历史」 | 真实分页/搜索/目录落地后记录，返回/前进只在公共 FOUND 导航成功后移动游标 |
| sync-status-view | 书架「更多 → 同步」 | 只读状态详情（阶段、安全原因、分片、待上传、冲突），不 ack/retry/写修订 |

标题遵循 `ImportEntry.ReadyRequest.title()` 的去扩展名契约。旧 S20 run 40248648454 的
Android 3/45 不作为成功证据：旧 driver 期待 `Sample.epub` 等文件名，而实际标题是 `Sample`。
本队在 Actions 中复制原 driver 到专用 candidate 目录，逐文件明确标题与格式；例如
`Sample.epub`、`Sample.txt`、`Sample.pdf` 分别核对 `Sample` 与 EPUB/TXT/PDF，不使用任意标题匹配。
picker 仍选择原文件名，并明确断言返回应用；原 driver 字节与失败记录保留。

五项审阅反馈逐项处理：接手源码已有 SDK-only FOUND callback，预先验证书籍身份后不重入
product owner；JNI 在分配收据前只消化协作取消，普通异常原样抛回；整批标注不再包入
`HostTask.commit`，未提交条目继续取消；stage 文件到 UI 接手前持续承担清理责任；丢弃或中断
jump 结果时在原 owner 释放 peek。未完成的标注批次显示已提交收据，并提供明确重试。

搜索与目录来自既有 `SearchPanel` / `NavigationPanel`（真实 `apps/reader/search`、
`apps/reader/navigation` 原生包），本包交付的 APK 默认把这二者与 reading/settings/sync 一起
编入，不存在“要另外加 panel 才有”的情况；共享默认构建仍保持 OFF，避免改变其它包的既有矩阵。

## 真实云端验收（仅 Actions）

`.github/workflows/reader-wave3-c11.yml` 在 ubuntu-latest 上：

1. `tests/reader_wave3_c11/guard.py`：固定 seed、精确自有路径、冻结 SDK/旧测试字节、模块树与 run/attempt 身份。
2. 用 NDK 构建并安装 3.41.0 SDK（x86_64, API26），再安装 raw0.2 产品包与
   annotation-import/export、font-library、original-export、jump-history、sync-status-view
   以及 search/navigation/preferences 到同一前缀。
3. `tests/reader_wave3_c11/fixtures.py` 生成两本确定性书（TXT 长文 + 含真实 nav 的 EPUB），
   `tools/build_android_host.py` 的既有写入器生成旧走查的 9 个夹具；字体为
   `tests/fixtures/fonts/primary.ttf`，内嵌字体仍由 `tools/host_font.py` 的固定版本下载。
4. gradle 编译 `app-debug.apk`（wave3 + search + navigation + reading + preferences + sync +
   selector bytes）、`app-debug-androidTest.apk`（runner = `Wave3UiTest`）与旧 `uitest` APK。
5. API34 emulator 内启用 CheckJNI：先跑 `HostWalkthroughTest`/`HostReviewTest` 的专用标题契约
   candidate（真实 DocumentsUI 导入、阅读、字号、标注、PDF、旋转、进程重启、取消），再跑
   `Wave3UiTest` 的 `first`/`cancel`/`restore` 三阶段及原 NavigationUiTest 16+2 项。
   `Wave3UiTest` 每个检查独立记录通过/失败，单个失败不掩盖其余检查。
6. `tests/reader_wave3_c11/report.py` 只接受同 run/attempt 的证据：源码 SHA、run/attempt、
   设备上实际安装 APK 的 SHA-256、夹具 SHA-256、走查 45 项及全部 wave3/导航检查、
   捕获 PNG 的哈希、SAF 导出原件与夹具逐字节相同、标注导出哈希、进程确实被停止。

## 明确未主张

- 系统分享：宿主 manifest 未声明 content provider（manifest 属冻结路径），因此原件只走 SAF；
  报告里的 `share_intent` 如实记录为不可用。
- TalkBack 语音、性能与“完整产品”仍不在本包验收内（`complete_product=false`）。
- 共享默认构建的 search/navigation 开关保持 OFF；本包只对自己交付的 APK 主张默认启用。
