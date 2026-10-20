# 轻量格式转换契约（WP12-lite）

本文件冻结 `exreader-convert` 的 CLI、格式别名、profile 选择、清单 schema、路径规则、
文件保护、取消粒度、报告字段与能力边界。实现只通过公开 SDK 解码/导出；CLI 负责参数、
文件 I/O、原子发布和报告。**text profile 不是无损或高保真转换**；preserve profile 只承诺
结构/资源保留，目标阅读器的绘制保真单独声明。

## 1. 命令与退出码

```
exreader-convert --capabilities
exreader-convert --input PATH --to FORMAT [--from FORMAT] [--profile text|preserve]
                 [--output PATH] [--report PATH] [--overwrite]
exreader-convert --batch MANIFEST [--root DIR] [--output-root DIR] [--profile PROFILE]
                 [--report PATH] [--overwrite]
```

- 无交互确认；`--overwrite` 就是显式覆盖授权，参数已表达的授权不再询问。
- `--from`/`--format` 是显式输入格式；扩展名与内容不一致时按声明选择解析器，但仍要求
  文档内容可被该解析器打开。显式声明 MOBI/KF8 变体时必须与字节一致。
- `--capabilities` 必须单独使用，输出 JSON 能力查询。
- 单文件必须给 `--input` 和 `--to`；`--batch` 不能与单文件参数混用。
- 退出码：`0` 全部项成功并重开验证；`2` 参数/调用错误；`3` 至少一项
  rejected/failed/cancelled/unfinished；`4` 报告无法发布（转换结果不回滚，stderr 列出已发布输出）。
- 能力不支持是**单项 rejected**（退出码 3），不是参数错误；不会自动把 preserve 降级成 text。

## 2. 格式与别名

| 规范名 | 扩展名别名 | SDK 枚举 | text 输入 | text 输出 | preserve 输入 | preserve 输出 |
| --- | --- | --- | --- | --- | --- | --- |
| `txt` | `.txt` | `EXR_TXT` | 是 | 是 | 否 | 否 |
| `html` | `.html` `.htm` `.xhtml` | `EXR_HTML` | 是 | 是 | 是 | 是 |
| `fb2` | `.fb2` | `EXR_FB2` | 是 | 是 | 否 | 否 |
| `epub` | `.epub` | `EXR_EPUB` | 是 | 是 | 是 | 是 |
| `docx` | `.docx` | `EXR_DOCX` | 是 | 是 | 否 | 否 |
| `rtf` | `.rtf` | `EXR_RTF` | 是 | 是 | 否 | 否 |
| `mobi` | `.mobi` `.azw` `.prc` | `EXR_MOBI`（变体 mobi） | 是 | 否 | 否 | 否 |
| `kf8` | `.kf8` `.azw3` | `EXR_MOBI`（变体 kf8） | 是 | 否 | 否 | 否 |
| `pdf` | `.pdf` | `EXR_PDF` | 否 | 否 | 否 | 否 |
| `cbz` | `.cbz` | `EXR_CBZ` | 否 | 否 | 否 | 否 |

- `html`/`xhtml` 是同一逻辑格式。输出统一为 XHTML 序列化；目标名 `html` 与 `xhtml`
  产生相同字节，报告记录用户选择的目标名。
- MOBI 与 KF8 共用 `EXR_MOBI`，但变体由输入字节判定（PalmDB 的 MOBI 版本 8，或
  hybrid BOUNDARY 后版本 8），不能靠改扩展名充数。扩展名 `.mobi` 期望 mobi、
  `.azw3`/`.kf8` 期望 kf8；字节不一致时 rejected（显式 `--from` 同样校验）。
- 默认输出扩展名：text profile 用规范名；preserve 的 `html` 输出是 `.zip`。
- 同格式 text/preserve 请求默认输出会自动加 `-converted`/`-preserved`，避免源目标同名。

## 3. Profile 选择与语义

- `--profile` 省略时默认 `text`，报告 `profile_defaulted:true`；清单顶层/单项也可声明。
  优先级：CLI > 单项 > 清单顶层 > 默认 text。
- **text**：输入 `txt/html/fb2/epub/docx/rtf/mobi/kf8`，输出
  `txt/html/fb2/epub/docx/rtf`。六个基础格式形成 36 个方向（含 6 个同格式）；
  MOBI/KF8 各自再覆盖 6 个输出。
  - 承诺：已声明的正文、段落/阅读顺序、Unicode 行为。
  - 报告逐项给出标题/元数据/章节/图片/表格/CSS/字体/链接/脚注/批注的
    `preserved|degraded|unsupported|declared` 状态；无法判断的记 `unknown`。
  - 不是无损、不是高保真；不会复制图片/字体/CSS，不保留批注。
- **preserve**：只接受 `epub/html/xhtml` 输入到 `epub/html` 输出，四个必做组合：
  `epub→epub`、`epub→html`、`xhtml→epub`、`xhtml→html`（`html` 输入与 `xhtml` 同义）。
  - 复用 `exr_document_export_epub` 与 `exr_document_export_html_bundle`。
  - 保留章节/阅读顺序、树、图片/字体/样式资源、可解析内部链接和已声明元数据；
    独立报告元数据保留/降级。字体等资源复制成功 ≠ 像素一致。
  - `html` 目标是**单个 ZIP**，不是改名成单 HTML。报告 `entry_path`；必须先整包解压，
    再按入口路径打开。ZIP 成员保留原始相对路径，重复 basename（不同路径）不冲突。
  - 超出范围的输入/目标明确 rejected，绝不自动切换 text。

PDF、CBZ、音频的跨媒介转换、MOBI/KF8 写回、OCR、DRM、音频转写、完整 Word/PDF 排版、
旧 UI 数据库迁移均未支持；能力查询明确列出。

## 4. 路径与输出根规则

单文件：

- 输入相对路径相对当前工作目录。
- 显式 `--output` 若为相对路径：有 `--output-root` 时相对它，否则相对输入所在目录。
- 省略 `--output` 时输出在输入所在目录（有 `--output-root` 时在它下面）。
- `--report` 相对当前工作目录；报告路径不得与任何输入/输出相同。

批处理清单：

- 清单路径相对当前工作目录；清单所在目录是默认基准。
- 顶层 `root` 相对清单目录；`--root` 覆盖它。相对 `input` 相对有效 root 解析，绝对路径原样。
- 顶层 `output_root` 相对清单目录；`--output-root` 覆盖它。相对 `output`（含默认派生输出）
  相对有效 output_root；没有 output_root 时相对该输入所在目录。
- 显式输出中的目录必须已存在；工具不递归创建任意输出目录（避免隐式目录事务）。
- 重复输出在预检阶段按规范化路径和现有文件 identity 判定，冲突项全部 rejected，不按
  basename 互相覆盖。

## 5. 清单 schema（schema 1）

```
{
  "schema": 1,
  "profile": "text",
  "overwrite": false,
  "root": ".",
  "output_root": "out",
  "items": [
    {"id": "a", "input": "a.txt", "to": "epub", "output": "a.epub"},
    {"id": "b", "input": "sub/b.html", "to": "html", "profile": "preserve",
     "format": "html", "overwrite": true}
  ]
}
```

顶层允许字段：`schema`（必须整数 1）、`profile`、`overwrite`、`root`、`output_root`、`items`。
单项允许字段：`id`、`input`、`to`、`output`、`profile`、`format`（等价 `--from`）、`overwrite`。
未知字段、重复 id、空 `items`、错误类型、非法 JSON 都是调用错误（退出码 2）。
`items` 上限 100000；清单上限 16 MiB。

## 6. 文件保护与原子发布

- 输入始终以只读方式打开；工具从不写输入。测试对输入做转换前后 SHA-256 对照。
- 源/目标同一文件拒绝，包括：相同路径、大小写别名（Windows）、相对/绝对别名、
  symlink/junction、硬链接、现有文件 identity 相同。目标尚不存在时比较解析后的父目录 +
  basename。
- 默认不覆盖现有输出；`--overwrite` 才允许。即使覆盖也先写同目录唯一临时文件
  （`.名称.exreader-<pid>-<n>.tmp`，独占创建），写入并 flush/close 成功后原子发布：
  Windows `MoveFileExW`（不带 REPLACE 时目标存在即失败），POSIX 无覆盖用 `link`+`unlink`、
  覆盖用 `rename`。发布失败保留原目标字节；临时文件删除。
- EPUB、HTML 资源包和所有目标都按单个文件发布，不引入多文件目录事务。
- 批处理逐项独立发布；单项失败/拒绝/取消保留记录并继续其他独立项。整批有失败/取消/
  未完成即退出 3。不会把失败项过滤成成功。
- 报告在每项后原子更新，最终再写一次；报告与已发布文件状态一致。报告无法写入时退出 4，
  在 stderr 列出所有已发布输出，不声称整批回滚。

## 7. 取消粒度（不宣称逐字节）

- 安装 SIGINT/SIGTERM（Windows 控制台 CTRL_C/CTRL_BREAK）处理器，设置取消标志。
- 边界：每项开始前；读入前/后；打开后；text 导出每 64 个 block、RTF 每 4096 个
  scalar、归档发布前；preserve 导出沿用既有 control（逐成员/逐节点轮询）；临时文件写入后、
  发布前再次检查。
- 取消时该项 `status:"cancelled"`，不发布；临时文件删除；原输出保持不变。批处理剩余项
  记为 `unfinished`。已发布的项不回滚，报告如实记录。
- 旧 `exr_document_export` 无 control 参数；本包新增
  `exr_document_export_control`（NULL 等价旧行为）。它仍在 block 粒度取消，不是逐字节。

## 8. 限界

- 工具输入上限 512 MiB（自有保护，不抬高 SDK 限界）；SDK 的 `EXR_MAX_INPUT`、
  文本/模型/资源/深度/成员预算继续生效。
- preserve EPUB 需要 1..9996 个成员；保留路径、保留名、冲突、缺资源按 SDK 规则原子失败。
- XML 1.0 禁止的标量在 XML 目标被拒绝（TXT/RTF 可表示）；不通过放宽校验通过验收。
- 不整本加载模拟章内增量，不做 1 GiB 流式导入；这些属于其他工作包。

## 9. 报告 schema

顶层字段：`schema`(1)、`tool`、`engine_version`、`abi`、`mode`(`single|batch`)、`manifest`、
`report_path`、`report_written`、`overwrite`、`profile_defaulted`、`cancel_requested`、
`started_utc`、`finished_utc`、`elapsed_ms`、`peak_rss_bytes`、`counts`、`batch_complete`、
`published_outputs`、`items`。

`counts`：`expected/actual/succeeded/rejected/failed/cancelled/published/reopen_verified/unfinished`。

每项字段：`id`、`profile`、`input`、`input_format`、`input_variant`、`format_source`、
`output_format`、`output`、`entry_path`、`stage`、`status`、`error_code`、`error_name`、
`error`、`published`、`reopen_verified`、`cancel_requested`、`input_sha256`、
`output_sha256`、`input_bytes`、`output_bytes`、`chapters`、`package_resources`、
`elapsed_ms`、`degradations`、`notes`。

`stage` 取值：`preflight|read|open|convert|write|publish|verify|complete|queued`。
`status` 取值：`ok|rejected|failed|cancelled|unfinished`。
`degradations` 是 `{capability,status,note}` 数组，最后一项 `transparency` 记录 profile、
输入格式、章节数、包资源数和目标说明。`notes` 记录发布/重开/入口等事实。
`reopen_verified`：text 为输出可重开且正文规则一致；preserve EPUB 还比较 spine 与资源字节；
HTML 包比较入口可打开且每个章节/资源路径存在。渲染保真不在该字段内。

## 10. 构建、安装与示例

```
cmake -S . -B build/native -DCMAKE_BUILD_TYPE=Release
cmake --build build/native --parallel 4
cmake --install build/native --prefix stage
stage/bin/exreader-convert --capabilities
stage/bin/exreader-convert --input book.epub --to html --profile preserve \
  --output book-html.zip --report report.json
stage/bin/exreader-convert --batch manifest.json --report batch-report.json
```

`EXR_BUILD_TOOLS=OFF` 只关闭工具，不关闭 SDK 导出/安装消费；转换不要求字体渲染、
PDF/音频/书库可选组件。安装后的工具与 `exreader` 运行库需成对分发。

## 11. 验证入口

```
python -X utf8 tools/generate_conversion_corpus.py --out C:/Users/Oscar/exr-wp12-lite-corpus
ctest --test-dir build/native -R 'native-convert' --output-on-failure
python -X utf8 tests/check_convert_cli.py <tool> <corpus> <work> <json>
python -X utf8 tests/check_convert_benchmark.py <tool> <corpus> <work> <json>
```

组合矩阵、工具场景、preserve 渲染与基准证据分别在
`docs/validation/wp12-lite-conversion-matrix.json`、`wp12-lite-cli-scenarios.json`、
`wp12-lite-preserve-render.json`、`wp12-lite-conversion-benchmark.json`。

## 12. 量化验收表（本包）

| 组合 | 预期 | 实际 | 通过 | 拒绝 | 未完成 |
| --- | ---: | ---: | ---: | ---: | ---: |
| text 六类输入×六类输出 | 360 | 360 | 360 | 0 | 0 |
| MOBI 输入×六目标 | 60 | 60 | 60 | 0 | 0 |
| KF8 输入×六目标 | 60 | 60 | 60 | 0 | 0 |
| preserve 四组合×10 | 40 | 40 | 40 | 0 | 0 |
| preserve 渲染回归（同路径像素/坐标/源范围） | 20 | 20 | 20 | 0 | 0 |
| CLI 工具场景 | 37 | 37 | 37 | 0 | 0 |

- text 矩阵的 6 个同格式项单独计入 360，不代替 30 个跨格式方向。
- MOBI/KF8 各 10 个真实、散列不同的输入；变体由字节判定。
- 证据：`docs/validation/wp12-lite-conversion-matrix.json`、
  `docs/validation/wp12-lite-preserve-render.json`、
  `docs/validation/wp12-lite-cli-scenarios.json`、
  `docs/validation/wp12-lite-conversion-benchmark.json`、
  `docs/validation/wp12-lite-builds.json`、`docs/validation/wp12-lite-baseline.json`。
- 未完成项：Linux ASan/UBSan 本机不可运行；完整 WP12 的高保真全格式往返、旧 UI 数据迁移
  仍按路线表独立跟踪，不能由本子包标记完成。
