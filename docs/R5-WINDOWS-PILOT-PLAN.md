# H8：Windows 有界 EPUB 首个闭环计划

本文件是只读宿主审查及实施拆分；尚未修改 `examples/reader.c`，未执行构建、脚本或测试。
审查基准为本工作树 `a0c35f5f01ff88244470ef395886410b78293693` 的 Windows 宿主。
先接收集成人固定的 SDK 源码、接口、schema 与同源云端结果，再实施宿主接入。

## 范围与依赖

- 已有：书库随机源 `exr_library_source`；publication/章内 bounded pager、章内 anchor/CFI/text 查询。
  只提供原件出口不等于已经完成有界导入、位置存储或 Windows 接入。
- 等 R2 固定交付：source/file EPUB 导入、存储模式查询、part/path + 章内 point 进度及 schema 契约。
  当前候选 `library.h` 已可见 `exr_library_epub_info_get`、`exr_epub_location_free`、
  `exr_library_epub_progress/get`，本计划不把候选声明当作已验收 SDK，也不另造一套宿主数据库格式。
- H8正式实施前还必须固定：同章 EPUB notes 的存储、查询、修改/删除及 ID 所有权域。
  SDK 的进度阶段可以独立验收；给 H8 的正式固定 SDK 信号必须同时包含同章 notes。
  旧全书 notes 不能接受新章内坐标。
- 首个闭环：显式有界导入 → SQLite 书架 → 多章前后翻页 → 当页选择/复制 → 字号重排 → 保存章内进度 →
  同章标注增改删/跳转 → 结束进程 → 从书库原件重开及准确恢复。不是全格式流式化或跨章单条标注。
- PDF/CBZ 保留原有功能；可在独立提交把打开改为 `exr_library_fixed_source`，不和 EPUB 的新坐标混用。

## 最少公共 API

| 用途 | 接口及约束 |
| --- | --- |
| 书架/有界导入 | 现有 library open/books/delete 与 `exr_library_import_file_unique` 的 R2 EPUB 分支；不调用 memory import 建全文 DOM |
| 识别存储模式 | R2 固定后的 `exr_library_epub_info_get`；旧书/去重返回旧 ID 时保留原模式 |
| 原件/目录 | `exr_library_source` → `exr_publication_open_source` → `exr_publication_parts`；`in_reading_order` 决定跨章顺序 |
| 当前章分页 | `exr_publication_pager_create`、`exr_chapter_options_defaults`、`exr_pager_get`、cache/checkpoints/set_control；沿用 get 模式，不混 next |
| 页面发布 | `exr_layout_pages/glyphs/lines`、`exr_layout_font`、`exr_render_page_ex`，以及 `exr_pager_read_text` 提取当前页 UTF-8 |
| 选择/重排定位 | `exr_layout_hit_test` 在 worker 有效页面上调用；`exr_pager_anchor_create/resolve` 生成/解析章内 selector |
| 保存与重开 | R2 固定后的 `exr_library_epub_progress/get`、`exr_epub_location_free`；使用 part+path+point，不写旧 `books.position` |
| 同章笔记 | 固定 SDK 的新 EPUB notes 创建/列表/改评论/删除/释放入口；捕获与解析由 bounded pager 完成，不能临时使用旧 note 表 |
| 清理/观测 | pager/publication/source/font 各自公开释放规则；`exr_pager_chapter_statistics` 与 `exr_pager_statistics` |

首个闭环不需要新的 publication 快捷入口、全书 extent、CFI 强制持久化或全书偏移转换 API。
CFI 可留到已有 anchor 路径通过后按需求使用。

## 现有全文依赖及隐式重开点

| 当前实际位置 | 影响与最小处理 |
| --- | --- |
| `job_import` / `read_import_file`（约1270、1370行） | 先 `malloc(total)`，256 KiB 循环只是复制分块；后续 memory import 仍解析全文。仅 EPUB pilot 改 R2 file/source 导入，其他格式保留96 MiB明确上限 |
| `job_open`（约1139行） | `exr_library_document` 明确重开全文。先识别模式，再为 bounded EPUB 创建 source/publication/首个阅读 part；不能在 bounded 失败后静默走旧快照 |
| `render_reflow`（约816行） | 以 `exr_document_text` 切页，并用完整 document 创建 positioned hit layout。改当页有限 UTF-8、位图、几何发布；不为命中测试补开文档 |
| `page_for_offset`（约979行） | 当前整个搜索以单一全书 offset/extent 为准，末端还查 document text。改为指定 part 的局部搜索，extent 仅来自该章的公开统计/已知页面，不用 ZIP 字节数 |
| `reflow_restore` / `job_go` / `job_layout` | 都调用 document anchor resolve；bounded 分支使用当前章 pager，不能用旧 global 数字当本章提示值 |
| `save_progress` / `change_font` | 当前在 UI 回调创建 document anchor；bounded anchor 查询移到串行 worker，进度写新 API，旧记录不覆盖 |
| `selection_bytes` / `page_text_snapshot` / `drive_state`（约1990、2630、2660行） | 剪贴板及验收日志也依赖全文 text，不只渲染函数需要改。统一从 accepted frame 自有 UTF-8 取值，日志不能再打开全文取 hash/预览 |
| `add_note` / `job_note` / `jump_selected_note` | UI 创建 document anchor，旧 note 写入/查询仍是 global 范围。新 bounded 模式只用固定后的新 notes API，带part/path/章内selector与note类型域；未固定前不实施H8 |
| `reload_notes`（约532行） | 读取旧 notes 本身是 SQL 查询，不重开正文；新 bounded 模式调用新 notes 查询，数据库/不支持错误不能记作空列表成功 |
| `src/library.c:exr_library_note` | 未给 selector 且需重新捕获范围时调用 `exr_library_document`；即使显式给 selector 避免重开，旧全书 extent 语义仍不适用于 bounded 书 |
| `exr_library_progress/get` | 这两个接口本身不重开正文，但检查旧全书 extent。不能因“没有重开”便复用作章内进度 |
| `exr_library_fixed_note` | 内部会重新打开存储原件并捕获固定页范围；属于固定页既有路径，不计为 EPUB bounded notes 已实现 |
| 原26项 legacy self-test（约3328行以后） | 独立的 document/pager 消费者；保留作为旧 API 回归，不冒称已迁移为新 bounded 宿主测试 |

## Session、Frame 与 hit-test

`host_session` 仅在 bounded 分支增加 publication、当前 part、稳定 path/路由、该 part 的页号和存储模式。
`exr_document *document` 继续只服务原 snapshot 分支。一个 active session 保留一个当前章 pager，
跨章候选创建成功前不释放 accepted pager；需要保留前章信息时只保留轻量路由/已知页数，不缓存章全文。

`host_frame` 增加自有 UTF-8 页文本、part、章内 range、frame generation，以及当页高亮所需的自有 glyph/line 几何。
`range_start/end` 是该 part 的 normalized UTF-8 坐标；选择和 pending selection 同时携带 part/generation。
UI 的 UTF-16 展示和 UTF-8 选择不能共用数字下标。
当页文本/几何都设置明确容量上限，超限返回可见错误，不截断后假称复制完整。
精确容量在固定 SDK 接入时登记；不能用 page cache 的容量代替 bitmap/文本/几何的计量。

worker 内先 get 页面，完成渲染并复制 page/glyph/line 元数据；不把 borrowed layout、字体视图或窗口指针发布给 UI。
随后通过 `exr_pager_read_text` 拷贝该页的有限区间；sink 不重入 pager，失败时丢弃候选文本/位图，不发布前缀。
frame 的 UTF-8 同时服务剪贴板、页面预览、hash 和验收日志，消除这些路径的全文依赖。

命中测试继续使用 SDK `exr_layout_hit_test`，不在宿主重写 bidi/字素算法，也不把 `NULL` document
传给 `exr_layout_create_positioned`。最小可行方案是串行 worker 的 page-hit 请求：

1. UI 把像素坐标换算为页面坐标，携带 accepted book/part/page/frame-generation 和鼠标手势序号。
2. worker 重新取得该页，在 borrowed layout 有效期内调用 hit-test，返回章内 UTF-8 offset。
3. UI 只在上述身份仍匹配时接受 offset；跨章/换书/字号变化均清除旧选择。
4. 拖动 move 请求可合并，但 down/up 的顺序和手势身份必须保留；不能让现有单 pending 槽覆盖尚未完成的 down，
   也不能把旧 hit 结果应用到新 frame。highlight 仅使用 accepted frame 自有 glyph 几何。

这需要宿主新增一个有限的选择作业/事件处理分支，不需要新增 SDK hit-test API。
若未完成该分支，不得用“全选本页成功”替代拖选验收。

## 跨章、重排及恢复

- 页坐标是 `(part, page_in_part)`，持久坐标是 `(part, canonical path, chapter selector)`；不伪造全书页数。
  UI 显示章序与当前页，只有已知时才显示本章总页数；没有全书精确百分比。
- 向后翻页只在正常请求确认章尾时切下一个 `in_reading_order` part；IO、LIMIT、CANCELLED 等保持原错误，
  不能当作 EOF 跳过坏章。必须云端验证 get 模式的章尾拒绝与真实读取错误可以区分。
- 当前章第0页向前翻，创建前一阅读 part 的候选 pager，按已验证的 get/checkpoint 路径寻找其末页。
  原有“到末页”的巨大页码哨兵不直接跨章传给 pager；大跨度重放仍可取消，不扫描全书求总页数。
- 重复 spine path 必须仍以 part+path 区分，不能按 path 找到第一个相同资源就恢复。
- 字号/窗口配置变化：在旧 pager 捕获 point，创建同 part 候选 pager，解析并定位后渲染；
  所有步骤成功且未取消，才交换 pager/config/frame。缺失/歧义不得宣称精确恢复。
- 重开先读新进度：`present=0` 与存储/源读错误分开；有记录先验证 part/path，再用该章 pager resolve。
  只允许 FOUND 精确恢复。MISSING/AMBIGUOUS/旧记录的 fallback 必须明示，并保留旧记录直到用户接受新位置。
- 对 memory 导入的旧 EPUB，第一版保留旧 snapshot/global progress/notes 全链路。
  unique 去重返回旧 ID 时不自动转换旧数据。自动 global→part 转换另开包，不混入 H8。
- 新同章标注从 accepted frame 的 part/range 捕获 pager selector，并通过固定 SDK 新 notes 存储。
  列表记录保留存储类型、note ID、book ID、part/path；不能拿新 note ID 调旧删除/改评论接口。
  跳转先打开对应 part 的候选 pager，再 resolve；仅 FOUND 发布定位/高亮，歧义保留记录并明确拒绝。
  修改评论不重抓 selector，重启回读必须验证原选文、part 和范围；跨章拖选拆分或拒绝，不伪装成一条同章范围。

## 取消、所有权和提交边界

- 延续现有单 SDK worker、`book_id` 守卫、candidate session/pager/frame 和 pending 替换规则。
  part 和 generation 成为额外的接受条件；只有 UI 接受的新 frame 才能持久化为当前进度。
- source/library/publication/pager 的长生命周期取消 context 不得指向可释放的 `host_job`。
  使用现有长期 `host_cancel_check` 模式或等价 session owner；每次短调用的 control 可借用当次 job。
- `exr_library_source` 成功后由宿主负责；publication 成功打开才转移 context 所有权，失败必须调用 source.release。
  candidate 被取消/失败统一清理；清理顺序为 pager → publication → 未转移 source，最后才是全局 font/library。
- 同 owner 元数据/进度写入不使已有 source 失效；其他连接的提交可能使 source 永久失效。
  此时显式重开 source/publication 并重新解析位置，不能继续使用旧 source 或发布旧作业结果。
- save progress 也放在串行作业中；保存失败保留现有可见错误与关闭保护，不伪装重启恢复已可靠。
- R2 导入提交前取消由 SDK 回滚；提交后返回已提交结果。宿主已有晚到取消回滚仅可删除本作业 `created=1` 的新 ID，
  不删除去重得到的既有书；回滚失败继续保留可见状态，不隐藏新行。

## 与原验收并存的最小提交

不增加临时启动选项或双默认开关。R2 进度可先单独验收，但 H8 必须等到同章 notes 一并固定后开始。
同一正常 binary 的新 EPUB 导入改走新 source/file 路径，原158步也必须在此新路径上通过。
按数据库存储模式兼容原有 memory 导入书，是旧数据兼容分支，不是另一个用户默认模式；
已经标记 bounded 的书不能静默降为快照。验收记录必须证明原 EPUB 用例实际使用新模式及新 notes API。

| 提交 | 最小代码边界 | 同次云端出口 |
| --- | --- | --- |
| H8.1 | `host_session` 模式/生命周期、默认EPUB有界导入、job_open、frame文字/渲染/日志；旧数据兼容分支保持 | 新导入→书架→首屏；证明无 library_document/blob 全书副本；重复导入保留旧/新模式 |
| H8.2 | job_go/page_step/page_for_offset、part候选交换及章内保存/恢复 | 多章同local offset、重复path、跨章前后翻、进程重启、FOUND/歧义/丢失与真实读取错误 |
| H8.3 | 页命中作业、选择/复制、新同章notes CRUD/列表/跳转、字号重排、取消和旧帧守卫 | 真实拖选、UTF-8字素、复制内容、标注重启/高亮/改评论/删除、歧义拒绝；换书/跨章/改字号时旧结果拒绝 |
| H8.4 | 仅Windows专用新增夹具/driver/严格判定与工件；不改共享引擎 | 固定SDK+正常宿主同源跑完旧26项、原158步/8截图、证据拒绝回归、worker正反验证和新增pilot |

原 `tools/check_windows_host.py` 的 A/B/C（120/29/9）共158步、八张绑定截图、原26项 package self-test
保留原计划及判定。`tests/windows_host/check_evidence.py` 的伪造拒绝也保留。
`wp13-windows-worker.yml` 现有 candidate/base 正反验证继续跑，不将观察型 binary 当作唯一交付宿主。
新 pilot 独立记录 plan/case/页面文字与像素身份、source/SDK/binary/font/fixture hash、book/part/path/range、
parse/page/checkpoint/bitmap/owned-frame 字节与 windows loaded/evicted。失败、超时、缺原件全部拒绝。

阶段性通过只授予 Windows pilot；其他格式维持原上限；真机/辅助技术及性能硬预算不在本包声明。
同章 notes 是该 pilot 前置及验收范围，跨章单条 notes 仍不支持。
未收到包含 notes 的固定 SDK 信号前，只维护这份接入准备，不提交宿主草案接口、不启动云端验收。
