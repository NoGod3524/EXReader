# R5：原生宿主接入有界阅读

本轮完成源码接入梳理；宿主代码未修改，未运行构建或测试。检查基准为联合验收源码
`686ce2fe6c3463ef1b917569677ee9933e22faa9`。Android 另只读核对独立交付工作树
`wp13-android-review/EXReader`，HEAD 为 `31b36f305085cb8b1468b1d9b9b1ea2d67ee1656`。

目标是让 EPUB 进入已有窗口分页路径，PDF/CBZ 进入已有原书按需读取路径。
其他重排格式继续保留当前快照与明确上限；`exr_publication_pager_create` 目前只适用于内置 EPUB provider。
各平台保持原生绘制，不引入 WebView。

## 已有公共 API 与共同缺口

| 环节 | 已有接口与契约 | 接入影响 |
| --- | --- | --- |
| 随机读原件 | `include/exr/base.h` 的 `exr_source`：`size/read_at/release/control`；`exr_publication_open_source`、`exr_publication_open(path)` | 无须整本堆缓冲；成功打开才转移 source context 所有权，失败由调用者释放 |
| 窗口分页 | `exr_publication_parts`、`exr_publication_pager_create`、`exr_chapter_options_defaults` | 当前分页器对应一个 part；宿主须管理阅读顺序和跨章前后翻页 |
| 定位与选文 | `exr_pager_anchor_create/resolve`、`exr_pager_cfi_create/resolve`、`exr_pager_read_text` | 节点和 normalized UTF-8 偏移是章内坐标；选择文本以最多 32 KiB 的 UTF-8 chunk 回调 |
| 页面与预算 | `exr_pager_get` 或 `exr_pager_next`、cache/checkpoint 设置、`exr_pager_chapter_statistics` | 不混用两种页面模式；parse、页面、checkpoint、字体/图像和位图分别计量 |
| 书库固定页 | `exr_library_import_file_unique`、`exr_library_fixed_source` | CBZ 按 SQLite blob 随机读，PDF 使用匿名映射；已有公开路径可直接接入 |
| 书库 EPUB | `exr_library_document`、`exr_library_blob` | 前者解析全文快照，后者整本 malloc 复制；没有公开的书库 EPUB 随机读 source/publication 出口 |
| EPUB 大章导入 | `exr_library_import_unique`；流式 import API 目前只支持 CBZ/文件 PDF | 打开路径改成 bounded 仍不能让超过快照限制的 EPUB 完成书库导入 |
| 书库进度/标注 | `exr_library_progress/get`、`exr_library_note/notes` | 原契约是全书 normalized UTF-8 偏移和 `text_size`；不能直接写入章内偏移 |

缺口来自 `include/exr/library.h`、`src/library.c` 与 `include/exr/layout.h` 的实际契约。
`exr_library_note` 支持调用者显式提供 selector，从而避免再次捕获全文快照，
但它仍检查全书范围。当前各宿主通常未提供这个 selector。
`exr_library_progress` 虽不重新解析，也校验全书 extent；旧数据的恢复语义必须保留。

因此先固定一个最小公共 SDK 契约，再给平台包同一份 SDK：

1. 书库提供 EPUB publication 或原件随机读出口，明确库句柄、blob、publication 的关闭次序与失败释放。
   复用 `src/library.c` 已有 blob I/O，宿主不直接读取书库表结构，也不用 `exr_library_blob` 伪装流式。
2. 为 EPUB 确定“稳定 part/path + 章内 selector/CFI”的持久化和旧全书偏移迁移契约。
   可以由 SDK 提供转换，但不能先在四个平台各自发明存储含义。
   旧歧义/未找到状态继续明确返回，不能按原数字偏移猜测跨章位置。
3. 大章导入纳入该契约：有界读取元数据/原件并保存必要 extent，不能靠抬高全文快照上限。

这些是待实现接口要求，不是现有 API。冻结接口和云端通过的 SDK 后，平台实现才相互独立。

## 公共生命周期与页面发布规则

publication 被 bounded pager 保留；宿主仍应持有明确的 source/library 所有者，最后一个引用释放才关闭原件。
字体、图像回调 context、取消 context 必须覆盖所有相关分页与绘制作业。
渲染使用页面的 `exr_layout_font(layout)`，保留书内字体和图片资源语义。

worker 内完成 get/next、渲染、文字提取、hit-test 与锚点捕获；UI 接收自有位图、页面范围和有限文本。
缓存借用页面不能跨下一次 get/clear/free 使用。先消费页面需要的几何与渲染信息，再调用可能逐出窗口的查询。
位置以 `part/path + page-local index + normalized source range` 表示；页码不能替代持久锚点，
`exr_pager_position` 也不是可序列化恢复 token。

页正文/选文改用 `exr_pager_read_text`，sink 不重入 pager。UI 的 UTF-16/字符索引转换依托当前页自有 UTF-8 文本，
叠加当前章范围；复制大选择或导出须有明确输出预算，不能把整个章节积成 String/Data/byte[]。
sink 失败可能已交付前缀，宿主应暂存所需有限结果，成功后才发布剪贴板或文件。

保留每平台串行所有权与取消令牌；翻页、改字号、关闭、换书时旧结果必须经书 ID 和 generation/token 守卫。
更新 UI、保存进度及接受候选分页状态需维持既有提交边界，失败时不能偷偷推进已接受页。

## 平台独立包

### R5-Windows：建议首个书库完整 pilot

拥有 `examples/reader.c` 及 Windows 专用验收工具/夹具；先接收固定 SDK，不修改核心接口。
现有 C 宿主已有串行 worker、取消、书 ID 守卫和候选 pager 交换，接入无需新增语言桥接。

- `host_session` 增加 EPUB publication/当前 part 生命周期；`job_open` 与字号重排创建 bounded pager。
  非 EPUB 快照分支保留。PDF/CBZ 的 `exr_library_fixed` 改用 `exr_library_fixed_source`，独立验证存储原件读取。
- `render_reflow` 去除 `exr_document_text` 整本依赖，按页范围读取文字。
  当前为 UI hit-test 调用 `exr_layout_create_positioned(session->document,...)`；不能给它传空 document。
  将 hit-test 放在 worker 对仍有效页面执行，或复制当页必要几何并明确坐标；UI 不留借用 layout。
- `reflow_restore`、`save_progress`、`add_note`、`jump_selected_note`、`copy_quote` 和重排锚点捕获统一采用新位置契约。
  当前 `exr_anchor_create/resolve_ex(document,...)` 路径不能在 bounded 模式继续隐式打开全文档。
- 云端 Windows 验收保留既有用例，增加多 part 跨章翻页、长章、换书/取消、重排后定位、重启、选择/标注和预算观测。

### R5-Apple

拥有 `examples/apple/HostSDK.swift`、`HostModel.swift` 及 Apple 专用验收；不改共享 Swift binding。

- `HostDocument` 目前保存全文 `Data`，`HostPager` 持有 snapshot document；新增清楚区分的 EPUB publication/session 路径。
  `HostPager.makeAnchor` 的注释已明确当前 snapshot pager 不能调用 bounded anchor API，不能仅替换一处构造函数。
- `HostSession.open/rebuildPager/renderSnapshot/notes/jump` 改为 part+范围定位；
  `slice(document.text, range)` 与用全文字节数算进度的逻辑换为有限页文本和已知章节信息。
- `HostLibrary.importUnique` 当前先读入最多 32 MiB `Data`；只有新 SDK 导入契约完成后才能扩大支持范围。
  `HostFixed` 使用书库 fixed-source 路径；保留原生 selectable text、SwiftUI token、串行队列及 `HostCancelBox` 提交边界。
- 云端 macOS/iPhone/iPad 分别保留原验收并覆盖窗口逐出后选文、旋转/字号、重启和歧义定位。

### R5-Android

拥有 `examples/android/app/src/main/java/org/exreader/host/`、局部
`examples/android/app/src/main/cpp/exreader_host_jni.c` 及 Android 专用验收；共享 JNI/Java binding 另经接口所有者协调。

- 当前 `ReflowSession` 从 app-owned path 打开 `EXReader.Document`，并复制全文到 `byte[]`；
  Java `Publication` 只暴露 open/parts/load，未暴露 bounded pager/anchor/read_text。
  用局部 JNI 桥接已有 C 公共入口，比让宿主引用 SDK 内部结构更直接。
- `ReflowSession.prepare/next/recoverAcceptedCursor`、`PageSnapshot`、`ReaderView` 的行文本与选择切片改为有限页数据，
  保留 next/recovery 计量及接受/回滚动作。
- `exreader_host_jni.c` 的 progress/saveProgress/notes 仍重新调用 `exr_library_document`；
  替换渲染并不能解决这些全文解析入口。显式 selector 和新书库位置契约需一起接入。
- Android 保留 app-owned 原件 path，故可以独立先做文件直读 bounded 绘制验证；
  但当前导入预检和书库 import 仍打开全文快照，这个小验证不能授予书架大章闭环。
- 保留 worker、`HostTask`、generation、原 45+10 项与门禁；增加跨章和长章用例。
  先验收现有 API34 x86_64 模拟器范围，真机和 TalkBack 继续独立跟踪。

### R5-Linux

拥有 `examples/linux/reader.c` 及 Linux 专用验收。当前为 8 MiB 快照的小型 GTK 重排宿主，不处理 PDF/CBZ。

- `open_id/frame/present/resize_font/save_progress/add_note/note_activated` 均依赖全文 document/text；
  先按固定 SDK 接入 EPUB，其他格式保留明确上限。
- 目前 SDK 与渲染调用直接发生于 GTK 回调；长章 pilot 必须增加一个串行 worker 与取消/generation，
  仅在 GTK 主线程更新自有位图/文本，不把同步大章工作搬进主循环。
- `GtkTextBuffer` 只保存当页文字，按 UTF-8 字节转换选择范围。PDF/CBZ UI 属另一项明确扩展，不顺手并入本包。
- 云端保留既有宿主用例，增加关闭/换书取消、跨章、窗口逐出、重启定位与 UI 响应验证。

## 开工与交付顺序

先冻结 SDK 的书库随机读、导入和位置契约，再由 Windows 做首个书库完整 pilot；
Apple、Android、Linux 可在同一固定 SDK 上独立分支并行。SDK 契约未完成时可做平台包装准备，
不能把原件读取或位置持久化阻塞转化为静默全文回退。

每个平台交付固定源码、云端 run、逐例结果及 parse/page/checkpoint/bitmap 内存观测。
数值预算沿用 R3 的实测约定；R5 不凭页缓存大小宣布整体低内存，也不重启旧源码长测。
