# 产品元数据与修订的受限事务

本阶段在现有产品EXRP/schema1上增加固定实体API，不修改SDK或迁移，不提供通用SQL callback。
它接续[WebDAV原件与修订传输](READER-WEBDAV-SYNC.md)，把传输与宿主书架之间的原子边界具体化。
云端验收尚在执行；UI接线、真实设备和跨平台产品联合验收仍独立进行。

## API

安装`EXReaderRevisions 0.3.0`，包含`reader_projection.h`。
`book/shelf/tag/series/membership`可写现有产品metadata表；progress/annotation以不可变修订payload为权威。

`reader_revision_local_project`在同一产品连接的BEGIN内比较当前完整head集合、宿主的
`expected_heads`与新wire的parents集合；三者必须相同，最多32个父ID。随后一次保存
history、outbox与metadata。任何阶段失败均回滚三者；不能先在另一个catalog连接改metadata，
再调用原revision_local来拼接事务。

已保留的同ID／同字节先核对后no-op，`created=applied=0`，不回放旧metadata或重新入队；
同ID／异字节拒绝。既有plain revision不会因重复local_project被偷偷投影，宿主可显式请求当前safe head。

`reader_revision_project`在BEGIN内重新计算当前完整、唯一、安全head，必须精确匹配
`expected_head`才改metadata。它不插history或outbox。过时选择、缺父、并发头、隐式复活、
缺活跃依赖或数据库约束失败均拒绝应用；远端历史继续保留待处理。

book的`book_sort_title`只取宿主既有NFC转换结果，作为本机派生排序缓存；
wire原始字节不重写。SDK本地书号／location_kind映射保持不动。

## 选定payload与阅读

`reader_revision_selected`在同一只读快照返回以下明确状态：

| 状态 | 返回码 | wire |
| --- | --- | --- |
| MISSING | NOT_FOUND | 无 |
| PENDING_PARENTS（含foreign parent） | UNSAFE | 无 |
| CONCURRENT | UNSAFE | 无 |
| BLOCKED_RESTORE | UNSAFE | 无 |
| SAFE（含明确delete） | OK | 原字节副本 |

完整graph状态仍随结果返回；安全delete通过`deleted`区分。宿主可以显示所有冲突头，
不能把UNSAFE当成某个时间较新payload的成功。progress/annotation只从该权威payload读取；
用户明确恢复阅读时，按显式位置模式走公开SDK解析，只有FOUND才定位。
远端进度不自动跳转活跃session。

## 分类与删除

书／子书架／标签／系列删除只设置`deleted=1`，保留身份、成员关系和原有历史。
membership删除只删除派生join行，其delete修订与墓碑继续保留。没有级联删除和远端回收。
未知分类墓碑可形成隐藏的ID占位记录；book墓碑必须等到非删除历史给出原件长度后才能投影。

membership新增／修改要求书与分类均活跃；子书架父必须活跃。
现有外键、八层深度及环检查继续执行。删除父分类不改其子项或成员，宿主应显示保留项，
由用户明确移动／恢复；本API不把隐藏父当成授权级联删除。

SDK库与产品目录是不同数据库。SDK原书导入后，再提交本产品事务；失败时保留SDK去重结果，
用既有repair路径重试映射，不能删旧SDK书来模拟跨库回滚。
本阶段不把SDK标注镜像、UI、同步安全凭据或两数据库写入包装为原子。
