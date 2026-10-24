# 接收后的产品书架更新

网络worker只接收不可变修订/原件，不接触SDK owner或立即改当前阅读位置。
宿主在SDK/product owner上显式发现修订、处理安全metadata、再导入下载的原书。

`reader_revision_entities_page` 按指定kind读取原历史，复用schema1索引，双向keyset、
每批1..100个全局entity_key，一个读快照。同一实体多条修订只返回一行。
SAFE返回精确wire与metadata；缺父、并发、隐式恢复只返回状态，不替用户选内容。
删除保留为墓碑。回调中只复制结果，不能重入；应用动作在分页返回后进行。

对非删除book，`reader_revision_book_title` 从给定不可变revision_id复制精确title。
宿主复用自己的NFC转换生成sort_title，不改原wire/title。随后调用已有
`reader_revision_project(kind,key,expected_head,sort_title)`，在写事务内重查唯一安全头。
分页后收到新修订会使旧expected_head拒绝；不拿旧快照覆盖新metadata。

book、shelf、tag、series、membership均可发现；后者仍受现有活动依赖约束。
子书架先于父书架时维持pending，宿主显式投影父项后重试；不自动恢复被删除父项。
progress/annotation使用产品记录及公开SDK resolve，不能用metadata投影写入当前位置。

本接口不额外写历史/outbox、不ack、不修改SDK或产品schema，也不创建调度线程。
宿主接入仍需有界分批、父依赖重试、冲突显示、原件校验/下载导入和视图刷新；
该接口本身不宣称后台扫描完成就能打开所有云端书籍。

候选在同源Windows/Linux原生作业验证235实体双向分页、七kind隔离、全部状态、
所有权/重入、真实第二连接快照、原样NFD标题到宿主NFC、实际metadata投影、
父依赖及分页后新head围栏，共12项。原32项投影、阅读协议/分页/导出/会话/HTTPS
套件保留。

受测源码`2cbdd49ba9920afb5246e4b5b904e1ab28345169`，run`40061634535`，
attempt1，五作业全部成功；两平台各12项通过，严格作业`120777162291`重新散列
四ZIP并校验本包及全部保留报告，`accepted=true, problems=[]`。
五工件同源、非空、未过期，完整身份见
[接收发现与投影验收](validation/reader-remote-projection.json)。

后续HTTPS消费者进一步接入这条路径：A原子提交metadata+history+outbox，B收到
四份book后先按SAFE head投影，再实际导入下载原件并建立本机映射，核对云端
title/author/favorite不被导入默认值覆盖。这项端到端加强已在源码
`fb30036af7e23314f4d5949ebf219b92447d1bc9`、run`40062187051`、attempt1
同源五作业全部通过；两平台各投影4本，22条修订及18个阅读捕获经真实原生HTTPS往返，
17 FOUND/1预期歧义、零误定位。严格汇总重新核对四ZIP，`accepted=true, problems=[]`。
工件与逐平台计数见[metadata往返验收](validation/reader-metadata-webdav.json)。
这是原生消费者出口；宿主账号界面的分批调度、冲突呈现和刷新继续接入。
