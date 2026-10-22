# WP12 旧数据迁移（E1 独立子包）

范围：把旧阅读器（`codex/reader-app`，固定提交 `24a3e04b6fc456fa3fa68fa7bd6d9cc3b5c4e383`）的真实用户数据迁入当前
C SDK 书库（schema 6，SDK 3.40.0，ABI 1）。链路：

```
旧浏览器 IndexedDB ──只读导出器──▶ 自描述迁移包(.exrpack) ──exreader-legacy-migrate──▶ 阶段库 ──验证──▶ 发布 ──重开核对
旧"备份书库"zip ──backup_to_pack.py──▶ （同一迁移包）
```

**这不是完整 WP12 高保真转换。** 它只迁移旧应用已保存的用户数据；格式转换保真度属于其他工作包。

本包只含 `extras/migration/**`、`tests/migration/**`、`tools/check_legacy_migration.py`、
`.github/workflows/wp12-migration.yml`、本文档与 `docs/validation/wp12-migration*`。不修改 `src/`、`include/`、
`cmake/`、顶层 `CMakeLists.txt`，只通过安装后的公开头文件和 CMake 包（`EXReader::exr_library`）消费 SDK，不直接写
SQLite 私有表，不改 schema。迁移工具不进入默认 SDK 构建，不引入浏览器或迁移运行时。

## 1. 已核实的旧数据格式

阅读旧源码（`src/store.js`、`src/library.js`、`src/app-library.js`、`src/app-transfer.js`、`src/transfer.js`、
`src/reader.js`、`src/pdf.js`、`src/formats.js`、`src/registry.js`）后冻结；没有虚构的旧版本。

| 格式 | 事实 | 本包覆盖 |
| --- | --- | --- |
| 浏览器 IndexedDB | 库名默认 `exreader`，**版本只有 1**；store `books`（keyPath `id`）、`files`（键为书 ID）、`notes`（keyPath `id`，索引 `bookId`）。 | `exr-legacy-export.js` 只读导出 |
| Tauri 桌面/移动壳 | `src-tauri/src/lib.rs` 只注册 fs/dialog 插件和转换命令，**没有自己的数据库**：数据就是 WebView 内同一份 IndexedDB（便携版把 WebView 配置放在 `EXReader-data/`，仍是 IndexedDB）。因此不是第二种格式；在 Tauri WebView 的同源上下文运行同一个导出器。未在真实 Tauri 窗口里运行（见 §12）。 | 同上 |
| 旧"备份书库"zip | `transfer.js:backup()`：`library.json` = `{version:1, books, notes}` + `files/<书ID>`；`restoreBackup` 限 1 GiB/解压 2 GiB。这是旧应用**实际存在的第二种独立格式**。 | `backup_to_pack.py`（无需浏览器） |

字段读写点（逐字段追踪）：

- `books`：`importFile` 创建 `{title,author,format,audio,cover?,id,filename,size,modified,added,progress:0,favorite:false,tags:[],status:'unread'}`；`updateBook` 只可改 `title/author/tags/favorite/status/cover`；`saveProgress` 只写 `progress/cfi/page/seconds` 并刷新 `lastRead`（`unread→reading`）。
- `files`：值为 `{bytes:ArrayBuffer,name,type,modified}`；旧代码兼容直接存 `Blob` 的形态，导出器两种都读。
- `notes`：`saveNote` 允许字段 `id/quote/note/value/page/seconds/rects/bookmark`，并写 `bookId/created`。重排书的 `value` 是 foliate 生成的 EPUB CFI；PDF 为 `page`(1 起)+`quote`+归一化 `rects`；音频书只有书签（`selected()` 返回 null），`location()` 给出 `seconds` 且 `quote` 为秒数字符串。
- 书签：`bookmark:true`，重排书 `value=lastLocation.cfi`、`quote=目录标题`；PDF `page` 且 `quote="第 N 页"`。

## 2. 迁移包格式 v1（`exreader-legacy-pack`）

单文件，便于浏览器 Blob 下载，也便于 C 侧随机读取：

```
"EXRLGP1\n"(8)  |  原书字节依次排列  |  manifest JSON(UTF-8)  |  trailer(56)
trailer = "EXRLGPT1"(8) | manifest_offset u64le | manifest_size u64le | sha256(manifest)(32)
```

`manifest`：

```
format="exreader-legacy-pack", version=1,
exporter{name,version,read_only}, source{kind:"indexeddb"|"backup-zip", database, version, stores, note_indexes,
  unknown_stores, origin, user_agent, exported_at}, counts, stats, warnings[], orphans{files[]},
books[]: {legacy_id, record:<旧 books 记录原样>, file:{present, offset, size, sha256, name, type, modified, shape}}
notes[]: {legacy_id, record:<旧 notes 记录原样>}
```

读取器的分类（每一类都有独立错误码和用例；包级错误整体拒绝，目标不动）：

| 情形 | 码 | 层级 |
| --- | --- | --- |
| 魔数不符 / 容器版本 `EXRLGP2` | `pack-bad-magic` / `pack-unknown-version` | 包 |
| 截断、尾部错位、尾部多余字节 | `pack-truncated` | 包 |
| 清单散列不符 | `pack-manifest-hash` | 包 |
| 清单不是 JSON / 缺 books、notes 数组 | `pack-manifest-json` / `pack-schema` | 包 |
| 清单 `format`/`version` 未知 | `pack-unknown-format` / `pack-unknown-version` | 包 |
| 重复 `legacy_id` | `pack-duplicate-id` | 包 |
| 原书散列不符、偏移越界 | `pack-hash-mismatch` / `pack-truncated` | 包 |
| 超出清单(64 MiB)、书(10 万)、标注(200 万)上限 | `pack-limit` | 包 |
| 记录缺字段（默认值） | `missing-field` (info) | 条目 |
| 记录有未知字段（逐字保留） | `unknown-field` (info) | 条目 |
| 字段类型错误 | `invalid-book-record` / `wrong-type` | 条目 |
| 无原书字节 | `missing-original` (unsupported) | 条目 |
| 无对应 SDK 格式（`fbz`/`fb2.zip`） | `unsupported-format` (unsupported) | 条目 |
| SDK 拒绝原书 | `sdk-rejected-original` (unsupported) | 条目 |

## 3. 字段映射表

| 旧字段 | 去向（公开接口） | 规则 |
| --- | --- | --- |
| `books.id` | 迁移账本 `legacy_id`→新 `book_id` | 旧→新映射在目标库旁的 `<库>.legacy-map.json`，不改 schema |
| 原文件字节 | `exr_library_import_unique(format, bytes)` | 以格式+字节精确去重；**不按文件名/大小**；格式取 `format`，缺失取文件扩展名：txt/html/htm/fb2/epub/docx/rtf/mobi/azw3→MOBI/pdf/cbz |
| `title` | `exr_book.title` | 去首尾空白；空则用文件名主干；仅在**新建**书时写 |
| `author` | `exr_book.author` | 缺省空串 |
| `tags[]` | `exr_book.tags` | 以 `", "` 连接；含逗号的标签报 `tag-separator` |
| `favorite` | `exr_book.favorite` | 0/1 |
| `status` | `exr_book.status` | `unread/reading/finished`→0/1/2（SDK 未命名常量，按此顺序约定）；未知值警告并取 0 |
| `cover` data URI | `exr_library_cover` | 仅 PNG/JPEG/WebP/GIF 的 base64，≤8 MiB；否则 `cover-invalid`（dropped） |
| `cfi`（重排书） | `exr_document_cfi_resolve`→`exr_anchor_create`→`exr_library_progress` | 解析为**精确**文本点才写选择器；否则回退百分比并报 `cfi-unresolved` |
| `progress`（重排书） | `exr_book.position` | `floor(p×文本字节数)`并回退到 UTF-8 边界，**无选择器**（LEGACY 状态），报 `approximate-progress` |
| `page`（PDF，一基） | `exr_book.position = page-1`（零基页） | 超页数报 `progress-out-of-range` |
| `progress`（仅小数的固定页书，如 CBZ） | `position = round(p×(页数-1))` | 页级估计，报 `approximate-progress` |
| `seconds` | `exr_library_audio_resume`，`offset_ms = round(seconds×1000)`，`rate=1.0` | `audio_id = "exreader-legacy:<legacy_id>"`，`track_id = <legacy_id>`；已有续播点不覆盖 |
| `added`/`lastRead`/`modified`/`size`/`filename`/`audio`/`format`/`type` | 账本 `retained`（原样） | 书库无对应字段，记录在案而非丢弃 |
| `notes.note`（评论） | `exr_note.text` / `exr_fixed_note.text` / 音频书签标签 | 书签评论为空时用 `quote` |
| `notes.quote`+`value`（重排） | `exr_library_note(start,end)`，选择器由 SDK 从存储原书捕获 | 见 §4 |
| `notes.page`（一基）+`quote`（PDF） | `exr_library_fixed_note(page-1, start, end)` | 页内定位见 §4 |
| `notes.bookmark`（重排/固定页） | 空范围点标注 / 页首空范围 | 重排书签必须有可精确解析的 CFI |
| `notes.seconds` + `bookmark` | `exr_library_audio_bookmark(offset_ms)` | 去重按 标签+偏移+轨道 |
| `notes.rects` | 不转换（`rects-not-converted`, dropped）；账本逐字保留 | SDK 固定页标注由文本选择器重新得到几何 |
| `notes.created`/其他 | 账本 `retained` | — |

## 4. 定位规则（不伪装精度）

重排书引用文本：

1. 有 CFI 范围且两端都能精确映射到文本偏移，并且范围内文字与 `quote` 相同（空白等价）→ `cfi+quote`。
2. 否则在全文以"空白序列等价、区分大小写"的 UTF-8 精确匹配搜索 `quote`：唯一→ `quote-unique`。
3. 多处匹配且 CFI 指向的文本节点内恰有一处→ `quote-in-cfi-node`；否则 `quote-ambiguous`（最多比较 4096 处，超出同样视为歧义）。
4. 无匹配 → `quote-not-found`。
5. 书签：只有 CFI 精确映射到文本偏移（`cfi-offset`）或元素起点（`cfi-element-start`）才写点标注；无 CFI/无法解析→未定位。
6. **百分比从不写成字符锚点**；歧义、缺失、无法解析的标注状态为 `unlocated`：原文、评论、CFI、矩形完整保存在账本，**不放进库、不猜高亮**。

CFI 偏移按 UTF-16 码元计，文本节点内容与 `exr_document_text()` 对应片段逐字节一致时才映射；否则只作节点区域用于消歧。固定页（PDF）按页取文本后同样匹配，页码一基→零基。

## 5. 原子性与发布

阶段库 + 可验证发布。目标库 `T`：

1. **独占**：`T.migrate-lock` 以独占创建；已存在则 `busy`（退出 5），不删除别人的锁（`--break-lock` 仅在确认无迁移进程时使用）。要求迁移期间关闭宿主对 `T` 的所有句柄；仍被占用时 SQLite 打开失败→`busy`/`failed`，目标不动。
2. 只读检查 `T` 文件头：必须是 EXReader schema 6（application id + user_version=6），否则 `rejected`（`target-not-library`/`target-schema`），**不会就地升级**目标。
3. 已存在的 `T` 用公开 `exr_library_backup()` 构建阶段库 `T.migrating-<run>`；不存在则新建阶段库。账本 `T.legacy-map.json` 读入内存。
4. 所有写入只进阶段库（公开 import/update/progress/note/fixed_note/audio 接口）。
5. 关闭后**重新打开**阶段库核对：每本原书散列、元数据、选择器进度、每条已迁标注、音频续播点。
6. 严格策略：存在 `unsupported`/`conflict` 条目时 `rejected`（`policy-strict`），不发布；`--allow-partial` 才发布可转换部分并逐项列出跳过项。
7. 发布：写账本临时文件 → 复核 `T` 的 sha256 与开始时相同 → 复制 `T` 为预映像 `T.pre-<run>` → 原子替换 `T` ← 阶段库（POSIX `rename`，Windows `MoveFileExW(REPLACE_EXISTING|WRITE_THROUGH)`）→ 原子替换账本。账本发布失败则用预映像恢复 `T`（`ledger-publish-failed`, `rolled_back=true`）；回滚也失败则 `inconsistent`（退出 6），**保留预映像**并在报告给出路径。
8. 处置：成功后阶段库、预映像、临时文件、锁全部删除；失败/取消同样清理，只有 `inconsistent` 保留预映像。`--dry-run` 构建并验证阶段库后丢弃。

取消（`SIGINT/SIGTERM` 或测试钩子）在条目之间和 SDK 长操作内检查；读失败、写失败、验证失败、发布失败都只丢弃阶段，源包和原目标逐字节不变（用例比较库文件与账本 sha256，并比较 `dump` 逻辑内容）。

## 6. 幂等与冲突规则

- 同一包重跑：书由 `import_unique` 按字节复用；标注由账本（旧 ID→新 ID + 内容指纹）识别，账本丢失时再按 `(页,起,止,文本)` 内容匹配采用现有标注；音频续播点已存在则不覆盖。第二次运行 `created=0`，库内容、新 ID 和账本字节全部相同。
- 中断后重试：被取消/失败的运行不发布任何东西，重试等价一次干净运行（用例与独立干净库逐项相等）。
- **同原书不同旧 ID**：合并到先到者所在的库书；保留其元数据与进度，两侧标注合并，报 `same-original-different-id`（warning）。
- **同旧 ID 原书内容变化**：`id-content-changed`（conflict）；严格模式整体拒绝，`--allow-partial` 保留旧书并跳过该书。
- **同旧标注 ID 内容变化**：`note-changed`（conflict），保留先前结果。
- 目标库已有相同字节的书（用户自己导入）：`adopted-existing`，不改它的元数据/封面/进度。
- 重复写入的内容相同的标注（不同旧 ID）合并为一条。

## 7. 命令行

```
exreader-legacy-migrate inspect --pack P
exreader-legacy-migrate migrate --pack P --target LIB [--report FILE] [--allow-partial] [--dry-run] [--break-lock]
exreader-legacy-migrate verify  --pack P --target LIB
exreader-legacy-migrate dump    --target LIB
```

退出码：`0` success/dry-run，`1` 用法，`2` rejected，`3` failed/verify 失败，`4` cancelled，`5` busy，`6` inconsistent。
标准输出恰为一个 JSON：`result`(`success|rejected|failed|cancelled|busy|inconsistent|dry-run`)、`code`、`message`、`pack`、`target`、
`counts`（expected/created/existing/merged/skipped/unlocated…及 accounted）、`memory`（`peak_rss_bytes`、`max_original_bytes`、…）、
`atomicity`（`stage`、`pre_image`、`rolled_back`、`lock`）、`items[]`（逐书）、`notes[]`（逐标注：`created|existing|unlocated|skipped`、方法、原因）、
`entries[]`（severity ∈ info/warning/approximate/unlocated/dropped/unsupported/conflict）。账本 `<库>.legacy-map.json`
（`exreader-legacy-map` v1）保存映射和所有"未转换/未定位"内容，可回读。`--inject` 故障钩子只在 `EXR_MIGRATE_TEST_FAULTS=1` 时可用。

## 8. 导出（浏览器，同源）

IndexedDB 按源隔离，必须在**旧应用的同一源**里运行：

1. 在旧应用页面打开开发者工具控制台，粘贴 `extras/migration/exporter/exr-legacy-export.js`，执行 `await exrLegacyExport()`；浏览器下载 `exreader.exrpack`。
2. Tauri：在同一 WebView（开启调试或用测试驱动注入）执行同样脚本。
3. 备份 zip：`python extras/migration/exporter/backup_to_pack.py 旧备份.zip out.exrpack`。

导出器只开 `readonly` 事务；库不存在时中止 open 请求，**不创建空库**；库版本≠1 或 store 缺失拒绝（`unknown-version`/`store-missing`）；原书逐本读取并计算 SHA-256 后追加到 Blob（浏览器管理的存储），JS 堆里同时最多一本原书。需要安全上下文（https 或 localhost）以使用 `crypto.subtle`。

## 9. 构建与组件依赖

```
cmake -S extras/migration -B build/migration -DEXR_SDK=<安装前缀> -DCMAKE_BUILD_TYPE=Release
cmake --build build/migration --config Release
```

依赖：SDK 的 `core` 与 `library` 组件（`EXReader::exr_library`）；PDF 原书/固定页标注另需 SDK 以 `EXR_ENABLE_PDF=ON` 构建，缺失时 PDF 条目被 SDK 以 `EXR_UNSUPPORTED` 拒绝并作为 `unsupported` 条目报告（不会伪装成功）。不需要 audio、textindex、pdf_edit、图像可选解码器；CI 使用这个裁剪配置。

## 10. 限界与内存

- 沿用 SDK 边界：单本原书 ≤128 MiB（`EXR_MAX_INPUT`），书签/评论 UTF-8 校验，封面 ≤8 MiB。更大的原书 `limit-exceeded`（不实现流式迁移）。
- 清单整体驻留内存（≤64 MiB）；原书逐本读取、校验、导入、释放；报告含 `peak_rss_bytes`。

## 11. 云端验证

`.github/workflows/wp12-migration.yml`（仅本分支及本包路径 push 或手动触发，不定时、不启动长测）在 Linux 与 Windows：构建安装裁剪 SDK→按安装前缀构建迁移工具→运行 65 个具名场景（`tests/migration/run_cases.py`，覆盖元数据、标签/收藏/状态、原书字节、进度、CFI/歧义引用、固定页/音频位置、标注/书签、重复与冲突、取消、损坏包、未知版本、目标占用、发布回滚、备份 zip）→ Chromium 中用**旧应用自己的 `store.js`/`library.js`** 创建版本 1 IndexedDB（`createStore().addBook`、`updateBook`、`saveProgress`、`saveNote`），在页内运行**发布的导出器**并下载，保存前后快照证明源库未被修改→C 工具迁移、重复迁移、新进程 `verify`/`dump` 核对。旧源码仅在 CI 里按固定提交取出到 `build/`，不入库、不再分发。

`tools/check_legacy_migration.py gate` 汇总证据并核对必需用例；证据（含工具/SDK/导出器/输入 SHA-256、逐 case 断言结果、内存计量和原始步骤日志）由 `record` 作业提交到 `docs/validation/wp12-migration-run<run>-a<attempt>/`，失败时同样保留。

## 12. 未满足项 / 未执行项

见证据 `summary.json` 的 `not_executed`，此处同步：

1. **需要的公共接口**：库内无法保存"未定位"标注（`exr_library_note` 拒绝 `SIZE_MAX` 范围、不接受只带选择器的输入）。未定位标注因此只保存在账本和报告，没有进入库内 UI。需要新接口（如接受明确 `unresolved` 状态与选择器的写入）才能让宿主显示它们。
2. 音频书原文件无法存入书库（`exr_format` 无音频格式）：只迁移续播点与书签；严格模式因此拒绝含音频书的包，需 `--allow-partial`。
3. 超过 128 MiB 的原书不迁移（不做流式迁移）；未实测。
4. 没有在真实 Tauri 窗口、Firefox、WebKit、macOS 上运行；未使用真实用户库（数据集合成，但通过旧应用自己的存储模块创建）。
5. 旧备份 zip 的布局来自源码阅读；CI 的 zip 由测试按该布局构造，未由旧应用在 CI 中生成。
6. 重排书的 CFI 仅在 SDK 能解析、文本节点与文档文本逐字节一致时精确映射；否则回退到引用文本并如实标注。

回复/验收不得把本包写成完整 WP12。
