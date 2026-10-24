# WebDAV 选书下载与侧载导入

`apps/reader/cloud-import` 是独立的静态 C11 适配包 `EXReaderCloudImport` 0.1.0。
它把已有的 WebDAV 目录浏览、选中远端文件、下载到私有 staging 和侧载导入串成两个显式分开的阶段。
它不新增网络后端、账号库、自动同步、宿主界面或产品映射，也不改变冻结 SDK
`9854061be331fe603a1822d9b2b36ee357154927`（SDK 3.40.0／ABI 1／schema 7）、`extras/webdav` 或 `extras/sideload`。

固定起点 `f43baf9182d75907c0cb5d6f77048f27bca8c950`，分支 `codex/reader-webdav-import`。
依赖只读：`extras/webdav/include/exr_webdav.h`（0.2.0）与 `extras/sideload/include/exr_sideload.h`，
真实签名已核对，没有按名字猜接口。

## 两个阶段

| 阶段 | 调用 | 线程 | 使用 | 不使用 |
| --- | --- | --- | --- | --- |
| 1 下载 | `reader_cloud_download` | 宿主网络 worker | 借用的 `exr_webdav_client` | 任何 `exr_library`／SDK 指针 |
| 2 导入 | `reader_cloud_import` | 书库 SDK owner 队列 | 借用的 `exr_library`、`exr_sideload_import_file` | WebDAV client、网络 |

中间值 `reader_cloud_staged` 是不透明的普通数据，可由网络 worker 交给 SDK owner，同一时刻只由一个线程使用。
模块不创建线程、定时器或常驻任务，不写产品目录和产品 SQL，不打开或关闭书库，不调用 `exr_library_remove` 等行变更接口。

```text
list(client, "books/")  ->  用户选中 entry(resource, display_name, bytes)
  网络 worker:  reader_cloud_download(client, &request, &staged, &error)
  可取消:       reader_cloud_staged_discard(&staged)           // 阶段间取消，不触及 SDK
  SDK owner:    reader_cloud_import(library, &staged, &opt, &result, &error)
  成功后:       result.committed / result.created / result.book_id
```

## 公开接口（`reader_cloud_import.h`）

### `reader_cloud_download`

- **输入**：`reader_cloud_request`（`struct_size` 必填，用 `reader_cloud_request_init`）。
  `resource`＝列表返回的根相对资源；`display_name`＝远端名称（UTF-8，≤1024 字节）；
  `format`＝九种之一或 `EXR_CUSTOM`（由扩展名推断：epub pdf cbz txt html htm fb2 docx rtf mobi azw azw3）；
  `expected_bytes`＝列表声明长度（0 未知）；`max_bytes`（只能降低上限）；`staging_dir`＝宿主稳定私有目录；`control`。
- **输出**：成功时 `*staged` 为新值，持有一个已发布、完整、已记录 SHA-256 的普通文件；其他状态 `*staged=NULL`。
- **所有权**：`resource`、`display_name`、`staging_dir` 只借用到调用返回，名称被复制进 staged。
  staged 由 `reader_cloud_import` 或 `reader_cloud_staged_discard` 释放；accessor 返回的指针到那时为止有效。
- **本地文件名**：模块生成 `cloud-<16 位十六进制>.<扩展>`；远端名称、路径、ETag 都不参与本地路径。
  重名由 `exr_webdav_download_file` 的不覆盖发布暴露，最多换名重试 16 次。
- **内存**：不分配整本书；64 KiB 缓冲用于回读与哈希。
- **错误**：`READER_CLOUD_REMOTE`（`webdav_code`／`http_status` 带原 WebDAV 状态：TLS、401、重定向、HTTP、IO 等）、
  `LENGTH`（实收长度≠`expected_bytes`）、`LIMIT`、`CANCELLED`、`ARGUMENT`、`MEMORY`、`IO`。
  所有失败都清除临时与部分 staging 文件，client 仍可重试。
- **取消／提交边界**：取消在 I/O 边界检查；阻塞中的原生 HTTPS 调用受 client 超时限制，不保证立即中断。
  文件一旦原子发布，调用返回 OK（published wins），之后到达的取消由宿主改为调用 discard。
- **凭据**：Authorization 只在 client 创建时由宿主提供；本包不接触、不记录、不复制。

### `reader_cloud_import`

- **线程／重入**：只在 SDK owner 上、与该书库所有其他使用串行；回调不得重入本包、client 或书库。
- **步骤**：取消检查 → 回读 staged 文件并核对长度与 SHA-256（每 64 KiB 可取消）→ `exr_sideload_import_file`。
  阶段间若文件被改（翻转、截断、追加）返回 `READER_CLOUD_CORRUPT`，缺失返回 `IO`，二者都不进入 SDK。
- **标题**：`options.title`，缺省取远端名称去掉可识别扩展名；含控制字符的远端名称不当作标题，改用书内元数据。
- **提交边界**：`exr_sideload_import_file` 返回成功即 `committed=1`（`created` 区分新书与精确重复、`book_id` 持久），
  之后的取消请求不改变结果。SDK 自身取消或回滚为 `CANCELLED`／`IMPORT`，`committed=0`。
- **清理**：除 `READER_CLOUD_ARGUMENT` 外，调用消耗 staged：无论成功或失败都只删除 staging 副本、释放值并置 `*staged=NULL`。
  任何路径都不删除 SDK 书行；精确重复命中旧书时保留其标题、阅读进度、标注与存储模式。
- **上限**：沿用侧载契约——EPUB／CBZ／PDF 128 MiB 流式，其他六种重排格式 32 MiB；
  请求或导入选项只能降低。声明长度超限在发出任何网络请求前拒绝；无声明长度时由进度回调在越线时中止下载。

## 安装后接入

```text
cmake -S apps/reader/cloud-import -B build/cloud-import -G Ninja -DCMAKE_BUILD_TYPE=Release -DEXR_SDK=<sdk> -DCMAKE_PREFIX_PATH="<prefix>;<sdk>" -DCMAKE_INSTALL_PREFIX=<prefix>
cmake --build build/cloud-import
cmake --install build/cloud-import
```

先安装冻结 SDK、`extras/sideload` 与 `extras/webdav`（macOS 用 `-DEXR_WEBDAV_APPLE_URLSESSION=ON`）。
下游启用 C++17 链接（WebDAV 模块为 C++），使用 `find_package(EXReaderCloudImport 0.1.0 CONFIG REQUIRED)` 和
`EXReaderCloudImport::reader_cloud_import`。`tests/reader_webdav_import/consumer` 是只用安装前缀构建的 C 与 C++ 范例。

```c
reader_cloud_request request;  reader_cloud_staged *staged = NULL;  reader_cloud_error error;
reader_cloud_request_init(&request);
request.resource = entry->resource;  request.display_name = entry->display_name;
request.expected_bytes = entry->has_size ? entry->bytes : 0;
request.staging_dir = private_staging_dir;
if (reader_cloud_download(client, &request, &staged, &error) != READER_CLOUD_OK) { /* 展示 error，client 可重试 */ }

/* 交给 SDK owner 队列后： */
reader_cloud_import_options options;  reader_cloud_import_result result = {sizeof(result)};
reader_cloud_import_options_init(&options);
if (reader_cloud_import(library, &staged, &options, &result, &error) == READER_CLOUD_OK) {
  /* result.committed==1；created 0 表示已有同字节的书 */
}
```

## 验收范围

`.github/workflows/reader-webdav-import.yml` 在 Ubuntu 22.04、Windows 2022 和 macOS 15 上：
先跑源码／保护树／路径守卫（含其自身正反例），再安装冻结 SDK、侧载、WebDAV 与本包，用只依赖安装前缀的 C 与 C++ 消费者，
对运行器信任的临时 CA 的真实本机 TLS WebDAV 服务执行 `tests/reader_webdav_import/check_cloud_import.py`，
最后由同次运行的汇总作业按 GitHub API 的 artifact 身份、字节、摘要、源码 SHA、run／attempt 严格复核。

用例覆盖：九种格式（含 `.azw3`）经目录浏览→下载→导入并由独立进程用新 SDK 句柄回读原件字节；Unicode 与带空格／`#`／`&` 的远端名；
同名不同内容共存；精确重复保留旧书且其后的下载后损坏、取消清理均不删除它；下载后翻转／截断／追加／删除；
SDK 拒绝的坏书；跨源重定向、HTTPS 降级、不可信证书、主机名不符、401、404／500；短读；列表长度与实收不符；
33 MiB 重排流越线、128 MiB+1 声明、请求／导入限额只降不升；下载前、下载中、阶段间取消，以及导入阶段按轮询点扫描的
提交边界（每个扫描点只能是"已取消且无书"或"已提交且原件可回读"）；凭据不出源站、无外源请求、证据不含凭据。

这不是产品通过证明：没有连接真实用户云盘服务，没有移动端／模拟器／真机，没有实际音频或朗读，没有宿主界面接线，
没有性能或内存峰值预算。阶段间取消、提交后取消的边界由轮询点扫描确定性地证明；PDF 与重排格式的 SDK 调用本身无法被中断，
这是 `exr_sideload.h` 已记载的限制。本包不因宿主未接线而免除上述模块实测，宿主接线与最终联合复验由 root 负责。
