# 书籍信息快照（EXReaderBookInformation 0.1.0）

## 固定起点与边界

- 固定起点：`f43baf9182d75907c0cb5d6f77048f27bca8c950`；冻结 SDK
  `9854061be331fe603a1822d9b2b36ee357154927`（3.40.0 / ABI 1）；产品 schema1 与既有
  wire v1、reading anchor v1/v2 不改。
- 本包只写入 `apps/reader/book-information/**`、`tests/reader_book_information/**`、
  `.github/workflows/reader-book-information.yml`、`docs/READER-BOOK-INFORMATION.md`
  与 `docs/validation/reader-book-information.json`。
- 依赖只有两件已安装的公开包：冻结 SDK 的 `EXReader::exr_library` 与产品目录
  `EXReaderProductCatalog::reader_catalog 0.1.0`。不读 SDK 私有 SQL，不使用本机 SDK
  行号作跨设备身份，不新增同步实体，不写产品库也不写 SDK 库。
- 本包是只读组件；宿主信息面板、编辑、metadata 模块与真实宿主接线由 root 负责，本包
  因此不豁免自己的模块实测。

## 公开契约

```c
reader_book_information_status reader_book_information_read(
    reader_catalog *catalog, exr_library *library, const char *book_key,
    const reader_book_information_options *options,
    reader_book_information **out, reader_book_information_error *error);
const reader_book_information_view *reader_book_information_get(const reader_book_information *);
void reader_book_information_free(reader_book_information *);
```

- **输入**：`catalog` 必需，`library` 可为 NULL（此时不触碰任何 SDK 对象）。
  `book_key` 必须是产品键 `format:sha256`（≤128 字节），即
  `reader_books.book_key`；`options->struct_size` 必须覆盖整个结构体，短于记录一律拒绝。
  读取只经 `reader_catalog_metadata`、`exr_library_source`，以及（请求时）
  `exr_library_fixed_source`（PDF/CBZ）或 `exr_library_epub_info_get`（EPUB）。
- **输出与内存归属**：`*out` 是模块独占的深拷贝；调用方用
  `reader_book_information_free` 释放。视图不借用产品行、SDK 源或 fixed 文档，因此
  catalog、library、源和文档全部关闭后仍然有效；视图不可变，可被任意线程读取。
  失败与取消时 `*out` 恒为 NULL。
- **线程/重入**：`catalog` 与 `library` 必须在其创建 worker 上使用（两者自身即要求
  owner 线程）。模块自身另有逐线程重入闸门：从本模块取消回调里再次调用会立刻返回
  `REENTRANT`，不会触碰被借用的句柄。
- **取消**：`cancelled` 回调在同一线程同步调用；每个阶段之前与每个 64 KiB 散列块之间
  轮询。取消返回 `CANCELLED`，不产生任何部分快照。
- **提交边界**：模块从不写库、不开事务、不留后台状态；每次调用把两个库恢复为调用前的
  状态。读取期间只借用一行产品元数据与一个 SDK 源/文档。
- **错误**：`error` 在每次调用入口清零，只在返回非 `OK` 时有意义；`catalog_code`
  记录产品库/SQLite 码，`sdk_code` 记录 `exr_status`。缺本机文件、错书、口令与解析失败
  都是视图里的字段状态，不是错误。

## 产品字段与解析器字段

视图严格分区，解析器字段永远不会覆盖或推测产品字段：

| 分区 | 字段 | 来源 |
| --- | --- | --- |
| 产品 | `book_key`、`format`、`location_kind`、`title`、`author`、`author_known`、`favorite`、`deleted`、`product_source_bytes` | `reader_catalog_metadata` |
| 本机 | `availability`、`identity`、`verified_bytes`、`verified_sha256` | `exr_library_source`（+ 本模块 64 KiB 分块 SHA-256） |
| 解析器 | `parser_status`、`page_count_known`、`page_count`、`parser_title`、`epub_*`、`properties` | `exr_library_fixed_source` / `exr_library_epub_info_get` |

未知就是未知：非定页格式的 `page_count_known=0`，空作者是 `author_known=0` 而不是
"未知作者"，EPUB 没有公开标题就 `parser_title=NULL`。`location_kind` 只在存在本机映射
时非空（云only行是空串）。视图不包含本机 SDK 书 ID：跨设备身份只有产品 `book_key`。

| 格式 | 解析器字段 |
| --- | --- |
| `pdf`、`cbz` | 页数、标题、键值元数据（PDF Info 八个键 + XMP；ComicInfo 属性） |
| `epub` | 只有 bounded_storage / global_extent 存储模式；页数与标题保持未知 |
| `txt`、`html`、`fb2`、`docx`、`rtf`、`mobi` | `NO_PUBLIC_FIELDS` |

## 可用性与身份

| availability | 含义 |
| --- | --- |
| `CLOUD_ONLY` | 只有产品元数据；目录没有本机映射 |
| `LOCAL_UNCHECKED` | 有映射，但调用方没给 SDK 句柄 |
| `LOCAL_PRESENT` | 公开 SDK 源存在并通过下列身份级别 |
| `LOCAL_MISSING` | 有映射，但 SDK 无法提供原件（行缺失或读取中途失效） |
| `IDENTITY_MISMATCH` | 存的是另一本书 |

| identity | 含义 |
| --- | --- |
| `NOT_CHECKED` | 没有打开 SDK 源 |
| `SIZE_ONLY` | 存储大小等于产品大小，且未请求散列 |
| `SHA256` | 大小与 SHA-256 都等于 `book_key` 里的摘要 |
| `MISMATCH` | 大小或摘要不同；`verified_bytes=0` 且不给摘要 |

`SIZE_ONLY` 是刻意更弱的档位：不请求 `verify_source` 时，字节数相同的另一本书无法
分辨。该限制由 `size-only-identity-limit` 用例显式登记，不隐藏。

## 上限

| 项 | 硬上限 |
| --- | ---: |
| `book_key`（UTF-8 字节） | 128 |
| 标题、作者、解析器标题（各自） | 1024 |
| 元数据键 | 128 |
| 元数据值 | 1024 |
| 保留的元数据属性 | 32 |
| 散列块 | 64 KiB |
| 单次快照（含视图与属性数组） | < 48 KiB |

超长文本只在 UTF-8 标量边界截断，并在 `title_truncated`、`author_truncated`、
`parser_title_truncated`、`key_truncated`、`value_truncated` 标记；被截断的值绝不
当作完整值。超出 32 条的属性、空键条目与非合法 UTF-8 条目计入 `properties_omitted`，
不静默丢弃。

## 验收

`.github/workflows/reader-book-information.yml` 在 ubuntu-22.04、windows-2022、
macos-15 上各自：源码/保护树/路径守卫 → 构建安装冻结 SDK 与产品目录 → 只对已安装包
构建本组件 → 从已安装包编译独立 C 与 C++ 消费者 → 生成夹具、播种两个库、逐项判定。
同一次 run 的工件由 evidence 作业通过 API 重新枚举、下载、解包、重算 ZIP 摘要并核对
报告身份；缺项、跨源码、跨 attempt、篡改一律拒绝。

22 个具名用例覆盖：九格式云端仅元数据、无库读取、SHA-256 与 size-only 身份、非 ASCII、
超长字段与属性上限、无 Info 的页数、EPUB 两种存储模式、重排格式无公开字段、本机映射
缺失、错书（尺寸/内容）、size-only 档位、无句柄、逐轮询点取消、SDK 关闭后快照可读、
独立 public API 复算、异线程与不可变视图、取消回调重入、参数与错误契约、前后存储不变。

夹具、两个数据库、安装前缀、消费者二进制与全部失败原件随工件保留。

## 复现

```
cmake --preset reading-library && cmake --build --preset reading-library && cmake --install build/reading-library
cmake -S apps/reader/store/native -B build/bi-product -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=build/bi-prefix
cmake --build build/bi-product && cmake --install build/bi-product
cmake -S apps/reader/book-information -B build/bi-adapter -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DEXR_SDK=$PWD/build/reading-library/stage \
  -DCMAKE_PREFIX_PATH="$PWD/build/bi-prefix;$PWD/build/reading-library/stage" \
  -DCMAKE_INSTALL_PREFIX=build/bi-prefix
cmake --build build/bi-adapter && cmake --install build/bi-adapter
cmake -S tests/reader_book_information/consumer -B build/bi-consumer -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_PREFIX_PATH="$PWD/build/bi-prefix;$PWD/build/reading-library/stage"
cmake --build build/bi-consumer
python3 tests/reader_book_information/make_fixtures.py --out build/bi-fixtures
python3 tests/reader_book_information/check_book_information.py \
  --probe build/bi-consumer/book-info-probe --compare build/bi-consumer/book-info-compare \
  --fixtures build/bi-fixtures --work build/bi-work \
  --output build/bi-evidence/book-info-evidence --platform "$RUNNER_OS"
```

以上全部只在 GitHub Actions 执行；本机只做源码、文档与 Git 操作。

## 原失败与限制

失败的 run、attempt 与工件按共同约束保留，不删除断言、不换语料、不把真实失败改成预期
拒绝；记录见 `docs/validation/reader-book-information.json` 的
`failure_iterations_retained`。

## 未覆盖范围

- 加密 PDF 的 `PASSWORD_REQUIRED`：本包不生成加密夹具，该分支只有代码路径，没有实测。
- 软删除产品行：产品包没有公开 API 设置 `reader_books.deleted`，因此 `deleted=1`
  的视图只能由 root 的命令模块构造，本包不宣称覆盖。
- 非合法 UTF-8 的产品/SDK 文本：两个提供方在进入本模块前已拒绝，这两处校验是防御性的，
  未通过公开 API 实测。
- 宿主信息面板接线、编辑能力、metadata 模块、真机与无障碍、性能与功耗：本包不授予。
- 本包不因宿主未接线而免除模块实测，但也不把模块实测当成宿主功能通过。
