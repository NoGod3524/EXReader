# G14：Unicode 路径、名称与跨平台产品回归

本包只新增**安装后公开组合消费者**（独立测试、工作流、文档），不修改 SDK、产品 schema1、
既有 wire v1 与数值预算。受测源码固定为实现起点
`f43baf9182d75907c0cb5d6f77048f27bca8c950`，SDK 保护树固定为
`9854061be331fe603a1822d9b2b36ee357154927`。

## 1. 受测对象与不变项

| 项目 | 取值 | 本次是否改动 |
| --- | --- | --- |
| 产品 catalog（`EXReaderProductCatalog`） | 实现起点 | 否，只链接安装后的公共目标 |
| 投影/修订（`EXReaderRevisions`） | 实现起点 | 否 |
| 类型化命令（`EXReaderCommands`） | 实现起点 | 否 |
| 产品 schema（`apps/reader/store/001_catalog.sql`） | user_version 1 | 否，工作流逐字节比对 |
| SDK 保护树 | 上述 K | 否，工作流 `git diff --exit-code K HEAD` |
| wire v1 信封 | 既有字段集合 | 否，只作为输入字节 |

消费者只 include 安装后的公共头（`catalog.h`、`reader_revisions.h`、
`reader_projection.h`、`reader_commands.h`），不读 SDK 私有 SQL、不引入
WebView、不新增服务器或解析器。

## 2. 消费者身份与真实 UTF-16 入口

两个消费者都用**同一份**二进制请求容器 `cases.bin` 取输入：

- `unicode-consumer`（C++17，安装后 `EXReaderCommands`+`EXReaderRevisions`+`EXReaderProductCatalog`）
- `unicode-c-consumer`（C11，只链接安装后的 C ABI 目标）

argv 只出现 ASCII 开关（`--input`、`--output`）。**所有 Unicode 文本与所有
Unicode 路径都以 UTF-16LE 码元存放在容器里，由 `reader_command_utf16`
（`commands.h` 明确标注的 JNI/Windows 边界）转换成严格 UTF-8**，因此不存在
"F5 测试参数被 ANSI 代码页损坏"的通道。容器同时携带冻结的 URI 相对路径
（`build/图书馆-📚/café-组合/café-书库-A.sqlite3`），使 SQLite 真正在
Unicode 目录/文件名上创建、写入并二次打开。

消费者**不做**任何规范化、大小写折叠或预期计算：它只记录公共 API 返回的
状态码、字节（十六进制）、键、行序和 SHA-256，逐例写入 `observations.txt`。

## 3. 冻结输入与独立预期

`tests/reader_unicode_interop/fixtures.py` 是唯一输入源，同时生成
`cases.bin`、`expected.json` 和 `meta.json`。预期值全部由该脚本按
**公开契约**（schema 1 的 `length()` 约束、`catalog.h` 的 keyset/搜索注释、
wire v1 信封字段）在 Python 侧独立实现后写死，**不调用被测实现生成预期**：

- 排序预期 = 对冻结的 `sort_title`/`book_key` 字节做 `sorted()`（等价于 SQLite
  BINARY collation 的 memcmp）；
- 搜索预期 = 只折叠 ASCII A-Z 的子串匹配（`lower()` 的既有契约），不引入任何
  Unicode 折叠；
- 修订预期 = 按 `commands.cpp` 文档化的引号规则（`"`、`\`、`<32` → `\u00XX`）
  独立重建信封字节并取 SHA-256；
- `reader_command_utf16` 预期 = 按头文件契约（≤16384 码元、无 NUL、无孤立代理、
  ≤16384 输出字节）独立判定。

因为容器只含相对路径、且所有预期值都不含主机路径，`cases.bin` 与
`expected.json` 在三个宿主上**逐字节相同**，跨平台比较因此比较的是真实输出而
不是路径差异。

## 4. 覆盖矩阵

冻结文本包含：中文（红楼梦/曹雪芹）、组合 emoji（👩🏽‍💻、👨‍👩‍👧‍👦、🇨🇳）、
NFC/NFD 成对（Café、Ångström、한）、带元音的希伯来文、俄文、阿拉伯/希伯来混排、
RTL 控制符（U+202B/202C/200F/2067/2069）、平台保留字符（`a/b\c:d*e?f"g<h>i|j`）、
制表/换行、4096 字符与 16384 字节边界串、4097 越界串、256/257 分组名边界。

| 环节 | 记录（示例子集） | 断言 |
| --- | --- | --- |
| UTF-16 入口 | `utf16.t.*`、`utf16.capacity_small`、`utf16.null_input` | 状态/字节数/精确 UTF-8 十六进制；拒绝 NUL、孤立代理、16385 码元、16384+ 字节 |
| 导入（attach） | `attach.b1..b14`、`attach.neg.*`、`remove_local.b14` | 原件身份 attach 成功；非法 UTF-8（孤立续字节/超长编码/截断/代理/超 U+10FFFF）、4097 标量、非法 format、大写 SHA、无法与既有身份一致的字节数/SDK 映射全部被拒绝且不写入 |
| commands 提交 | `cmd.put.*`、`cmd.del.*`、`cmd.res.*`、`cmd.mem.*`、`cmd.neg.*` | created/applied、修订 SHA/字节、entity_key；精确重试为 0/0 空操作；同 ID 不同字节为 COLLISION；越界文本 LIMIT/FORMAT；缺历史 NEEDS_BOOK_BOOTSTRAP |
| catalog 排序查询 | `page.all`、`page.p0..p2`、`page.rev0..rev1`、`query.*`、`local.canon*` | 全序 = 字节序；正反向 keyset 分页不重不漏；ASCII 折叠命中、**Unicode 不折叠**（`ÜNÏ` 不命中 `Ünï`）、NFD 精确命中；`inclusive` 游标 |
| 子书架/标签/系列 | `groups.shelf.roots/children`、`groups.tag`、`groups.series`、`removed.*`、`gb.*`、`gbq.s1`、`membership.*`、`group_find.*` | (ordinal,id)/(ordinal,book_key)/id 字节序；软删除后仅剩删除组；成员连接在书软删后仍可查但列表隐藏 |
| revision 传输/投影 | `rev.get.*`、`rev.heads.*`、`rev.selected.*`、`rev.title.*`、`rev.validate.*`、`rev.entities.*`、`rx.*`、`proj.*`、`rx.neg.*` | 原件字节与 SHA 完全保留；远端 receive 后逐条 project 得到与写入端相同的最终状态；错误 SHA/篡改字节/非法 UTF-8/截断被拒绝且不落库；重复 receive 为 created=0 |
| 二次重开 | `re.*`（全部读取记录的重放） | 关闭并重开后字节、SHA、排序、分组、选择状态与首次一致 |
| 跨库一致 | `b.*`（镜像库的同一读取集合） | "本地写入"与"远端接收+投影"两条路径得到逐字段相同的 catalog |
| 传输转义保真 | `esc1.*`/`esc2.*` | `\u00e9`、`\uD83D\uDCDA`、`\u0009` 等转义按 JSON 解码为语义文本，但**保留字节逐字不变**（不做再编码/规范化） |
| Unicode 路径 | 上述全部 | 数据集与三个库都位于 `图书馆-📚/café-组合` 下，并由同一路径字符串重开 |

## 5. 明确未覆盖（不授予）

- **排版正确性**：本包只证明字段字节、排序键与连接关系一致，不证明字形选择、
  双向排版呈现或断行；RTL 控制符只作为普通字节参与存储与排序。
- **读屏/无障碍**：未涉及任何屏幕阅读器行为。
- **NFC 转换实现本身**：按公开契约，`sort_title` 由宿主转换后传入；消费者使用
  **冻结的** NFC 形式，只验证"产品不做隐式规范化/折叠"，不验证
  `NormalizeString`/`g_utf8_normalize` 的等价性（该实现在 SDK 绑定的桌面适配层，
  本包不构建）。
- **SDK 原件校验路径**：`catalog_sdk.c` 需要 SDK 库；本包以"宿主已校验"的
  冻结 SHA/字节调用 `reader_catalog_attach`，不覆盖 `reader_catalog_sdk_original_identity`。
- **性能/预算**：未测量，也未改动既有预算或 CPU 基线。
- 真实用户文档与旧 1710 目标不纳入本包计数。

## 6. 云端出口

`.github/workflows/reader-unicode-interop.yml` 在
`ubuntu-22.04`、`windows-2022`、`macos-14` 上对**同一受测 SHA** 执行：

1. 门禁：`HEAD == GITHUB_SHA`、实现起点为祖先、SDK 保护树与起点相同、产品 SQL
   与起点相同、`apps/reader/{store,revisions,commands}` 未改、改动路径全在白名单；
2. 构建并安装三个原有公共组件，再单独构建消费者（只走 `CMAKE_PREFIX_PATH`）；
3. 生成冻结夹具，运行两个消费者（一次 Unicode 路径会话）；
4. `check_interop.py` 逐记录比对预期，并独立复算每个修订/SHA 覆盖关系与
   行计数一致性、别名（重开/镜像）与规范记录的一致性；
5. 上传逐例原始结果、消费者二进制与身份、日志；
6. `compare` 作业下载三平台工件，`compare_platforms.py` 要求三份观测
   **逐记录逐字段相同**，且每份 per-platform 报告本身 `ok`、夹具摘要一致。

### 云上结果（同一次 source/run/attempt）

受测源码 `180a0679f364b4cfbb23454f564f847b1ad4cde2`，run **40079696724**，
attempt **1**，四个作业全部 `success`；逐项明细与工件身份见
[`docs/validation/reader-unicode-interop.json`](validation/reader-unicode-interop.json)。

| 宿主 | 观察者记录 | C ABI 记录 | 观察文件 SHA-256（前 12 位） | 结论 |
| --- | --- | --- | --- | --- |
| windows-2022 | 359/359 | 8/8 | `acf30ac2619c` | 通过 |
| ubuntu-22.04 | 359/359 | 8/8 | `acf30ac2619c` | 通过 |
| macos-14 | 359/359 | 8/8 | `acf30ac2619c` | 通过 |

- 三个宿主的 `observations.txt`（`acf30ac26…`）与 `c-observations.txt`
  （`e0bf6c5b04…`）**逐字节相同**；
- 冻结夹具 `cases.bin` = `006fdd57…`、`expected.json` = `d9007113…`，
  三个宿主完全一致；
- 命名分组（每个宿主相同）：`utf16` 42、`attach` 28、`cmd` 58、`page` 6、
  `query` 7、`local` 4、`local_lookup` 4、`has_local` 2、`find` 4、
  `meta` 5、`groups` 4、`removed` 2、`gb` 8、`gbq` 1、`membership` 2、
  `group_find` 2、`rev` 77、`rx` 49、`proj` 44、`esc` 9、`remove_local` 1，
  合计 **359**；
- 消费者二进制（同一源码各自构建）：Windows `5e7fe71c…`、Linux `17080452…`、
  macOS `9154290a…`；C 消费者 `c7174594…` / `99be47b8…` / `4087d980…`。

### 本轮早期失败（保留，不转为通过）

| run | 源码 | 原因 | 处置 |
| --- | --- | --- | --- |
| 40077452184 | `296f14d2` | 消费者 `reader_catalog_remove_local` 少一个参数（三平台同一诊断） | 修消费者 |
| 40077722660 | `c36dd051` | 夹具 `KeyError: 'sha'`（模型缺原件摘要） | 修夹具 |
| 40078131000 | `544b1335` | 夹具 `KeyError: 'path.workdir'`（路径项读已删除的 aux 命名空间） | 修夹具 |
| 40078512406 | `3ca59e32` | 359 条里 1 条不符：`cmd.neg.collision` 报 UNSAFE 而非 COLLISION（夹具未复用既有修订 ID，未走到冲突分支）；同时校验器把 `rows` 误当行字段 | 修夹具与校验器，**断言未改** |
| 40078923261 | `a5e400c3` | 三个消费者作业已 359/359、8/8，但比较作业发现夹具摘要不同：Windows 用 CRLF 写 JSON 夹具 | 统一 LF |

这些失败只作为历史记录；本包的通过证据只取上表那一次
source/run/attempt，且不把早期 run 的结果拼接到当前源码。

## 7. 本地复现（仅供审阅，不在本机执行）

```
cmake -S apps/reader/store/native -B build/product -G Ninja -DCMAKE_INSTALL_PREFIX=$PWD/build/stage-product
cmake -S apps/reader/revisions -B build/revisions -G Ninja -DREADER_PRODUCT_PREFIX=$PWD/build/stage-product -DCMAKE_INSTALL_PREFIX=$PWD/build/stage-revisions
cmake -S apps/reader/commands -B build/commands -G Ninja -DCMAKE_PREFIX_PATH="$PWD/build/stage-revisions;$PWD/build/stage-product" -DCMAKE_INSTALL_PREFIX=$PWD/build/stage-commands
cmake -S tests/reader_unicode_interop/consumer -B build/consumer -G Ninja -DCMAKE_PREFIX_PATH="$PWD/build/stage-commands;$PWD/build/stage-revisions;$PWD/build/stage-product"
python3 tests/reader_unicode_interop/fixtures.py --base build --out build/fixtures
build/consumer/unicode-consumer --input build/fixtures/cases.bin --output build/evidence/observations.txt
build/consumer/unicode-c-consumer --input build/fixtures/cases.bin --output build/evidence/c-observations.txt
python3 tests/reader_unicode_interop/check_interop.py --fixtures build/fixtures --observations build/evidence/observations.txt --c-observations build/evidence/c-observations.txt --consumer build/consumer/unicode-consumer --c-consumer build/consumer/unicode-c-consumer --platform linux --source $(git rev-parse HEAD) --output build/evidence
```
