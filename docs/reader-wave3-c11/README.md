# C11 Android 五模块真实宿主接入

分配包：C11（Android）。固定 seed：`d263ce5228838ac90c0a0dc13a5193d4a7739681`。
分支：`codex/reader-wave3-c11`。本目录只记录本包的实现、接入与验收方式；所有构建、测试、
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

另修复了既有宿主的两个真实缺陷（来自 S20 run 40248648454 的 Android 失败）：

1. **导入状态与书架标题丢了扩展名**：`ImportEntry` 的 `ReadyRequest.title()` 是去扩展名的
   提示名，宿主直接用它，导致真实 UI 只显示 `Imported Sample`、书架行是 `Sample`，
   既有黑盒走查（要求 `Imported Sample.epub` / `Sample.epub`）整链失败。现在宿主从暂存
   身份（`<sha256>.<format>`）恢复真实格式扩展名并用完整文件名显示与建库。
2. **超限提示不含真实上限**：32 MiB 限制的错误文本不含既有走查断言的 `exceeds 32 MiB`。

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
5. API34 emulator 内：先跑既有 `HostWalkthroughTest`（真实 DocumentsUI 导入、阅读、字号、
   标注、PDF、旋转、进程重启、取消），再跑 `Wave3UiTest` 的 `first`/`restore` 两个阶段。
   `Wave3UiTest` 每个检查独立记录通过/失败，单个失败不掩盖其余检查。
6. `tests/reader_wave3_c11/report.py` 只接受同 run/attempt 的证据：源码 SHA、run/attempt、
   设备上实际安装 APK 的 SHA-256、夹具 SHA-256、旧走查 45 例全过、wave3 14 个检查全过、
   捕获 PNG 的哈希、SAF 导出原件与夹具逐字节相同、标注导出哈希、进程确实被停止。

## 明确未主张

- 系统分享：宿主 manifest 未声明 content provider（manifest 属冻结路径），因此原件只走 SAF；
  报告里的 `share_intent` 如实记录为不可用。
- TalkBack 语音、性能与“完整产品”仍不在本包验收内（`complete_product=false`）。
- 共享默认构建的 search/navigation 开关保持 OFF；本包只对自己交付的 APK 主张默认启用。
