# 第1轮接收与审查

本记录不累计完成轮数。下列源码审查发现尚须Actions回归或修复；此前单包绿只证明当时的测试范围。所有包收口并在共同源码复验前，`completed_cycles=0`。

## G02：缩略图，退回修复

原交付HEAD `1168e2f46b812b683c4376a5a586e04c3bdfafbd`；受测`797774f283f17901161346a0938a0c0e81e4c118`，run`40078420397`。

root审读`apps/reader/thumbnails/src/thumbnails.cpp`与其消费者后发现：

- 初审怀疑`filesystem::rename`在Windows不能覆盖已有索引；后续原源码回归证明此假设在windows-2022未重现，MSVC STL执行了替换，原跨进程LRU身份断言也通过。实际重现的是索引替换失败被吞掉、临时文件安全和重入问题。回修同时保留平台原子替换及写入失败的明确状态。
- 临时文件用可预测名称和截断打开。必须证明预置hardlink/symlink不会覆盖缓存外文件，并使用独占创建、no-follow与原子发布。
- 打开缓存时先保留整个目录路径vector和全部有效entry，再最终淘汰；峰值不受缓存条目上限控制。需逐条有界扫描/淘汰及明确工作上限。
- `rth_cache_stats`未检查busy，与所有入口拒绝回调重入的合同不符；C ABI的分配/文件系统异常边界也须补齐。

旧检查保留，新增独立回归先在Actions证明原缺口。原Claude已结束；DeepSeek Flash1017 High/PTC/完全权限接管原G02工作树回修。未经root复审不进入本轮集成。

第一轮回修`00f3d3713619bef8f41c4f5d97957d37dbb3ed87`、run`40083975196`已通过其原158/159项与9项新增回归，文档HEAD`f1912d45c5a599f575f32d2d6df225c31c28a193`。root二次审查仍未放行：扫描截断后继续可写会漏算未扫描的合法缓存文件；多个进程各自的map不能共同保证目录硬上限；只catch异常没有RAII回收open对象、已分配输出和SDK blob。已要求原owner用真实有效条目/独立进程/分配失败回归修复，不能只把硬预算改成已扫描前缀的统计。

## G04：标注列表，已进入待集成队列

受测`02ec0587869a8ea036ffc9b3cbd9a780060fed72`，文档HEAD`0527476aed2f099e19bbc7dbeb8271dc662a3636`；两者只差两份证据文档。run`40082509106`三平台消费者、Linux诊断sanitizer和严格汇总五作业均success，root已独立核对；三平台各56项。复审确认同页快照复制、无冲突头伪选择、取消整页丢弃、输出预算与所有权路径。不因此授予宿主界面或移动平台。

本轮所有包收口后才统一合入。集成时G03/G04/G05只需encode/decode的产品依赖应改用已收口的ReadingState codec目标，避免其旧完整ReadingState传递依赖把SDK静态组件带入隔离的移动产品owner；须共同源码安装组合与符号审计复验，不借原单包绿跳过。

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

## G03：阅读命令，自动身份重试复审通过，待集成

DeepSeek接续交付HEAD`207778d8ef0b20f8945a8c8d64c7c3881205e62d`，受测`6ba1ad0d0c3c74dfc5c5267521f60dfd3210a48a`，run`40081701747`四作业成功，root已独立核对作业接口。

root发现新书签/高亮在空`annotation_id`时每次随机生成身份。首次响应丢失后，以相同稳定`revision_id`和相同空身份输入重试，会生成不同实体的wire，造成碰撞而非精确no-op。已要求原接续owner补云端回归和稳定身份根因修复，保留原检查和旧通过记录；暂不交宿主采用。

回修受测`7829ddff129e62d156db445af6c975ebf9166881`，文档HEAD`e1d306e2`仅两份证据文档。root已读实际实现与新增11项回归，并独立核对run`40084536016`三平台和严格工件汇总四作业全部success。实现先以稳定revision ID通过公开`reader_revision_get`恢复同书标注身份，再重建wire交原提交路径；相同输入返回原身份/`created=0`，ack后不重排队，不同payload仍碰撞；写锁失败后可再提交一次。三平台各1413项通过。本包进入待集成队列，不将它的旧完整ReadingState依赖原样接入移动隔离owner。

## G05：标注导出，退回实体快照与路径别名修复

原交付HEAD`14fb43bc6104ef0483b786423550742128589d32`，受测`d7ad100b67dca6d0cd0dae97262e5e1d419fd0b2`，run`40079793192`。

非SAFE实体会在较晚的`heads`快照取得graph和头列表，却继续输出较早page行的selection/tombstone与统计。并发补父、merge或restore可使单实体导出的状态与实际头不一致；应从同一公开快照得出该实体的全部状态。

两个输出路径只用字符串比较判重，`dir/out`与`dir/./out`等别名可以发布到同一个文件。要求发布前拒绝别名，保留原有效输出，并补回调重入的拒绝性回归。原19项与wire精确字节检查不减。

原G07完工会话已以Flash1017 High/PTC/完全权限接管G05原工作树。此回修仍属于第1轮收口，原G07交付不再编辑。

回修`0b79307a41fc5152cf10f7c34e30573d2481aa08`的run`40085969696`三平台和严格汇总均success，root已独立核对。单实体状态改从同一次heads/graph快照导出；root继续发现Windows不存在输出文件时，`GetFullPathNameW`不解析父目录junction，两个父目录别名仍能落在同一最终文件。现有测试只在POSIX建立symlink目录，Windows缺这个场景。已向原owner排队发送补充回修，要求真实junction、初始不存在的同名leaf、发布前拒绝且不创建temp；新绿不代表此缺口通过。

## 主线证据核对

root已通过GitHub作业接口独立核对：iOS run`40080841137`的producer和严格汇总均success；Android run`40081333678`实际模拟器作业success；同源codec run`40081333621`的Windows/Linux作业success。正式SwiftUI/Android账号和阅读界面的接线继续由各主线owner实施，不借测试壳授予产品界面。

GTK受测`27ab57fd725816dd098c7031fa634efde83c63e5`、run`40082557686`、job`120838919065`已由root接口核对success；46项账号/收取、原105项界面与4项故障、原后端同轮通过。文档HEAD`adef2c01a177c120831b27897c5f3a460eafe788`仅两份证据文档。其后GTK/ATK修复候选`532d8ebb97a21a113cb1464b6014827c058e21a9`的run`40084158805`仍待真实回归，不转移上一源码通过结论。

## G01：Windows账号，补齐真实capture出口

原受测`20c6a1deec794b4902f0ae3a7140a17b19cef7fd`、文档HEAD`cd0c7f9b8e3a9af53e30e53248d47ce959f1d0c8`、run`40082869006`保留。root发现旧探针手写v1 location再提交wire，并未调用SDK capture，已要求原owner补安装后四格式18真实捕获、正式A/TLS/B往返与公开resolve、重开，以及冲突/缺父/墓碑不投影的真实UI出口。此前25项只授予其实际传输范围。

G12受测`da2bcde7d684c1db8a9a51de9a7d478d870d5149`、run`40084309431`审计作业success，root已独立核对并读报告：49项为34pass/9fail/5gap/1not_verified，其中8blocking；`audit_completed=true`、`accessibility_accepted=false`。root已将报告交同一Windows生产owner，先完成当前18捕获，再修无名输入框、Tab陷阱、禁用时丢焦点、详情关闭焦点恢复、阅读页真实文字/选择provider、模态背景语义及状态事件。只增G01定向回归；G12报告目录只读，完整审计在集成后复跑。

## 主线后续候选（2026-10-24 10:38 UTC）

- Apple正式账号分支已独立为`codex/reader-apple-host-account`。`8b70b91ac9684124eca505aed54f519b54aea225`的WP13/mapping/shelf三轮均实际失败，原因分别涉及bounded消费者仍导入旧SQLite3头及macOS WebDAV缺curl链接，原失败保留。新同源`9b84f4254a7442a10e91a082796e8c8f1a8d840c`已派完整三套：`40086427673`、`40086438356`、`40086444544`，未授予新候选。
- Android正式UI受测`2db9c240705fbe89579ea1bba5bb6e498f34aff5`：root核对codec`40085974325`的Win/Linux通过；旧18捕获及原宿主run`40085974318`通过。正式UI`40085974320`在instrumentation runner注册处失败，owner保留原suite并修分别构建测试APK，不借旧通过授予账号UI。
- GTK最新`dc1fa2c1fd6a156f0471e66ec9bd29d97e56cfb6`、run`40086097714`继续原46+105+4及定向AT-SPI；先前公共combo焦点仍落入私有button的候选未授予。只真实焦点事件和原生键盘路径通过后登记。

交付HEAD`cd0c7f9b8e3a9af53e30e53248d47ce959f1d0c8`，受测`20c6a1deec794b4902f0ae3a7140a17b19cef7fd`、run`40082869006`自报25项及原基线成功。

root读到`check_account_ui.py`的`capture()`只把Python手写v1 wire交给`revision-consumer reading-local`；location的`exact/start/end`均为常量，没有公开SDK capture调用。原检查证明修订字节传输，不能授予“真实阅读capture往返”。要求保持旧传输断言，补四格式公开SDK真实捕获、v2编码、正式宿主TLS往返和第二SDK定位（优先复用既有18案例），并证明当前阅读/SDK notes不被自动写入。

同轮还须实际触发未覆盖的并发、待父与墓碑状态，验证不选头、不误投影/复活及已有本机书仍离线可读。已交回原DeepSeek接续owner；这不等于否定旧25项各自的实际范围，也不把缺口移到限制里就算本包收口。

## 后续审查队列

- G09清单run`40081161966`记录`release_ready=false`：安装文档、部分归档与pkg-config材料仍有构建机绝对路径。后续分发准备须在冻结SDK约束内解决并复验；清单完成不等于发布就绪。
- G10观测run`40081997953`没有授予性能预算。其保留失败`40079602783`里的16 MiB TXT导入不可见后来改用多章EPUB进行观测；原TXT必须单独复现、区分实际导入/标题查询/等待条件的根因。EPUB观测不能证明原TXT问题已修复，已交回原owner保留原输入并追查。
- G07记录的Windows操作耗时可超过单个WinHTTP超时设置；“1200 ms是整个操作上界”的含义不能从4.02 s观测推出。集成时应准确区分各阶段设置与端到端总耗时。
