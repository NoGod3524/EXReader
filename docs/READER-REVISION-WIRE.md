# 产品修订 v1：不可变记录与离线 outbox

本协议供后续 WebDAV 同步使用，不是已经运行的跨设备同步客户端。
一期只保存修订、因果关系和本机发送队列，不自动改变产品实体 projection、SDK 书库或当前阅读位置。
SQLite 使用现有 EXRP/schema1 的 `reader_revisions` 和 `reader_outbox`；不修改迁移或增加表。

## 封装

UTF-8 JSON 对象固定为：

```json
{"version":1,"id":"0123456789abcdef0123456789abcdef","entity_kind":"tag","entity_key":"fedcba9876543210fedcba9876543210","operation":"put","location_kind":"none","parents":[],"payload":{"name":"旅行"}}
```

另允许可选 `display_time` 字符串，仅用于展示，不能选赢家或覆盖其他头。
其他封装字段、重复对象 key、无效 UTF-8、NUL、JSON5 和尾随数据均拒绝。
每份原件最多1 MiB、20000个值、32层、32个不同父ID；ID为32位小写hex。
原字节与SHA-256一起保存，不重新序列化或把等价JSON当作相同原件。

实体类型为 `book/shelf/tag/series/membership/progress/annotation`。
book与progress的key是 `format:sha256`；shelf/tag/series使用全局UUID；
membership的key是 `collection_kind:collection_id:book_key`；annotation是 `book_key:annotation_id`。
SDK行号、连接路径和运行中的SQLite文件不进入协议。

`delete`的payload必须为null。`put/restore`的payload按实体类型严格验证：

| 实体 | payload |
| --- | --- |
| book | format、source_sha256、source_bytes、title、author、favorite；原件身份须与key相同 |
| shelf | name、parent_id（UUID或null）、ordinal |
| tag／series | name |
| membership | book_key、collection_kind（shelf/tag/series）、collection_id、ordinal |
| progress | book_key、location |
| annotation | book_key、annotation_id、location、text |

排序用的NFC key由宿主根据标题生成；不会传输本机派生排序缓存。
书名／作者最多4096 scalar／16384字节，分类名最多256 scalar／1024字节。
文本、selector及其他字符串仍有各自限额，不把1 MiB允许值直接当作任意字符串限额。

## 阅读位置

progress/annotation每份修订都有显式 `location_kind`；其余实体必须为 `none`。
删除记录仍保留该模式。location对象包括 `mode/parser_version/anchor_version`，且mode与封装相同。

- `reflow_global`：selector。
- `epub_chapter`：part_path和selector，仅用于EPUB。
- `fixed_page`：page_id、page和selector，仅用于PDF/CBZ。

selector固定为 `exact/prefix/suffix/start/end`；start/end是非负UTF-8偏移提示，不能替代引文解析。
exact非空、最多65536字节，prefix/suffix各最多4096字节。
path、page identity和parser/anchor version随原件保留。宿主只在公开resolve返回FOUND时定位，
歧义和缺失继续保留原修订；本包不声称这些selector已由SDK验证。

## 因果与队列

父ID构成同实体DAG，不使用设备时间。远端缺失父允许先入库；父后到时重新计算完整性。
已知跨实体父拒绝；若先前缺父后来证明属于另一实体，原记录留存并标成foreign-parent，禁止自动projection。
成环的新增记录拒绝。每实体最多4096份历史；达到上限返回限额错误，不删除历史。

没有被其他同实体记录引用的修订均为头。并发头全部保留，缺父头不能掩盖成安全单头。
delete是保留的墓碑；后继普通put不能隐式复活。restore必须直接命名delete父，
并且通过父集覆盖其余并发分支；未覆盖的头仍然存在，projection_safe仍为false。
restore之后的正常put可以沿已恢复分支继续，但新的并发分支会再次使projection不安全。

local只在一个事务中保存revision和outbox；receive不产生outbox。
同ID／同字节幂等，ack后重试也不重新入队；同ID／异字节拒绝。
ack要求远端已验证的SHA，删除队列行但保留历史。失败重试只增加本机attempts和固定错误token，
不保存任意URL、认证头或服务器错误正文。

本模块不暴露任意SQL callback。宿主metadata与revision的联合写入、远端不可变对象命名、
上传条件、两设备发现／传输、冲突UI及产品联合验收在后续阶段实现，不能用本期数据库验证代替。
