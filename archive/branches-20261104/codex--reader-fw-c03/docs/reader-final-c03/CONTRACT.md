# C03 账号、导入与同步故障边界复核（契约）

固定实现起点 `0889f7d1e9a537c6c1b05456547e016b26e1cd85`，分支 `codex/reader-fw-c03`。只新增 `tests/reader_final_c03/`、
`.github/workflows/reader-final-c03.yml`、`docs/reader-final-c03/`、`HANDOFF-RESULT.md`。
Root接手后固定合并独立WebDAV修复候选 `8cc57c078f50c7e81bd2a75620a4acf9b23bb456`；
原C03断言、SDK及其他owner保持原件，路径守卫另认证该候选逐文件身份。
当前Linux验收为run40220894221/1、24项通过；其他平台及下列pending不授予。

## 复用（只读）

- 已安装公开 API：`EXReaderWebDAV`、`EXReaderCloudImport`、`EXReaderSideload`、`EXReaderSync`/`Revisions`/产品库；
- 原独立消费者：`tests/reader_webdav_import/consumer`（`cloud-probe`）与 `tests/reader_sync_resilience/consumer`（`resilience-consumer step`），由本 workflow 从同一 checkout 构建，程序 SHA-256 写入 `result.json`；
- 不重复原 `check_cloud_import.py`（九格式/重复/篡改/取消扫描）与 G07（kill 边界、401/403/429/503、错误原件摘要）已覆盖项。

## 新增缺口（具名检查）

| 区域 | 检查 |
| --- | --- |
| 路径 | 12 种 `..`/`%2e`/`%2f`/`%5c`/反斜杠/NUL/绝对 URL/query/fragment/`./` 资源在任何请求前被拒；远端显示名永不成为本地路径；符号链接暂存目录不被穿透；恶意 PROPFIND href 不得逃出集合 |
| 重定向 | 同源出根、环、超预算、跨源、https→http 全部 `REDIRECT`，出根/外源路径无请求，外源无凭据 |
| TLS | 不受信证书、主机名不符：`TLS` 且服务端无 HTTP 请求；全程不关闭验证 |
| 凭据 | 缺失/错误口令 401，下载与同步均无产品写入；证据与日志无凭据（按随机口令扫描） |
| 中断/取消 | RST、停滞超时、流中取消：无半成品、无库文件、无行 |
| 原件身份 | 服务器换发不同原件：暂存摘要 ≠ 记录摘要，丢弃不导入 |
| 同步线格式 | 损坏 JSON、未知 version、未知字段、超 1 MiB、正文哈希与文件名不符、id 与文件名不符：不拉取、本地历史/outbox/缓存无变化、无远端写 |
| 同步越界 | 监听 href 含 `..`/`%2e`/外源、GET 重定向出根：不请求；无凭据/错凭据 401 不取正文；停滞超时无写入 |
| 账户 | 命名空间隔离；A 的库指向 B 的空命名空间不删除历史、不写远端 |

## 未覆盖（pending，不得视为通过）

平台凭据库锁定/拒绝（`reader-credentials` 工作流，需 OS keyring）；下载与导入之间暂存文件被换成符号链接（需新原生探针）；Windows/macOS/Android/Apple 执行；第三方真实 WebDAV 服务；真机。
