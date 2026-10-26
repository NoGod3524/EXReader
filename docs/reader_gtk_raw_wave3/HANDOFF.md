# GTK raw0.2 Wave 3 家族接线交接（DSF-G02）

本包只做 GTK 宿主对 five Wave 3 工具的 raw0.2 installed family 显式接入，不加产品功能。
起点 `36d5deec`，分支 `codex/dsf-gtk-raw-wave3`。本机未运行任何构建、测试、语法检查、夹具、
截图或工件下载/解包，全部在 GitHub Actions 内完成。

## 1. 结论先行

- **五个 Wave 3 工具现在可以显式选 raw0.2 installed family**：`EXR_READER_GTK_RAW3=ON` 时
  annotation import/export、jump-history、sync-view 全部来自同一 raw prefix 的 exact `0.2.0`；
  font-library 与 original-export 只有单一 0.1.0 家族，保持原样。`RAW3=OFF`（默认）仍解析原
  0.1.0 模块，原入口、原 CMake 图、原测试二进制不变。
- **raw gate 全绿**：run `40385003502` / attempt `1`（source `af87ba8d`）——raw 安装家族 34 项、
  raw host 身份 13 项、raw owner probe **20 组业务断言**、legacy-OFF 配置+链接，全部通过，
  `accepted=true`。
- **原授权的一次完整 raw GTK GUI 轮已执行且通过 10/10**：run `40385948659` / attempt `1`
  （source `af87ba8d`，workflow_dispatch `gui=true`），`accepted=true`，10 项记录逐条 `pass:true`。
- 该 GUI 轮只覆盖五工具本身；**原 navigation、batch-import 两条保留套件本轮未执行，也不计为通过**。
  它们在本队合并前由 DSF-G01 的一轮里各失败一次（真实 X11 时序），本包不改、不重跑、不掩盖。
- 本交接不宣称 GTK 五模块端到端验收完成，更不宣称六平台产品完成。

## 2. source / run / attempt

| 用途 | source | run / attempt | 结果 |
| --- | --- | --- | --- |
| 最终 raw gate（push） | `af87ba8db0c43f4fcf878983eaa2290e7889b0ee` | `40385003502` / `1` | **success**，`accepted=true` |
| 原授权完整 raw GUI（dispatch `gui=true`） | `af87ba8db0c43f4fcf878983eaa2290e7889b0ee` | `40385948659` / `1` | **success**，`accepted=true`，五工具 **10/10** |
| 前一次 GUI dispatch（未进入任何 UI 断言） | `2b8abe3e5e9878520a499d67aa2fc2a09e3b3a78` | `40383943824` / `1` | failure：驱动拿到 payload 父目录，`bin/exreader-linux` 不存在，宿主从未启动；判为“未开始”，不是一轮 UI |
| 一次 gateway 复核（push） | `2b8abe3e5e9878520a499d67aa2fc2a09e3b3a78` | `40382931330` / `1` | success，首次全量包含 GUI 夹具与 compact payload 制备 |
| 首个全绿 gate（push） | `d0f723731a172ab51a6821a098854d2b0b176550` | `40381812170` / `1` | success，backend 20 组首次全过 |

全部失败尝试与真实根因（同一 branch，逐轮只修一处，无放宽断言）：

| run | 失败点（真实原因） |
| --- | --- |
| `40353794089` | 探针缺 `reader_annotation_export_raw3.h`（implicit declaration） |
| `40354021577` | install 检查用头文件文本判家族，legacy/sync 头两家族同字节 |
| `40354756437` | 把落点当区间：落点是 caret（`exact_size==0`），断言错 |
| `40356515420` | EPUB 槽位按 index 0 读，历史是进程级单栈 |
| `40360111121` | 翻页是“一次落点”，count 不增（coalesce 规则） |
| `40361844573` | EPUB 翻页 caret 不是可证明位置，跳转被模块正确拒绝 |
| `40363515478` | worker 要求命令 part/page 与当前会话一致（HISTORY/SEARCH_CHOOSE/FONT_USE） |
| `40368278429` | 新书落点会先截断 forward 再追加，count 不等于 before+1 |
| `40370359769` | legacy 检查渲染后仍是 `if(OFF)`，文本判据错；legacy 只链接库与 probe，无 GUI 可执行 |
| `40371314773` | 固定页无文本选区：宿主 `current.start/end` 不含范围，highlight 被正确拒绝 |
| `40372404883` | 同上，加上 slot 对比诊断（证明 anchor3 字节完全一致） |
| `40373839350` | host 身份里的 raw exporter 符号属于 probe，不属于 GUI host |
| `40374994768` | 公开固定夹具第 2 页起不可渲染，翻页无帧 |
| `40376004836` | outbox 分页上限是模块自带的 100 |
| `40378851138` | 复读文本的选择器不唯一，public FOUND 拒绝（模块正确行为） |
| `40380737789` | 宿主提交的是已校验快照，截断 live 文件不会改变确认导入 |

## 3. 家族边界（legacy / raw）

| 模块 | legacy（默认，`RAW3=OFF`） | raw（`RAW3=ON`） | 判据 |
| --- | --- | --- | --- |
| EXReaderAnnotationImport | `0.1.0` | `0.2.0`（`reader_annotation_import_raw3.h`） | exact 版本 + target 带 `EXR_READER_SELECTOR_BYTES_CANDIDATE=1` + 安装头版本宏 + config/归档同源 |
| EXReaderAnnotationExport | `0.1.0` | `0.2.0`（`reader_annotation_export_raw3.h`） | 同上 |
| EXReaderJumpHistory | `0.1.0` | `0.2.0`（`READER_JH_INSTALL_VERSION`） | 同上 |
| EXReaderSyncView | `0.1.0` | `0.2.0`（`READER_SYNC_VIEW_VERSION`） | 同上 |
| EXReaderFontLibrary | `0.1.0` | `0.1.0` | 单一家族：禁止携带 raw capability |
| EXReaderOriginalExport | `0.1.0` | `0.1.0` | 单一家族：禁止携带 raw capability |

- 宿主侧开关：`EXR_READER_GTK_RAW3=ON` 且 `READER_WAVE3_PREFIX` 必须与 `READER_GTK_RAW3_PREFIX`
  是同一个安装前缀（否则 FATAL），并在 `exreader-linux-reading` 上增加 `EXR_READER_WAVE3_RAW3=1`。
- **纯 capture 编码只用公开候选**：pin `a911cd0e8405a362dae1bb489190de02c4c81d51` 的三个 blob
  —— `apps/reader/reading-state/CMakeLists.txt` = `2b513dee…`（blob `2b513deeb2681eb2e0c674fe447ddfee83cb3994`）、
  `include/reader_reading_state_capture_raw_candidate.h` = `0cce3515…`、`src/reading_state.cpp` = `25de29dd…`；
  候选以 `EXR_READER_PURE_CAPTURE_CANDIDATE=ON` 显式安装，raw 历史缺它时 CMake 直接 FATAL。
- 旧 reading-state 公共头/API 与版本未动；无私有 extern（`reader_rs_encode_retained_raw_v3` 未被使用，
  guard 断言其不出现）；SDK、模块 schema/实现、公共 desktop CMake 均字节未变。
- 历史不把 v1/v2 伪标 v3：fixed 页用公开 `reader_jh_commit_fixed_v3`（anchor3），reflow/EPUB 用公开候选
  `reader_rs_encode_capture_raw_candidate(...,2,...)` 保 v2 后 `reader_jh_commit_wire_raw_v3`。
- 进度/落点必须是真实 point：落点是 caret（`start==end`、`exact_size==0`），由真实 SDK capture 生成，
  并与 live 会话的 fresh capture 逐字节比对（含 NUL 与 NULL/empty 区分）。

## 4. 验证执行范围（仅 Actions）

### 4.1 raw gate（run `40385003502` / attempt `1`，source `af87ba8d`）

- **raw 安装家族检查 34/34**（`check_install.py --family raw`）：版本文件、raw 头存在、config 渲染条件、
  target capability、归档/头同源。
- **raw host 身份 13 项**：`READER_GTK_RAW3_PREFIX`/`READER_WAVE3_PREFIX` 同一前缀、WAVE3/RAW3 打开、
  GUI host 内 `reader_annotation_import_raw3_run`/`reader_jh_commit_wire_raw_v3`/`reader_rs_encode_capture_raw_candidate`/
  `reader_sync_view_capture`/`rfl_import_file`/`roe_run`，probe 内 raw import/export 入口。
- **raw owner probe 20 组业务断言**（`reader-gtk-wave3-raw-backend`，真实 SDK capture/resolve + 真实 raw store）：
  1. `reflow_history_and_progress_are_real_v2_points`——TXT 落点与 progress 记录都是真实 v2 point；
  2. `history_back_and_forward_prove_the_point_before_moving`——先证明后移动，游标只在 COMMIT 后动；
  3. `epub_history_slot_is_the_real_anchor_v2_route_point`——EPUB 保留 anchor v2 与 spine route；
  4. `epub_page_turn_replaces_one_landing_with_the_new_real_point`——翻页是替换不是新增；
  5. `epub_search_landing_is_appended_as_a_real_anchor_v2_point`；
  6. `epub_history_jumps_only_to_a_resolved_anchor_v2_route`——真实跳转（status=0）；
  7. `fixed_history_slot_is_anchor3_with_every_nullable_selector_byte`——fixed 槽位 anchor3，逐字节等于
     fresh SDK capture，含 NUL 与 NULL/empty 区分；
  8. `fixed_history_landing_is_the_real_anchor3_page_point`；
  9. `original_export_and_font_refusal_keep_the_raw_host_intact`——原件导出逐字节、fixed 页拒绝字体；
  10-12. sync 三项：无会话显式只读、capture 不启动/不推进会话、真实失败 sweep 仍只读且从不宣称全库同步；
     每次都比对 outbox 行数不变（只读不写）；
  13. `raw3_export_writes_both_retained_annotations`——真实 raw exporter 写出 2 条；
  14. `raw_preview_validates_the_export_without_writing`——PREVIEW 全文件校验、0 写入；
  15. `raw_commit_without_the_checked_fingerprint_is_refused`——无 preview 指纹的 COMMIT 被拒；
  16. `raw_confirmed_import_commits_the_checked_bytes_not_the_changed_file`——确认导入提交的是已校验字节；
  17. `raw_damaged_export_is_refused_by_its_own_preview`——被改坏的文件由自己的 preview 拒绝；
  18. `raw_roundtrip_preserves_every_reflow_selector_byte`——导出→导入后选择器逐字节一致；
  19. `raw_exact_retry_is_a_duplicate`；
  20. `raw_wrong_book_is_refused_without_commit`。
- **legacy-OFF 兼容**：完整 0.1.0 家族安装并通过 30/30 家族检查；用 `RAW3=OFF` 配置并链接
  `exreader-linux-reading` 与 `reader-gtk-wave3-backend`（**只配置+链接，未重跑整套 legacy 套件**）。
- 二者同一 attempt 内互不掩盖：探针失败也会继续跑 legacy 检查并在结果里各自记账。

### 4.2 完整 raw GTK GUI 轮（run `40385948659` / attempt `1`，source `af87ba8d`）

驱动：`tests/reader_gtk_raw_wave3/ui_raw.py` = DSF-G01 受测驱动**同源 blob**
`43bab342c97cde24ae30556e46cebe269312d66e`（G01 source `0be6a226`，run `40350391595`），
仅追加一条 raw 家族前置动作（下节 4.3），十条业务断言、reveal chooser、所有超时原样。

payload：compact raw0.2 包（`EXReader-Linux/bin/exreader-linux` sha256 `7f8492cbad1f2406b60c10ac99443efcaf3e77d4e1f490a03e1f72450bf3042d`）。

| # | 断言 | 实测 |
| --- | --- | --- |
| 1 | `reading_tools_menu_complete` | More 菜单六个工具齐全 |
| 2 | `compact_default_has_no_tool_surfaces` | 默认阅读面仍为 5 个紧凑控件 |
| 3 | `annotation_preview_validates_without_writing` | `ann_phase=2, validated=1, annotations=2, heads=2, committed=0, bytes=3554` |
| 4 | `annotation_confirm_commits_records` | `committed=2, created=2, duplicates=0` |
| 5 | `annotation_broken_file_refused_without_writing` | `phase=5, validated=0`，状态文本 `Annotation file refused: Truncated string or unescaped control` |
| 6 | `font_import_lease_and_reading_agree` | 2 个字体、`font_applied=1`、租约哈希 `ce360aed…`、书页未变 |
| 7 | `font_anomaly_keeps_previous_font_and_page` | notice `…previous font and page retained (stored font changed)`，前后帧一致，翻页可回原位 |
| 8 | `original_export_matches_source_bytes` | `89048` 字节、`created=1,durable=1`、父目录=exported，reveal 逐级真实滚动（work→EXReader→build→gtk-raw-wave3→gui→exported） |
| 9 | `history_back_forward_after_real_landing` | `count=2,cursor=1,moves=2`，`11770 → back 485 → forward 11770`，使能位逐项正确 |
| 10 | `sync_status_read_only` | `refreshes=1,phase=4`，文本 107 字符、`editable=false`、`session_present=0,session_state=0`，重开一致 |

### 4.3 raw 家族唯一新增前置（不是断言）

`ui_raw.py` 在 `import_book()` 之后增加一步：经同一原生 `Reading → Reading records… → Add bookmark`
路径保存一条真实记录。原因是安装的 raw0.2 导入器只向**已经保留原始身份**的 store 提交
（`reader_revision_book_identity_raw_v3`，模块合同），而一条真实记录正是用户创建该身份的动作。
该步骤不产生 check，不改十条断言、不改超时、不改 reveal chooser。

## 5. 原工件与实际程序身份（全部在 Actions 内解析）

- artifact：`reader-gtk-raw-wave3-40385948659-1`（GUI 轮）；身份报告由该轮 authenticate 作业在 Actions 内
  从自身上传的 ZIP 解析（`build/gtk-raw-wave3-identity/identity.json`），本机未下载、未解包。
- 实际程序（包内真实二进制，本包自身解析所得）：
  - raw GUI host `raw-host/gtk-host/exreader-linux` = `fa298c02b8b95004d97cd6c07bd5b9468260f61832d25ffa5c3438018090f23f`
  - raw owner probe `raw-host/reader-gtk-wave3-raw-backend` = `bbd39fb56d8458739ea316c0ee7dbfd7d9d3c9e971467eee22537d2579ce960a`
  - legacy OFF 链接产物 `legacy-host/reader-gtk-wave3-backend` = `410f3089e30b21bc6959dd07d4d8aced48536975294a342d149d55750f8377b8`
  - compact raw 包程序（GUI 轮实际被测）`7f8492cbad1f2406b60c10ac99443efcaf3e77d4e1f490a03e1f72450bf3042d`，
    与 GUI 报告自报的 `program_sha256` 一致。
- 夹具身份：书 `history.txt` sha256 `ab723a4beadcbe33a99be5e98ba58b886b96f78932e3bf27e3aa436d050c7d3b`
  （89048 字节，与导出件逐字节相等）；raw3 注释件 `annotations.jsonl` sha256 `c31914d4…`，由安装的 raw exporter
  从真实 raw store 写出（seed 自报 `annotations:2`，key `txt:ab723a4b…`）。
- 记录自报：`source_sha=af87ba8d…`、`run_id=40385948659`、`attempt=1`、`complete_product=false`、
  `screen_reader_accepted=false`、`scope=five Wave 3 GTK tools only; not a full product acceptance`。

## 6. 未测 / 失败 / 已知边界

1. **原 navigation 与 batch-import 两条保留套件本轮未执行**（见 §1），因此不计为通过；它们的失败历史见
   DSF-G01 交接（`docs/reader-wave3-c10/HANDOFF-DSF-G01.md`，run `40350391595`）。
2. fixed 页的**历史跳转**未执行：需要同一本书第二个可渲染页，而公开固定夹具第 2 页起故意不可渲染；
   本包改为证明 anchor3 槽位逐字节等于 fresh SDK capture（含 NUL/NULL 区分），fixed 的 v3 resolve 由保留的
   raw3 owner probe 覆盖，不在此重复宣称。
3. fixed 页**不能产生注释夹具**：安装的 raw store 拒绝没有 quote 的 fixed 记录，且本宿主没有固定页文本选区；
   因此导出/导入 roundtrip 在 reflow 书上执行，fixed 的字节保真由历史槽位承担。
4. 真实网络 sync（真 WebDAV/TLS 会话）未覆盖：本包只验证“无会话”和“真实会话 + 失败 sweep”两种只读快照。
5. 真机、屏幕阅读器、其余五个平台、性能均不在本包范围；不把它们拼成本次跨平台通过。
6. `annotation import` 在 raw 家族要求目标 store 已有该原件身份（模块合同）；本包按要求“不越界放宽”，
   在文档与 GUI 前置中显式说明，未改模块。

## 7. 最小合入 diff（相对 `36d5deec`，12 文件 / +2102 / −11）

| 文件 | 内容 |
| --- | --- |
| `apps/reader/desktop/gtk_feature_integration.cmake` | raw/legacy 家族显式选择 + 四条 `_exr_raw_guard_target` + 前置条件校验 + raw probe 目标；OFF 分支逐字保留 |
| `examples/linux/wave3_backend.inc` | fixed 走 `reader_jh_commit_fixed_v3`；reflow/EPUB 保 v2 后 `commit_wire_raw_v3`；raw3 import PREVIEW/指纹/COMMIT + 真实 FOUND 回调；legacy 路径原样 |
| `examples/linux/reading.c` | 仅新增 raw 指纹字段（`EXR_READER_GTK_RAW3` 下） |
| `apps/reader/reading-state/{CMakeLists.txt,include/reader_reading_state_capture_raw_candidate.h,src/reading_state.cpp}` | pin `a911cd0e` 三个 blob（候选编码），旧公共头/API 不动 |
| `tests/reader_gtk_raw_wave3/`（新） | `backend.c`（20 组业务断言 + seed 模式）、`check_install.py`、`guard.py`、`run.py`、`ui_raw.py`（G01 同源 blob + 唯一前置） |
| `.github/workflows/reader-gtk-raw-wave3.yml`（新） | 自有 workflow；`gui` 布尔输入，push 永不跑 GUI |

未改动：`tests/reader_wave3_c10/*`、`.github/workflows/reader-wave3-c10.yml`、`apps/reader/desktop/CMakeLists.txt`、
SDK、五个模块的 schema/实现、其它 owner。`guard.py` 逐条断言这些路径与 base 同字节。

## 8. 复现

```
gh workflow run reader-gtk-raw-wave3.yml -r codex/dsf-gtk-raw-wave3            # gate only
gh workflow run reader-gtk-raw-wave3.yml -r codex/dsf-gtk-raw-wave3 -f gui=true # gate + 一次完整 raw GUI
```

GUI 轮只在同一 attempt 的既有范围全绿后执行；不含原 navigation / batch-import 套件。
