# S12：Unicode 路径与书库状态跨配置回归

本包只新增独立消费者、工作流与证据，不改任何现有文件。受测实现起点
`0889f7d1e9a537c6c1b05456547e016b26e1cd85`；受保护 SDK 树固定为批准的 3.41
`edddc463c06ed5731195cdb8f06b2df6dff7699e`（3.40 冻结树 `9854061b…` 在该起点上已被 3.41 替换，
工作流因此比对 3.41 子树，并照常通过 `001_catalog.sql` 的逐字节比对）。

## 1. 复用而不是重写

| 既有交付 | 本包如何复用 |
| --- | --- |
| G14 `tests/reader_unicode_interop/` | 复用"容器只放 UTF-16LE、argv 只放 ASCII 开关"的入口纪律，以及逐记录比较与跨平台逐字节相等的证据形状；不复制其消费者 |
| Raw metadata 0.2 独立包（`EXR_READER_METADATA_RAW3`，0.2.0） | 直接使用 `reader_metadata_open_raw_v3` 与同一 pending 意图协议，不重写 pending/journal 逻辑 |
| J09/J13 公开只读信息与账号隔离 | 原件入口仍走 `reader_catalog_attach`；账户隔离仍走 `EXReaderAccountProfiles`，不新增第二套目录规则 |
| 原 29 项 metadata 检查 | 不复制、不改动；本包只在其之外新增 Unicode/路径/字节稳定维度 |

消费者只 include 安装后的公共头，只链接安装后的公共目标：
`EXReaderProductCatalog::reader_catalog`、`EXReaderRevisions::reader_revisions`(0.4.0)、
`EXReaderCommands::reader_commands`(0.2.0)、`EXReaderDesktopMetadata::reader_desktop_metadata`(0.2.0)、
`EXReaderAccountProfiles::reader_account_profiles`(0.1.0)。不引入 WebView、服务器、第二份 SQLite 或 SDK 私有头。

## 2. 两个真实消费者

- `s12-consumer`（C++17，约 160 条记录）：账户隔离 → 原件入口 → raw metadata 0.2 → 重开 → 再次同步。
- `s12-c-consumer`（C11，18 条记录）：只走 C ABI 头，只读地重开同一个 Unicode 库，并用
  `reader_command_utf16` 复核计数边界。

`cases.bin` 是唯一输入：magic `S121`、版本 1、146 条记录，记录为
`(name, kind, bytes)`，kind 1/2 是 UTF-16LE 码元（kind 2 故意携带嵌入 NUL），kind 0 是 ASCII 标识。
所有 Unicode 文本与**所有 Unicode 路径分量**都在容器里，因此 argv 只出现
`--input`、`--root`、`--output`、`--local` 四个 ASCII 开关，不存在 ANSI 代码页损坏通道。

## 3. 覆盖矩阵（`tests/reader_final_s12/probe.cpp`）

| 区域 | 记录数 | 断言要点 |
| --- | --- | --- |
| `utf16.*` | 36 | 27 个文本/路径的精确 UTF-8 十六进制；非 BMP 代理对 4 字节；容量恰好/不足；16385 码元；NULL+0 码元；嵌入 NUL 被拒绝 |
| `account.*` | 20 | Unicode+空格 store 目录；NFC/NFD/大小写四种显示名逐字节保留且互不合并；同一 {account,url} 重复为 EXISTS；userinfo/query 为 SECRET、http/空格为空名为 INVALID；两个 profile 的隔离路径互不相同；计划被篡改拒绝；相对 store 目录拒绝；嵌入 NUL 的 store 目录不创建任何目录 |
| `attach.*` | 33 | 6 本原件的 Unicode/空格/制表/引号/非 BMP 标题与作者；重复 attach 幂等；(sort_title,book_key) 字节序全序与正反向 keyset 分页；仅 ASCII 折叠的搜索（`ÜNÏ` 不命中 `ünï`）；NFD 精确命中；`local_canonical_page` 的 NFC/NFD 两次调用各自只命中一本，不静默合并；NULL 与空串在 `lookup`/`metadata`/`query` 上分别为 MISUSE 与"空结果" |
| `metadata.*` | 37 | legacy 打开被拒、raw 打开成功；pending 路径不得等于产品库；第二个 owner 为 OWNER；NEEDS_BOOTSTRAP → 普通编辑被拒 → 已验证原件 bootstrap；**重开且意图仍在**时 sidecar 字节不变；finish 后 sidecar 消失；NULL 作者 ARGUMENT 与空串作者被接受并原样读回（`author_null=0`、`authorhex=""`）；NFD 标题改 NFC 后旧修订仍保留 NFD 原始字节；**陈旧 head 的意图只在提交时以 CONFLICT 拒绝**、产品行保持新值；**两个并发 head 时 prepare/stage 双双 CONFLICT**、两 head 与 titlehex 如实报告 |
| `resync.*` | 12 | 从主库取出的原样 wire 接收进镜像库：首次 created=1、再次 created=0；错 SHA 与篡改字节都被拒且不落库；重开后再次接收仍 created=0；投影后镜像行与主库行逐字段一致（`sdk=0`、`loc` 为 NULL）；`selected` 为 SAFE 且 wire 与主库逐字节相同 |
| `probe.*` | 11 | 大写 SHA、0 字节、SDK 0、NULL 标题均为 MISUSE；同 key 不同字节、同 SDK ID 不同原件均为 CONSTRAINT；空标题/空作者/空 sort 的空串行被接受且与 NULL 区分 |
| `path.*` | 4 | 约 210 字节的 Unicode 长路径上创建、attach、重开、读回 1 行 |
| `nul.product` | 1 | 嵌入 NUL 的路径：产品库拒绝打开（非零），诱饵文件字节不变；raw metadata 同样拒绝且不返回句柄 |
| `stability.*` | 6 | 重复 attach、重开、sidecar 重开、镜像二次接收/重开都是逐字节相同 |
| `c.*` | 18 | 同一库上 C ABI 的页、搜索、规范页、查找、元数据与 C++ 逐字段相同；NULL 与空串区分一致；`reader_command_utf16` 的 NUL 拒绝与 C++ 相同 |

`tests/reader_final_s12/check_s12.py` 另外独立复算：每个记录的 `sha256` 必须覆盖其 `hex` 载荷；
`metadata.wire.book1` 必须等于公开命令文档形状（把随机分配的 32 位十六进制 ID 代入模板）；
九组 C++/C 记录必须逐字段一致；五组字节快照必须相同；C 消费者只读运行后产品库必须仍等于
`main.final` 快照。

## 4. 明确不覆盖（不授予）

- 六平台 UI、宿主接线、读屏、真机：本包只有模块与路径范围。
- SDK 原件校验、原件导出、真实 WebDAV/网络同步：未构建 SDK，也未起网络。
- 性能/预算、旧 1710 计数、schema1 与 wire 的任何改动：一律不动，工作流逐字节比对
  `apps/reader/{store,revisions,commands,desktop-metadata,account-profiles}` 与 `001_catalog.sql`。
- 超过宿主路径上限（Windows 260 字节）的深路径：只记录在本平台本地证据里，不冒充通过。
- 嵌入 NUL 的 C 字符串：C 接口无法看到 NUL 之后的字节；本包证明的是"计数边界拒绝 NUL"与
  "被截断的路径不会把无关文件静默变成产品库"，不声称 C 字符串接口能自行检测 NUL。

## 5. 云端出口

`.github/workflows/reader-final-s12.yml` 只由本包分支与路径触发，矩阵 `max-parallel: 2`：

1. `source-preflight`：`HEAD == GITHUB_SHA`、实现起点为祖先、3.41 SDK 子树与 owner 目录未改、
   改动路径全在白名单、夹具冻结 + 静态记录一致性；
2. `unicode-regression (windows-2022|ubuntu-22.04)`：按安装顺序构建 5 个公共包与 2 个消费者，
   生成夹具，在 Unicode/空格/非 BMP/长路径上运行，逐记录比对并写 `report.json`；
3. `compare`：要求两平台 `observations.txt`、`c-observations.txt` 与夹具摘要逐字节相同；
4. `strict`：用既有 `tools/check_parallel_integration.py` 的 GitHub 助手重新下载并认证
   **原工件 ZIP** 的字节、`sha256:digest`、有效期与 run 身份，再逐个复算工件内的消费者二进制、
   观测文件与快照摘要。

## 6. 结果

见 `validation.json` 与 worktree 根的 `HANDOFF-RESULT.md`：未执行时 `accepted=false`，
执行后只填同一次 source/run/attempt 的真实值，失败原样保留。
