# WebDAV v1 实施契约

状态：待实现的首版协议，尚无网络客户端或互操作验收。产品范围见
[READER-PRODUCT-PLAN.md](READER-PRODUCT-PLAN.md)，本地存储见
[产品库契约](../apps/reader/store/README.md)。使用用户自有 WebDAV 的一个账号及专用目录，
保留本地优先、离线阅读；平台 HTTPS 客户端直接访问，不增加服务端或插件框架。

## 1. 目录、身份与限额

用户选定的 HTTPS 专用目录记作 `R/`，必须绑定 origin、规范化目录路径和 library ID。
路径只由下列受限标识生成，不包含书名、原始文件名或凭据。

| 对象 | 相对 `R/` 的精确路径 | 身份与上限 |
| --- | --- | --- |
| 初始化记录 | `library.json` | 不可变，UTF-8 JSON ≤4 KiB |
| 原书 | `objects/<format>/<sha前两位>/<sha>` | `format:sha256`；EPUB/PDF/CBZ ≤128 MiB，其他格式 ≤32 MiB；长度必须等于书籍修订声明 |
| 实体修订 | `revisions/<revision_id首位>/<revision_id>.json` | UUID 为32位小写十六进制；原始 UTF-8 JSON ≤1 MiB |
| 删除墓碑 | 同一修订路径 | `operation=delete`，首版永久保留 |
| 本机 outbox | `reader_outbox` 表 | `revision_id` 唯一，不上传本机队列 |

`format` 只允许 `epub/pdf/cbz/txt/html/fb2/docx/rtf/mobi`；SHA 为64位小写十六进制。
书架、标签、系列、标注、设备、library 和 revision ID 均使用随机 UUID 的32位小写形式。
本机 SDK book/note ID、数据库路径和凭据不进入远端对象。

初始化记录为 `{"protocol_version":1,"library_id":"<32 hex>"}`。
首次初始化用 `PUT library.json`、`If-None-Match: *`，随后回读验证。
双设备同时创建或请求结果不确定时，GET 并采用已存在且有效的 library ID；
重新绑定尚未发布的本地草稿后再生成修订，不以设备时钟选择赢家。
已绑定目录出现不同 library ID 时停止同步并要求重新选择库，不自动合并。
不设置全局可变书籍清单、head 清单或远端 outbox。

## 2. 修订 JSON

每次修改只序列化一次，原始字节写入 `reader_revisions.body_json`，
SHA-256 写入 `body_sha256`；上传、重试和重放比较均使用这些原字节。
散列不放进其自身被散列的 JSON。设备时间只展示，不参与顺序或胜负判断。

```json
{
  "protocol_version": 1,
  "library_id": "0123456789abcdef0123456789abcdef",
  "revision_id": "11111111111141118111111111111111",
  "device_id": "22222222222242228222222222222222",
  "entity_kind": "book",
  "entity_key": "epub:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "operation": "put",
  "parents": [],
  "payload": {
    "format": "epub",
    "source_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "source_bytes": 474733,
    "title": "Example",
    "author": "",
    "favorite": false
  }
}
```

上述字段全部必需。`entity_kind` 使用 schema 的
`book/shelf/tag/series/membership/progress/annotation`；`operation` 为 `put/delete/restore`。
`parents` 是本次编辑所见的该实体全部 head ID，最多64个，无重复或自身引用；
已知父节点必须属于同一 library、同一 kind/key。
没有父节点表示新实体，不能用空 parents 覆盖已有实体。
收到并发的首次创建仍须保留为多个 head。

| kind | entity_key | put/restore 的 payload |
| --- | --- | --- |
| book | `format:sha256` | 示例中的来源身份及完整显示元数据；来源身份不可变，`sort_title` 由本机生成 |
| shelf | shelf UUID | `name,parent_id,ordinal`；parent_id 为 UUID 或 null |
| tag / series | 对应 UUID | `name` |
| membership | 下述固定散列键 | `relation,container_id,book_key`；shelf/series 另有 `ordinal` |
| progress | book_key | `book_key,location_kind,parser_version,anchor_version,selector` |
| annotation | annotation UUID | `book_key,location_kind,parser_version,anchor_version,selector,comment` |

membership 的 `relation` 为 `shelf/tag/series`。统一令 entity_key 为
`member:` 加 `SHA256(UTF8(relation + "\n" + container_id + "\n" + book_key))`。
这些组成部分均禁止换行。payload 保留完整关系，ordinal 不参与身份；
不直接拼接任意长关系键，不超过现有 `entity_key` 的256字符限制，也不改 `001_catalog.sql`。

显示文本、非负整数、书架深度等沿用产品库约束；拒绝 NUL、重复 JSON 键、非有限数值、
类型不符和未知协议版本。严格核对 envelope 与 payload 的身份，所有数据库写入使用参数绑定。
delete 的 payload 为 `{}`，实体身份与因果 parents 仍完整保留；restore 包含完整新 payload。
selector 的版本化编码须另按公开 SDK 类型固定：`epub_chapter` 保留 part/path 与章内 selector，
`reflow_global` 保留全书 UTF-8 selector，`fixed_page` 保留 page_id 与固定页 selector。
编码与验证器未完成前，不接受进度/标注同步声明，也不把一种位置模式猜成另一种。

## 3. 创建、回读与离线重试

本地投影修改、不可变修订和 outbox 行在一个产品库事务内提交，离线也可完成。
上传 book 修订前，先上传原书并回读核对长度及 SHA；其他修订先满足其引用依赖。
新文件均使用 `PUT`、`If-None-Match: *`。`MKCOL` 只创建固定父目录，已有目录不算错误。

对 PUT 成功、超时、断线或 `412 Precondition Failed`，均 GET 同一路径确认：
修订按完整原字节比较，原书分块比较完整字节并核长度及 SHA。
首次 library 初始化按第1节采用现存有效 ID，将回读原字节保存为此后绑定的一致性基准。
相同才确认已提交；404 则保留同一 outbox 对象待重试；内容不同则报告身份冲突/损坏，
不能覆盖、换 revision ID 掩盖冲突或删除旧原件。确认成功后才删除 outbox 行，revision 不删除。
服务器改写 JSON 字节同样不满足协议。回读验证结果可以绑定 ETag 缓存。

ETag 是不透明缓存值，不能作为内容散列或因果顺序；已验证对象 GET 可使用
`If-None-Match: <etag>`。首版没有修改已有远端文件的正常操作。
服务器必须正确执行条件新建；连接验收须证明第二次条件 PUT 返回412且原件未变。
中断 PUT 后可见的不完整对象不能当作成功，须保留失败状态；不自动覆盖修复。

每次同步最多重试三次，临时网络故障/502/503/504 采用指数退避，429 遵守 Retry-After；
超过当前轮预算则持久保留到下轮。401/403 暂停并提示重新认证。outbox 的 attempts/last_error
只记录本机重试状态，错误须脱敏。进程重启以原 ID/原字节重放，不依赖上次响应是否送达。

## 4. 发现、依赖和冲突

对 `revisions/0/` 至 `revisions/f/` 执行 `PROPFIND Depth:1`，请求
resourcetype/getetag/getcontentlength；只 GET 未见或 ETag 改变的修订。
不依赖目录 ETag、mtime 排序或服务商专有同步令牌。普通 WebDAV 没有通用分页：
客户端逐条解析并分批处理；达到单响应上限时停止并报告未完成，不能把截断列表当完整。
未知/缺失目录、本轮未列出的旧对象、原书暂缺均不推导删除。

XML 禁用 DTD、外部实体和外部资源加载；上限为解码后4 MiB、10,000个 response、
嵌套深度32、单 href 2 KiB。逐项检查207 multistatus中的成功 propstat，跳过 collection 本身。
href 解析后必须同 origin、位于本次请求分片的直接子路径，且名称符合 UUID.json 规则。
拒绝 userinfo、查询/片段、点段、编码斜杠/反斜杠、跨目录及跨源结果，不能按任意 href 发带认证请求。

接收顺序不保证父先于子。未知 parents 或分类/原书引用保存为待依赖，继续发现/定向获取，
不能因先见到子就断言父不存在。未解决依赖不进入有效 head 或应用到 SDK。
验证父图无环、父身份一致；自环/回路拒绝投影并保留诊断，不能跳过检查后宣告有效。
图遍历分批执行，每批最多10,000节点；未完成验证继续待处理。
待依赖缓存最多256条且总计16 MiB，触顶暂停新增获取并提示恢复同步，不能丢弃已有历史。

有效修订覆盖其因果祖先；互不包含的多个 head 全部保留，形成冲突。
不同 payload 不按设备时间或 ETag 自动择一。解决冲突创建新修订，parents 覆盖所有竞争 head。
delete 与 put 并发时保留墓碑和修改，显示删除冲突；restore 必须显式包含墓碑和其余竞争 head。
旧 put 不构成恢复授权。跨实体修订合成的书架循环/超深树同样保留修订、暂停非法投影。
当前阅读不会被远端进度强制跳转；用户选择位置后仅公开 resolve 的 FOUND 允许精确导航。
歧义、缺失及不兼容位置保留原记录。

## 5. 网络、凭据与 SDK 边界

只接受 HTTPS，按系统信任策略验证证书。凭据按 origin 和账号隔离，目录/root 绑定另行检查；
跨源重定向不转发认证，也不自动把新 origin 加入信任；同源重定向最多五次，且须保持在 R/ 内。
URL 禁止内嵌 userinfo。
Apple Keychain、Windows Credential Manager、Linux Secret Service、Android Keystore保护的加密存储
持有凭据；安全存储不可用时仅当前会话保留。日志、SQLite、修订和证据不含认证头/密码/token。

响应按流计数，不能信任 Content-Length：library/revision/PROPFIND 使用上述限额，
原书使用声明长度与格式上限中较小者；压缩响应按解码后的字节同样限额。
原书写私有临时文件，完成验证后原子发布再走 sideload，不把半文件交给 SDK。
网络、哈希和 XML/JSON 解析在后台；SDK source 的使用/释放及写入仍在其 owner 队列，
不要从网络线程持有 source 回调或向 SDK 数据库开第二个写连接。
TLS 保护传输，云盘端保存原书和修订；本协议未实现端到端加密。

## 6. 首版实现与验收出口

以下各项均待实现/验收，现有 schema 合同检查不替代网络证据。

| 项目 | 最小实现 | 云端出口 |
| --- | --- | --- |
| Envelope/因果图 | 严格验证器、原字节重放、依赖队列与多head | 两设备乱序、缺父、循环、ID复用、并发删除/恢复 |
| WebDAV传输 | 平台HTTPS、条件新建、有界XML/响应、ETag缓存 | 实际WebDAV服务的PUT/GET/MKCOL/PROPFIND；412、响应丢失、限流、断传、跨源与实体拒绝 |
| 本地同步状态 | library绑定、远端对象校验/ETag、本机重试状态 | 离线编辑、重启、逐阶段中断后幂等恢复 |
| 投影/SDK映射 | 本机annotation UUID→SDK note ID/类型/最后应用修订；产品进度与冲突状态 | 重放不重复建标注，原书去重保留旧标注，歧义不跳转 |
| 原生客户端 | 接产品库及既有owner队列，后台传输，显式冲突UI | 至少两设备同步原书、整理、进度和标注；六目标分别登记真实流程 |

parents/device等字段可存现有 body_json；远端状态、父/head索引和本机标注映射需要产品层明确实现，
新增持久表使用独立迁移，不修改或重跑001。固定页进度的SDK接口缺口单独跟踪：
产品层保存不等同SDK位置字段已更新；如需新增公开接口，应独立SDK版本及重新冻结。
首版不回收原书、历史修订或墓碑，不同步活的SQLite文件。
