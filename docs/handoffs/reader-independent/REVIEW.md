# 第1轮接收与审查

本记录不累计完成轮数。下列源码审查发现尚须Actions回归或修复；此前单包绿只证明当时的测试范围。所有包收口并在共同源码复验前，`completed_cycles=0`。

## G02：缩略图，退回修复

原交付HEAD `1168e2f46b812b683c4376a5a586e04c3bdfafbd`；受测`797774f283f17901161346a0938a0c0e81e4c118`，run`40078420397`。

root审读`apps/reader/thumbnails/src/thumbnails.cpp`与其消费者后发现：

- `write_index`用`filesystem::rename`覆盖已有索引；Windows失败后只删除临时文件，既有测试没有证明实际跨进程LRU顺序。
- 临时文件用可预测名称和截断打开。必须证明预置hardlink/symlink不会覆盖缓存外文件，并使用独占创建、no-follow与原子发布。
- 打开缓存时先保留整个目录路径vector和全部有效entry，再最终淘汰；峰值不受缓存条目上限控制。需逐条有界扫描/淘汰及明确工作上限。
- `rth_cache_stats`未检查busy，与所有入口拒绝回调重入的合同不符；C ABI的分配/文件系统异常边界也须补齐。

旧检查保留，新增独立回归先在Actions证明原缺口。原Claude已结束；DeepSeek Flash1017 High/PTC/完全权限接管原G02工作树回修。未经root复审不进入本轮集成。

## G06：本机下载，审查发现待回修

原交付HEAD `4f00f6bf5af9b995486b39a1d3e2ff7d56fbdf39`；受测`7817caa968ce9350ed1c6b3712d31a13c2da8fd8`，run`40079478242`。

root审读`apps/reader/local-downloads/src/local_downloads.c`：

- `reader_ld_reimport`先散列路径并关闭文件，随后SDK重新打开该路径导入，未核对实际导入原件的身份就attach。需要固定输入被替换的回归，保证导入和全局book key的字节身份一致。
- intent只读固定前缀，未验证文件EOF；数字采用宽松转换，未知/重复字段不拒绝。应严格拒绝尾随、嵌入NUL、超限和字段损坏，并保留两库及原intent。
- 固定`intent.tmp`截断写入与目录跟随会绕过私有状态边界；须验证外部sentinel不被截断或清理。
- 明确回调中recover/remove/reimport的重入合同，避免回调推进外层durable状态。
- 原31项覆盖TXT/EPUB/CBZ，未覆盖PDF等格式的移除/重导入与路径寿命；补齐实际格式出口。

这些是源码审查结论，不是已经运行过的失败测试。原交付记录不删除，新候选需三平台同源复验。

G06已由原G14完工后的空闲DeepSeek会话接管原工作树；G14交付保持不动。

## G03：阅读命令，退回自动身份重试修复

DeepSeek接续交付HEAD`207778d8ef0b20f8945a8c8d64c7c3881205e62d`，受测`6ba1ad0d0c3c74dfc5c5267521f60dfd3210a48a`，run`40081701747`四作业成功，root已独立核对作业接口。

root发现新书签/高亮在空`annotation_id`时每次随机生成身份。首次响应丢失后，以相同稳定`revision_id`和相同空身份输入重试，会生成不同实体的wire，造成碰撞而非精确no-op。已要求原接续owner补云端回归和稳定身份根因修复，保留原检查和旧通过记录；暂不交宿主采用。

## G05：标注导出，退回实体快照与路径别名修复

原交付HEAD`14fb43bc6104ef0483b786423550742128589d32`，受测`d7ad100b67dca6d0cd0dae97262e5e1d419fd0b2`，run`40079793192`。

非SAFE实体会在较晚的`heads`快照取得graph和头列表，却继续输出较早page行的selection/tombstone与统计。并发补父、merge或restore可使单实体导出的状态与实际头不一致；应从同一公开快照得出该实体的全部状态。

两个输出路径只用字符串比较判重，`dir/out`与`dir/./out`等别名可以发布到同一个文件。要求发布前拒绝别名，保留原有效输出，并补回调重入的拒绝性回归。原19项与wire精确字节检查不减。

原G07完工会话已以Flash1017 High/PTC/完全权限接管G05原工作树。此回修仍属于第1轮收口，原G07交付不再编辑。

## 主线证据核对

root已通过GitHub作业接口独立核对：iOS run`40080841137`的producer和严格汇总均success；Android run`40081333678`实际模拟器作业success；同源codec run`40081333621`的Windows/Linux作业success。正式SwiftUI/Android账号和阅读界面的接线继续由各主线owner实施，不借测试壳授予产品界面。
