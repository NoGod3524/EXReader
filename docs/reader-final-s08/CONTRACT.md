# S08 诊断输出与账号信息泄漏验收

固定实现起点 `0889f7d1e9a537c6c1b05456547e016b26e1cd85`，独立分支
`codex/reader-fw-s08`。本包只新增 `tests/reader_final_s08/`、
`.github/workflows/reader-final-s08.yml`、`docs/reader-final-s08/` 与
`HANDOFF-RESULT.md`；现有任何文件只读。

## 复用而不是重写

J21 的凭据实现已进入固定起点（`e2247deb35b52615810508092441922c4e4f7913` 是
`0889f7d1` 的祖先），因此本包**不重写**它，也不改它的原测试。独立红 action 验收针对三个
已有模块的**公开接口**：

| 模块 | 公开面 | 本包使用的诊断面 |
| --- | --- | --- |
| `extras/credentials` 0.1.0（J21） | `exr_credentials_open/put/get/delete/status_name/wipe` | 仅状态名与数值状态；模块契约规定没有消息字符串 |
| `apps/reader/account-profiles` 0.1.0 | `load/add/rename/remove/prepare_activation/verify_activation/validate` | `reader_account_profiles_error{status,system_error,offset,message}` 与 `*_status_name` |
| `extras/opds` 0.2.0 | `opds_download_url`、`opds_client_stats`、`opds_redact_url`、宿主 `transport`/`log` 回调 | 客户端自己生成的请求行 `GET <redacted url> -> <status>` 与 `opds_error{code,http_status,auth_scheme,message}` |

`tests/reader_final_s08/consumer` 只链接**安装后的** `EXReaderCredentials`、
`EXReaderAccountProfiles` 包与 `extras/opds` 自己构建出的静态库（该模块不安装 CMake
包），不重新编译任何 owner 源码，不放宽任何原断言。

## 泄漏范围的准确边界

红 action 验收同时证明“该删的删掉”和“该留的留下”。秘密由 job 内 CSPRNG 生成，只在
进程内存在，经 stdin（不是 argv）传给消费者，从不打印。

| 类别 | 诊断/日志/工件中的要求 | 证据 |
| --- | --- | --- |
| 密码、token、二进制秘密（凭据值） | 任何编码都不得出现 | raw、32 字节窗口、hex/HEX、base64/base64url（含去 padding）、percent、UTF-16LE |
| `Authorization` 头值 | 不得出现在请求行、错误、报告 | 请求行只保留方法/来源/路径/状态 |
| cookie 形态的秘密 | 不得出现在请求行或诊断 | 以 `session=` 形态的随机值做封锁检查 |
| URL userinfo | 必须从请求行移除 | `http://user:pw@host:port/path?token=...` → `http://host:port/path?token=REDACTED` |
| 秘密命名的查询参数 | 值替换为 `REDACTED`（大小写不敏感匹配 token/password/key/session/auth/sig/credential 等） | `token=REDACTED&page=2`，非秘密参数 `page=2` **必须保留** |
| 用户本地路径 | 诊断不得携带 store/临时 HOME/工作区路径 | 账号错误 `message` 与请求行逐条比对 |
| 账号 URL 与显示名 | 账号错误 `message` 不得回显 | 对比本次 job 随机生成的 url/name |
| **必须保留**（禁止过度清洗） | 模块与操作名、状态名、数值状态、`system_error`、文档 `offset`、HTTP 状态、challenge scheme、请求方法、来源、URL 路径、非秘密查询参数、模块固定消息文本 | 每行 `diag` 的字段白名单 + 覆盖率 + 最小文本量断言 |

判定规则（`tests/reader_final_s08/scan.py::judge_diagnostics`）：

- 每个 `diag` 行只允许该模块的白名单字段；未知字段即失败。
- `credentials`：`status`/`code` 必须与枚举一致，且**不得**携带任何文本字段。
- `profiles`：失败状态必须有非空 `message`，不得只有 `REDACTED`；`IO` 必须带非零
  `system_error`；`FORMAT`/`VERSION` 必须带正 `offset`；消息不得包含路径/URL/显示名。
- `opds`：每行必须以 `GET ` 开头、含 ` -> <3位状态>`；`http` 行状态与 `http_status`
  一致；`auth_required` 必须保留 challenge scheme。
- 覆盖率：`credentials` 至少 OK/NOT_FOUND/ARGUMENT（Linux 另加 UNAVAILABLE）；
  `profiles` 至少 OK/SECRET/INVALID/CANCELLED/VERSION/FORMAT/IO/LIMIT/NOT_FOUND；
  `opds` 至少 ok/auth_required/http/aborted；`opds-redact` 必须全部 ok。
- 反过度清洗：profile 消息至少 5 条、总长 ≥60 且含字段/文档类关键词；请求行必须保留
  来源 `reader.test:8080` 与路径 `/shelf/reader/`。

## 实际驱动路径

每个阶段都是**新进程**，日志逐阶段落盘，全部参与扫描：

1. `opds`：宿主 transport 返回 200/401/500/跨源 302/传输中断，经 `opds_download_url`
   走正常、失败、取消与重定向；日志回调的每一行都进诊断导出。
2. `credentials`：空存储、写入/精确回读、更短值更新无残留、账号隔离、namespace 隔离、
   缓冲区不足、非法 ID/namespace、0 长度、NUL 二进制、Unicode、2048 上限、删除与重复删除。
3. `profiles`：空存储、三个隔离档案（同 URL 不同账号、同账号不同 URL）、两阶段激活、
   userinfo/query 拒绝、非法 UUID/名字/相对 store、`load(NULL)`、**公开 cancel 回调**
   （首次轮询与提交前）导致 `CANCELLED` 且 `profiles.json` 哈希不变、无 `.tmp`、
   VERSION/FORMAT 的 offset、IO 的 system_error、32 条上限。
4. `worker`：**独立子进程**写入一个档案与一条凭据后退出；父进程在它退出后立即扫描
   store、临时 HOME、全部日志。
5. `reopen`：新进程读回持久记录与隔离结果。
6. Linux 额外：私有 D-Bus + 临时 HOME 的 gnome-keyring；锁默认 collection 与“无服务”
   两条真实不可用路径，恢复后新进程确认**没有写入任何明文**（专用账号仍 NOT_FOUND）。
7. `cleanup` / `verify-clean`：只清理本 job 自己的记录，随后确认空存储与凭据消失。

红 action 自检（同一 job 内，使用本次真实秘密）：planted 的 raw/hex/base64/percent/
UTF-16 必须被检出；干净文件必须 0 命中；空消息、只有 `REDACTED`、携带 forbidden 文本的
诊断必须被拒；形状正确的诊断必须被接受（防止“一律拒绝”的假绿）。

## 平台矩阵

| 平台 | 本轮 | 说明 |
| --- | --- | --- |
| Windows Server 2022 x64 | 实际执行 | Credential Manager 当前用户、随机测试 namespace，只删自己的记录 |
| Ubuntu 22.04 x64 | 实际执行 | 作业私有 D-Bus + gnome-keyring + 临时 HOME，锁 collection 与无服务两条不可用路径 |
| macOS / iOS / Android | 未执行（pending） | 本包不声明这些平台的凭据后端验收；J21 原五个平台证据仍只按其原 run 引用 |

Windows 的 `UNAVAILABLE` 仍为 pending：J21 已记录低完整性进程、停止 VaultSvc、S4U 计划
任务在 CI 上都不足以触发它，本包不重复猜测，也不据此授予。

## 同源绑定

`.github/workflows/reader-final-s08.yml` 只由本分支与 `tests/reader_final_s08/`、
本 workflow、`docs/reader-final-s08/` 触发；矩阵 `max-parallel=2`，`concurrency` 保证同一
时刻只有一个 live run。`report` 作业下载本 run 的三个工件 ZIP，核对 id/名称/字节/
`sha256:` digest/有效期/工作流 run，再重算 ZIP 的 SHA-256、拒绝重复条目与越界路径、
逐文件比对包内 `report.json` 的 `manifest`，并要求报告中的 source/run/attempt/
platform/job、检查计数、`judge_problems=[]`、`detector.passed=true`、全部 scan 命中为 0。
`check_aggregate.py` 用合成工件对这些门禁做正反例回归。

## 复现

```bash
python3 tests/reader_final_s08/check_aggregate.py
python3 tests/reader_final_s08/guard.py --output build/s08-guard
# 平台作业（在 Actions 内）：构建三个 owner 模块、安装、再构建消费者，然后
python3 tests/reader_final_s08/runner.py --platform linux \
  --consumer build/s08/consumer/reader-final-s08-consumer \
  --credentials-prefix build/s08/cred-stage --profiles-prefix build/s08/profiles-stage \
  --output build/s08/evidence --scan build/s08/build-logs
```

本机（非 Actions）不执行上述任何构建/测试；本包全部结论来自 Actions 的真实 run，见
[validation.json](validation.json)。
