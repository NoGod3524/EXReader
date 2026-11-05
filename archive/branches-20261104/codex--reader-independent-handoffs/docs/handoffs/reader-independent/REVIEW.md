# 第1轮接收与审查

本记录不累计完成轮数。下列源码审查发现尚须Actions回归或修复；此前单包绿只证明当时的测试范围。所有包收口并在共同源码复验前，`completed_cycles=0`。

## G02：缩略图，root回修复审通过，待集成

原交付HEAD `1168e2f46b812b683c4376a5a586e04c3bdfafbd`；受测`797774f283f17901161346a0938a0c0e81e4c118`，run`40078420397`。

root审读`apps/reader/thumbnails/src/thumbnails.cpp`与其消费者后发现：

- 初审怀疑`filesystem::rename`在Windows不能覆盖已有索引；后续原源码回归证明此假设在windows-2022未重现，MSVC STL执行了替换，原跨进程LRU身份断言也通过。实际重现的是索引替换失败被吞掉、临时文件安全和重入问题。回修同时保留平台原子替换及写入失败的明确状态。
- 临时文件用可预测名称和截断打开。必须证明预置hardlink/symlink不会覆盖缓存外文件，并使用独占创建、no-follow与原子发布。
- 打开缓存时先保留整个目录路径vector和全部有效entry，再最终淘汰；峰值不受缓存条目上限控制。需逐条有界扫描/淘汰及明确工作上限。
- `rth_cache_stats`未检查busy，与所有入口拒绝回调重入的合同不符；C ABI的分配/文件系统异常边界也须补齐。

旧检查保留，新增独立回归先在Actions证明原缺口。原Claude已结束；DeepSeek Flash1017 High/PTC/完全权限接管原G02工作树回修。未经root复审不进入本轮集成。

第一轮回修`00f3d3713619bef8f41c4f5d97957d37dbb3ed87`、run`40083975196`已通过其原158/159项与9项新增回归，文档HEAD`f1912d45c5a599f575f32d2d6df225c31c28a193`。root二次审查仍未放行：扫描截断后继续可写会漏算未扫描的合法缓存文件；多个进程各自的map不能共同保证目录硬上限；只catch异常没有RAII回收open对象、已分配输出和SDK blob。已要求原owner用真实有效条目/独立进程/分配失败回归修复，不能只把硬预算改成已扫描前缀的统计。

继续读固定`5af48c35`发现回修引入的像素源错误：`finish`把刚分配的输出`raw`传为`resample`的输入，缩小时会按源尺寸读取较小输出；应使用`bmp.pixels`。另外`drop_entry`先从map/total删除，再忽略磁盘删除错误，文件被占用时不能保证目录硬预算。已发送紧急回修：独立非均匀像素参考、真实大图缩小路径、占用有效条目导致淘汰失败，并保留RAII与独占锁。尚无上述两项的新通过结论。

`a03020ae`已实际修正像素实参和删除失败计数；root继续读`b7bc49e3`的故障驱动发现，它把任意`TERMINATE`归为外部noexcept边界，数量不超过12即通过原“返回错误、无泄漏”检查，尚未给精确栈证明。已排队发送第四次复审：逐点子进程保留用于诊断，未分类终止不得通过；先定位生产/stdlib/测试自身，再修具体可分配noexcept调用。活跃cache拥有的合法内存与close后泄漏分开判，C++new计数不冒充C malloc/SDK blob的泄漏证明。此项未处理前不进入待集成队列，旧run继续保留。

root已在外部UI确认G02模型停止，三个后台任务均为已结束的只读GitHub查询；以干净`b7e38e5b`接管异常修复。该源run`40091225844`虽五作业全绿，Linux原始日志实际将open的8次进程终止算为通过。root提交`b99034cd`恢复零终止要求，保留逐点子进程，在真实分配失败点捕获原生栈并经Actions解析；新run`40092109613`待结果。C++new计数只证明其覆盖的分配，Linux独立ASan/UBSan启用LeakSanitizer后复验C资源。旧绿不授予异常合同。

最终受测`430c718b7a92cf8055e5c3775bdcb254e918419b`，纯文档HEAD`46cab809`。root独立核对run`40092824048`三个桌面producer、完整Linux ASan/UBSan/LeakSanitizer及严格四ZIP汇总五作业全success。Linux/macOS各179、Windows178原探针，11回归和3逐点故障；open/store/library注入点Linux31/42/40、Windows17/22/21、macOS13/25/24、sanitized25/38/36，全部零终止。具名非均匀像素、真实锁文件删除失败、目录硬预算、独占owner与崩溃重开、RAII重试及原有断言保持；严格汇总实际下载四ZIP校验source/run/attempt/大小/digest/有效期并比较相同检查集合，`accepted=true, problems=[]`。新HEAD仅两份证据文档差异已核。G02进入待集成队列，宿主UI、移动平台和性能预算不随本包授予。

## G04：标注列表，已进入待集成队列

受测`02ec0587869a8ea036ffc9b3cbd9a780060fed72`，文档HEAD`0527476aed2f099e19bbc7dbeb8271dc662a3636`；两者只差两份证据文档。run`40082509106`三平台消费者、Linux诊断sanitizer和严格汇总五作业均success，root已独立核对；三平台各56项。复审确认同页快照复制、无冲突头伪选择、取消整页丢弃、输出预算与所有权路径。不因此授予宿主界面或移动平台。

本轮所有包收口后才统一合入。集成时G03/G04/G05只需encode/decode的产品依赖应改用已收口的ReadingState codec目标，避免其旧完整ReadingState传递依赖把SDK静态组件带入隔离的移动产品owner；须共同源码安装组合与符号审计复验，不借原单包绿跳过。

## G06：本机下载，两次回修复审通过，待集成

原交付HEAD `4f00f6bf5af9b995486b39a1d3e2ff7d56fbdf39`；受测`7817caa968ce9350ed1c6b3712d31a13c2da8fd8`，run`40079478242`。

root审读`apps/reader/local-downloads/src/local_downloads.c`：

- `reader_ld_reimport`先散列路径并关闭文件，随后SDK重新打开该路径导入，未核对实际导入原件的身份就attach。需要固定输入被替换的回归，保证导入和全局book key的字节身份一致。
- intent只读固定前缀，未验证文件EOF；数字采用宽松转换，未知/重复字段不拒绝。应严格拒绝尾随、嵌入NUL、超限和字段损坏，并保留两库及原intent。
- 固定`intent.tmp`截断写入与目录跟随会绕过私有状态边界；须验证外部sentinel不被截断或清理。
- 明确回调中recover/remove/reimport的重入合同，避免回调推进外层durable状态。
- 原31项覆盖TXT/EPUB/CBZ，未覆盖PDF等格式的移除/重导入与路径寿命；补齐实际格式出口。

这些是源码审查结论，不是已经运行过的失败测试。原交付记录不删除，新候选需三平台同源复验。

G06已由原G14完工后的空闲DeepSeek会话接管原工作树；G14交付保持不动。

第一轮回修`44a6991f65021b58f48165124fd5ae654b14e157`、run`40086428132`交回51项及原源码回归。root二审又发现：`ld_stage_copy`未在复制阶段执行期望长度/格式上限/`max_input_bytes`，会在SDK拒绝前无界写暂存；PDF分支先attach映射再发布保留文件，发布失败返回IO却已改变两库。已实际发送第二次根因回修与公开API故障回归要求；owner在`198aeb2d`/`041a1e1e`继续修，未复审授予。另冻结SDK会把PDF原件存入BLOB，文档不可再以“后续阅读依赖导入路径”为保留文件的理由。

回修受测`49313756e20efb4ea0d8f503deb0727beefd360b`，纯证据HEAD`1f04538dec1595b4af1373915de344766dda284f`。root已读复制硬边界、导入前发布、实际SDK原件复核与失败清理实现，以及真实目录阻挡发布/小输入预算/解除阻挡重试等回归；run`40087396501`三平台和严格汇总四作业已独立核对success。Linux/macOS各54/54；Windows53通过、1项路径替换因系统拒绝替换已打开文件而明确跳过，不冒充实际完成替换。两份文档差异已核。进入待集成队列。

## G03：阅读命令，自动身份重试复审通过，待集成

DeepSeek接续交付HEAD`207778d8ef0b20f8945a8c8d64c7c3881205e62d`，受测`6ba1ad0d0c3c74dfc5c5267521f60dfd3210a48a`，run`40081701747`四作业成功，root已独立核对作业接口。

root发现新书签/高亮在空`annotation_id`时每次随机生成身份。首次响应丢失后，以相同稳定`revision_id`和相同空身份输入重试，会生成不同实体的wire，造成碰撞而非精确no-op。已要求原接续owner补云端回归和稳定身份根因修复，保留原检查和旧通过记录；暂不交宿主采用。

回修受测`7829ddff129e62d156db445af6c975ebf9166881`，文档HEAD`e1d306e2`仅两份证据文档。root已读实际实现与新增11项回归，并独立核对run`40084536016`三平台和严格工件汇总四作业全部success。实现先以稳定revision ID通过公开`reader_revision_get`恢复同书标注身份，再重建wire交原提交路径；相同输入返回原身份/`created=0`，ack后不重排队，不同payload仍碰撞；写锁失败后可再提交一次。三平台各1413项通过。本包进入待集成队列，不将它的旧完整ReadingState依赖原样接入移动隔离owner。

## G05：标注导出，实体快照与路径别名复审通过，待集成

原交付HEAD`14fb43bc6104ef0483b786423550742128589d32`，受测`d7ad100b67dca6d0cd0dae97262e5e1d419fd0b2`，run`40079793192`。

非SAFE实体会在较晚的`heads`快照取得graph和头列表，却继续输出较早page行的selection/tombstone与统计。并发补父、merge或restore可使单实体导出的状态与实际头不一致；应从同一公开快照得出该实体的全部状态。

两个输出路径只用字符串比较判重，`dir/out`与`dir/./out`等别名可以发布到同一个文件。要求发布前拒绝别名，保留原有效输出，并补回调重入的拒绝性回归。原19项与wire精确字节检查不减。

原G07完工会话已以Flash1017 High/PTC/完全权限接管G05原工作树。此回修仍属于第1轮收口，原G07交付不再编辑。

回修`0b79307a41fc5152cf10f7c34e30573d2481aa08`的run`40085969696`三平台和严格汇总均success，root已独立核对。单实体状态改从同一次heads/graph快照导出；root继续发现Windows不存在输出文件时，`GetFullPathNameW`不解析父目录junction，两个父目录别名仍能落在同一最终文件。现有测试只在POSIX建立symlink目录，Windows缺这个场景。已向原owner排队发送补充回修，要求真实junction、初始不存在的同名leaf、发布前拒绝且不创建temp；新绿不代表此缺口通过。

最终回修受测`ad0d2fb3a38f74f5b600bd518e566ed3095a2516`、纯文档HEAD`0f0728b8abfe8245382d40747bc73f657c717b52`；root已读实际父目录handle身份判重与Windows真实junction/不存在leaf回归、同实体窗口回归，核对HEAD仅两份证据文档差异。run`40087054573`三平台各25具名检查及严格汇总四作业全success，已独立核对。进入待集成队列；统一组合时仍要切codec依赖。

## 主线证据核对

root已通过GitHub作业接口独立核对：iOS run`40080841137`的producer和严格汇总均success；Android run`40081333678`实际模拟器作业success；同源codec run`40081333621`的Windows/Linux作业success。正式SwiftUI/Android账号和阅读界面的接线继续由各主线owner实施，不借测试壳授予产品界面。

GTK受测`27ab57fd725816dd098c7031fa634efde83c63e5`、run`40082557686`、job`120838919065`已由root接口核对success；46项账号/收取、原105项界面与4项故障、原后端同轮通过。文档HEAD`adef2c01a177c120831b27897c5f3a460eafe788`仅两份证据文档。其后GTK/ATK修复候选`532d8ebb97a21a113cb1464b6014827c058e21a9`的run`40084158805`仍待真实回归，不转移上一源码通过结论。

## G01：Windows账号，真实capture回修通过，宿主无障碍接续

原受测`20c6a1deec794b4902f0ae3a7140a17b19cef7fd`、文档HEAD`cd0c7f9b8e3a9af53e30e53248d47ce959f1d0c8`、run`40082869006`保留。root发现旧探针手写v1 location再提交wire，并未调用SDK capture，已要求原owner补安装后四格式18真实捕获、正式A/TLS/B往返与公开resolve、重开，以及冲突/缺父/墓碑不投影的真实UI出口。此前25项只授予其实际传输范围。

G12受测`da2bcde7d684c1db8a9a51de9a7d478d870d5149`、run`40084309431`审计作业success，root已独立核对并读报告：49项为34pass/9fail/5gap/1not_verified，其中8blocking；`audit_completed=true`、`accessibility_accepted=false`。root已将报告交同一Windows生产owner，先完成当前18捕获，再修无名输入框、Tab陷阱、禁用时丢焦点、详情关闭焦点恢复、阅读页真实文字/选择provider、模态背景语义及状态事件。只增G01定向回归；G12报告目录只读，完整审计在集成后复跑。

回修受测`dde92e8990ec14888b2f500d6000db596f03c601`、纯文档HEAD`be197da252683eae031a5660f294be94fa0209a7`的run`40089084258` producer/严格汇总两作业已由root独立核对success。root已读原生capture/resolve消费者及实际宿主驱动：18捕获调用公开SDK创建，两个真实宿主经原生TLS传输并重开，17FOUND/1预期歧义、零SDK笔记副本；新旧共32项及原158/10/5/13/18回归保留。冲突/缺父/墓碑在接收端独立产品库种入，真实UI证明不投影、不选头、页面不跳、本机冲突原件仍可离线读取；这不冒称第二远端产生了冲突分支。两文档净差异已核。该固定账号/capture交付进入待集成队列，owner随后G12生产修复仍未验收，不把新脏文件转授。

## 主线后续候选（2026-10-24 10:38 UTC）

- Apple正式账号分支已独立为`codex/reader-apple-host-account`。`8b70b91ac9684124eca505aed54f519b54aea225`的WP13/mapping/shelf三轮均实际失败，原因分别涉及bounded消费者仍导入旧SQLite3头及macOS WebDAV缺curl链接，原失败保留。新同源`9b84f4254a7442a10e91a082796e8c8f1a8d840c`已派完整三套：`40086427673`、`40086438356`、`40086444544`，未授予新候选。
- Android正式UI受测`2db9c240705fbe89579ea1bba5bb6e498f34aff5`：root核对codec`40085974325`的Win/Linux通过；旧18捕获及原宿主run`40085974318`通过。正式UI`40085974320`在instrumentation runner注册处失败，owner保留原suite并修分别构建测试APK，不借旧通过授予账号UI。
- GTK最新`dc1fa2c1fd6a156f0471e66ec9bd29d97e56cfb6`、run`40086097714`继续原46+105+4及定向AT-SPI；先前公共combo焦点仍落入私有button的候选未授予。只真实焦点事件和原生键盘路径通过后登记。

10:49 UTC后续：Android最新正式候选`170d1f77d6e320c75fca25b047dbf117bd1d0c5f`，原完整回归`40086660638`及Win/Linux codec`40086660644`通过，正式`40086660647`在新语义阶段失败，owner继续Actions诊断。GTK的`dc1`原46+105+4与定向9项实际通过；Actions只读诊断`40087119792`确认状态名称事件已发，筛选应读AT-SPI的event.type而非detail1。owner在自有测试修正事件类型并核同一source对象，完整新候选`ddaded9b81c2e51de4313919242f883246dd4426`/`40087214516`待验；旧G13报告留存，最终完整审计需同源重跑。

G16落盘的`a8756cd196a18a050acb47967948b631df4313f7`/`40083042946`报告仍是`accessibility_accepted=false`；其iPhone大字体横屏返回/选文/笔记越界、返回/取消触控区、正文仅60字等明确问题已交Apple生产owner只读核实并修复。新审计`29f03e23`/`40085956514`还在汇总，报告源不得混用。Apple已确认先收当前回归，再补独占HostViews/HostModel的生产修复和定向XCUI，G16测试目录保持只读。

## 11:04 UTC 接收补记

GTK受测`ddaded9b81c2e51de4313919242f883246dd4426`、纯文档HEAD`8a7cab996f7b3a876254f16a90dab69bbeb9f15a`已收口，root核对`40087214516`实际消费者作业success且两份文档差异成立。46账号/收取+105界面+4故障+定向AT-SPI10及原后端全部通过。工件`12557658114`，40,134,196B，SHA-256`abedea8e4ba9037986bef4189cfe786901b36742f3b75711e606f2c94f593363`。完整G13审计和Orca仍待后续；生产owner从该固定HEAD新建`codex/reader-gtk-settings`继续正式设置接入，不改写已验收提交。

G10性能观测第二候选`55d066772baa37c02773eacbcbace5c73acc7839`/`40086319655`已独立核对success，文档HEAD`4d824967`。原16MiB TXT及7MiB变体经实际宿主与安装SDK诊断为`EXR_LIMIT`，无遗留SDK行、目录不变；原输入身份和失败保留。EPUB观测不替代TXT导入授予，原SDK冻结预算不改。G11受测`553d1a5e2aa27b8625930900f592d78d11e2378e`/`40086971620`的采样/工件核验两作业也已独立核对success，文档HEAD`ae504e50`；32次启动、520原始样本保留，注入前事件不得算入响应。两包均只交观测，不授予产品性能达标。

G16新报告`29f03e233ee5e6c668d737f8236974648ce4333c`/`40085956514`三目标及汇总已success，root已读源码差异：用path含`ScrollView`就跳过任意重叠对，实际连同容器可见区内的重叠也跳过，与其“同容器仍比较”的合同不符。已实际发送回修，要求依据可证明的viewport裁剪区分，不能证明就记uncovered，同容器重叠仍测，并补判定器正反例；真实生产问题仍由Apple owner修。报告原本`accessibility_accepted=false`不改变。

G02紧急消息最初滞留外部应用队列，root已为优先处理确认的像素源错误停止模型的例行轮询（未取消云端run），并以新的继续消息把完整回修要求送入当前会话；没有重置代码或重启同一云端运行。

## G08：基线模块组成，源码复核与集成要求

root已读其安装工作流、独立消费者CMake、prefix扫描和负例：固定起点已存在的13包确实按同一前缀安装，消费者复制到新目录，只用安装头/targets，移动前缀后重新编译运行；默认SDK快照与模块组合分开。其原`4b1a17ca24eab43a765a3e984a707061d012083a`/`40081552526`只覆盖固定基线，不覆盖本轮新G02–G06或codec拆分；统一集成须扩入实际新目标再同源复验。G09记录的SDK文档/归档/pkg-config内路径不等同于G08的已导出CMake接口泄漏，两种扫描范围分别处理。

## G09：分发清单，SDK部分已交，应用模块范围待补齐

原受测`f3b5c8f65d6a1d7db51364b897f81a995ce37c67`、文档HEAD`4e140fec7b3d47ce624cecc6d239dc94833559a2`、run`40081161966`的六SDK材料保留。root对照原交接发现范围缺项：任务要求“SDK和应用可选模块”，工作流及inventory实际只有六reading SDK profile，排除了应用可选模块，不能以更小的SCOPE算整个G09完成。

已实际向原G09 DeepSeek会话发送接续：保留六SDK及原负例，在固定起点已有13包上补Windows/Linux/macOS真实组合安装清单、SBOM、版本/头/归档/config散列、许可原文及实际静态/动态依赖材料，明确系统依赖和随包库。复用G08安装方法，不依赖移动G01–G06；reading默认无可选模块的断言保持，组合profile单独显式启用。新增漏模块/依赖/notice等拒绝项，最终同源完整复验后交回。原96处安装路径命中仍登记、`release_ready=false`，不为补报告改冻结SDK/发布流程或创建tag。

root先修不触及冻结树的两份分发文档：`CONVERSION.md`与`WP7-SCRIPTS.md`的本机绝对示例路径改为`build/wp12-lite-corpus`与`build/wp7`。当前只是源码文档修正，旧工件不变；实际安装材料是否消除这两处命中须在共同源码重新生成清单后验证，归档/pkg-config路径仍待分发层处理。

交付HEAD`cd0c7f9b8e3a9af53e30e53248d47ce959f1d0c8`，受测`20c6a1deec794b4902f0ae3a7140a17b19cef7fd`、run`40082869006`自报25项及原基线成功。

root读到`check_account_ui.py`的`capture()`只把Python手写v1 wire交给`revision-consumer reading-local`；location的`exact/start/end`均为常量，没有公开SDK capture调用。原检查证明修订字节传输，不能授予“真实阅读capture往返”。要求保持旧传输断言，补四格式公开SDK真实捕获、v2编码、正式宿主TLS往返和第二SDK定位（优先复用既有18案例），并证明当前阅读/SDK notes不被自动写入。

同轮还须实际触发未覆盖的并发、待父与墓碑状态，验证不选头、不误投影/复活及已有本机书仍离线可读。已交回原DeepSeek接续owner；这不等于否定旧25项各自的实际范围，也不把缺口移到限制里就算本包收口。

## 12:13 UTC 主线与root回修补记

- Android正式UI固定受测`ed9ff5ffc3608971bb19020f1ec07496a79d9710`的正式`40090470041`、原宿主`40090470061`和codec`40090470091`已由root独立核对通过。正式16项保留原18捕获及原宿主/DAV回归；真实页0→1、偏移0→415、字号24→28、系统字号2及原始树/图像留存。交付HEAD`27b8dadd`还含后来未验收的workflow变化，不能称为纯文档HEAD；集成选择受测ed9。owner从ed9新建搜索UI分支，复用同一共享SDK与worker，不引入第二静态SDK。
- GTK设置`893b76e9`/`40091207927`已取得实际字号/行距/段距/页边距导致分页范围改变和安装F3回读值的证据；原生页请求背景色没有命中像素、margin仍白，属于真实未完成。冻结API没有重排整页背景参数，先保留白纸可读与面板主题的准确范围，不用白色替换或反色伪装整页主题。剩余设置与原回归仍在跑。
- Apple `62aee485`原WP13三目标各13用例/67步骤与mapping三目标UI均有原owner交回成功；新增shelf容量探针失败保留。后续远端固定`d154e326`三套继续；真实HTTPS/后台显式重试及G16生产缺陷修复在owner下一候选，未混作已验收证据。
- G02原生枚举回修`7afa5982`在Linux实际完成30个open分配点、41个store、39个library分配点，均零终止；原179项也通过。该轮作业最终失败在root新增的诊断命令读取已被成功清理的scratch目录，随后`8d845f71`只在目录存在时执行诊断。该源完整Linux ASan/UBSan/LeakSanitizer已执行原探针、回归及逐点故障通过；最终`430c718b`再补第一分配点并拒绝NOFAIL但非零退出的子进程，run`40092824048`待完整三平台及严格工件汇总。
- G01新Windows provider尚未授予。root读固定`9955c472`发现range自身无refcount且Release直接free、页面各iface的IUnknown身份不一致、旧range读全局新frame、UTF16/任意TextUnit及几何响应不实。完整回修要求已排队交原owner；须真实COM生命周期/跨页/Unicode/实际UI回归和root复审，不以编译或一次GetText通过代替。

## 后续审查队列

### 独立包最终复核与 Windows 继续回修

### 后续固定交回与手动分包

- 共同候选 `bb8e0b864ac5bd709d0d6f4c5de858ea33f020e6` 已推 `codex/reader-g1-integration`，G01–G16普通merge保留历史。集成修改固定 `ba25961961ae69222bfed4f7a98cb02bb1dc6847`：仅取既有codec拆分，G03/G04/G05改用codec-only，实际SDK探针显式声明依赖。run `40116411109` 的Windows宿主及三桌面组合四个producer已确认在跑；新出口含原G08、G02–G06原判定器、五模块真实链路、重定位和无SDK运行符号的产品codec消费者。尚未授予共同候选，也未累计完成轮次；GTK/Android/Apple后续宿主仍需固定输入与同源复验。
- Apple最终交回 `a1a41b08a3661bb01170e37031913649b2b296db` 相对 `695ee448043e1f041b8d43cb94d8a2bf62433441` 仅两份证据文档，root已核Git差异；695相对281仅映射探针与记录。root独立读 `40109106732` strict job `120933040950` 原日志确认 `accepted=true`，三目标原书架/2202语料与账户/production语义接受；summary工件 `12567632527`、2737B、sha256 `c4178b1787a59fe7c5bb6bd85920735c3702b8d427cddb4fddf95244d939a336`。WP13/shelf在281源码，映射在695源码分别保留，不拼成同一SHA通过。原owner接续Apple搜索UI。
- Android导航最终交回 `b5d312d0b20a77fc7630cd464f9e12325438b91c` 相对受测 `d68d8e388730f0fbd9e86c70a422388be406391d` 仅两份证据文档，root已核Git差异。run `40115551503`/job `120935966789` success，root读原日志确认导航18/18、搜索15/15、正式16和旧套同源通过。工件 `12568127459`、129689309B、sha256 `a964ab12f94d2f6693d4aef35bf1bf55693cc6c37636ff418f42365910cc7214` 与上传一致。投影与目标边界只在可证明时导航；CFI拒绝路径、旋转/取消/重开真实执行。owner接续Android产品书签/标注面板，仍不授TalkBack/真机/性能。
- G01最终完整run `40113587443` attempt1：producer `120930166046`、严格汇总 `120931870728` 均success。root独立核原始日志，`accepted=true, problems=[]`；原UI158/product10/worker5/shelf13/metadata18/account32及定向键盘/UIA24全部通过，含TXT/PDF/有界EPUB实际几何与点定位。受测源码 `c74e861b7dbe95e680b53f18bc63a764ae06fc4f`，最终HEAD `8995ffbf421cf070e29c58f50f49d0a682fdca92` 已推远端，差异仅两份证据文档。producer工件 `12568060427`、44146885B、sha256 `3f7796b0f53126b3330996bafb99fb06c98e368134648108274be59acbbd7320`；summary `12567920905`、796B、sha256 `bf94a614819368a95c0fb4a7c7e46cd6c0f9b9bdb8fe1a3badf2a8f809807a60`，到期均2027-01-22T16:52:55Z。严格作业实际下载并重散列producer ZIP；root核元数据及上传日志，不在本地下载工件。该scope进入待集成；完整读屏、性能和六平台产品未授予。下列旧pending/失败记录保留为迭代历史。
- 按用户“每交回即准备”修订协调流程：本次Windows交回后重核已有25个J包，仍可独立投放；不为增加包数重复分配已有需求。任务页实现起点与独占路径不改，派发由用户手动执行；主线三个owner继续Android导航、GTK搜索和Apple现存验收。
- 用户改为单包交回即可继续准备任务，root已推 `34ef34ada254519db8c76f62a4b2dadf46775e73` 的25个J包完整说明、共同约束及文件归属。实现均固定f43，不依赖未合入G包或主线活动文件；用户手动分发，root未派发。五轮审计与完成轮数不因文档准备增加。
- Android搜索固定 `e764f08dea4986f11db183c5b17b41ddb5526bcc`，纯文档HEAD `6bbc49bffd2de66b562a6afc1b7e6a8b91ffa8fa`。root独立核 run `40111800432` attempt2/job `120925154490` success，原正式16和搜索15的同源码日志、工件 `12567530810`/118919384B/sha256 `188846a51dfc4b9ce2446a53fa0e5fb3fcc863b6393a0c454bb6e924bc1693fe` 与上传一致，Git差异仅两份文档。旧attempt1镜像下载失败日志留存、小ZIP目前404，不再宣称工件仍保留。owner已从固定e764另开原生目录UI，F2仅引入cbd7832b的不可变模块子树；不授予新导航UI。
- GTK设置固定 `ce912f8c149e30cf3843e39258ae6889235495a0`，纯文档HEAD `8a5e8a68c627196116e80ea456f12165a4e3209c`。root核 run `40110581923` 实际日志：安装F3 20、原46/105/4/AT-SPI10同源通过；设置35全执行，33通过、整页背景及Dark阅读页2项仍失败。`accepted=false`，不能当整个设置包通过。owner转GTK搜索，35项原失败保留；本轮工件未做最终ZIP重散列，亦不扩大证据范围。
- Windows `6c8d6462`/`40110638065` 实测已通过文本移动/端点/Unicode；无效枚举客户端返回E_UNEXPECTED而非server的E_INVALIDARG。公开客户端只承诺失败HRESULT；探针保留拒绝和端点不变并记录实际码，producer防御代码未改。后续 `fcf0d4be`/`40111567097` 停在原13项书架helper跨LB消息读取部分行；未走到新UIA，不继承其通过。root给两条真实列表替换路径加只读前后序号，专用wrapper仅在序号变化时重观察，稳定坏行仍失败；原13断言、2202规模、320轮滚动及worker时限不变。当前 `c74e861b7dbe95e680b53f18bc63a764ae06fc4f` 完整run `40113587443` 待结果。root只取消自己已被替代的 `40111464529` 和 `40113516107`，所有已失败运行未动。

G01 追加实际回修：`d1324959`/`40109071435` 已证明 import/refresh 禁用后的焦点续接、状态事件、原生正文/选区及模态背景禁用均通过；下一处拒绝是取消详情后焦点未返回。root 源码核对发现 `WM_DESTROY` 对无修改的取消也安排刷新，立即再次禁用详情按钮。`809033d7` 删除该多余刷新，保存/放弃修改的完成路径保留各自刷新。`35b677340710cebe41043601a6052f1b2d5d76f3` 另将这一个焦点失败记录为严格失败后继续独立文本组，最终报告和进程仍拒绝，21 项及原预算不变；完整 run `40109829474` 在跑。未授予 provider 全部通过；当前探针仍以 TXT 为主，PDF/有界 EPUB 的点定位和区域证据须另外补齐后才能扩大范围。

`40109829474` 后续终态保留 failure：详情取消焦点、COM clone/release 与跨页快照全部实际通过；失败是固定 `uiautomation==2.0.29` 的 `CompareEndpoints` 包装漏解包目标，`QueryInterface` 参数错误发生于产品调用之前。root 核对包装源码后改为同一公开 `IUIAutomationTextRange.CompareEndpoints` 的直接 COM 调用，原比较断言不变。另对照微软 `ITextProvider.RangeFromPoint` 要求（坐标外仍返回最近退化文字范围），修复原 mouse helper 会拒绝页面外及有界 EPUB 的问题：只用当前 SDK 渲染帧的 glyph clusters/固定页 quads 计算最近插入边，不重开/重解析或访问 worker pager。新增页面外、真实 PDF、有界 EPUB 的几何/点定位/选择与旧书范围拒绝检查，严格出口从21增加至24项。受测候选 `6c8d6462329b8345e53d115670059c0e747b1973` 的完整 run `40110638065` 已启动，结果待定；三格式或读屏均未提前授予。

- G09 固定受测 `93d2ad0db2d75af50eddc0843a4da9c7090a15aa`，纯文档 HEAD `b7bdd62d02a6c85ab57ab7bc36b8b8212dfe090b`。root 独立核 run `40095313750` 的 11/11 作业及严格汇总原始日志：六 SDK 安装及 Windows/Linux/macOS 三组合 prefix 均有材料；每个组合含原交接的 13 包，88 项通过、另两项报告/阻断状态，`accepted=true`、`materials_complete=true`，仍 `release_ready=false`。实际 consumer 是空 main，真实链接行证明安装后的依赖接口，归档符号证明提供/引用关系；这些不能表述成每个库成员均被最终可执行文件抽取或包行为通过。九份安装共有 60 个不同路径命中文件仍待发布准备处理；原失败与原 SDK-only 交付保留。
- G16 固定受测 `16a0b2b5426fbf474601169ba1bcecca848fb231`，纯文档 HEAD `c2e172d1da9352bee9e0b49003ca25f7e35aa829`。root 读新版判定器及 22 项回归：同级完全包含、20%/64%/80% 面积、跨容器包含均按可见重叠判定，仅有记录的语义祖先例外；未知滚动视口仍为未覆盖。run `40096206815` 八作业均成功。交回的是三目标审计材料与判定器，`accessibility_accepted=false`；真实阻断仍交 Apple 生产 owner 修复，不能用审计绿代替无障碍验收。
- G01 root 候选 `143368103c3bec786d1d932dfcf625fde8910efb` 的完整 run `40095466821` 保留失败：原 158/10/5/13/18 及账户/capture 全部执行通过，新增键盘/UIA 在 import 禁用自身后真实焦点为空处拒绝，尚未执行到新文本范围组。根因是原 focus guard 在 `EnableWindow` 已清空焦点后直接返回。候选 `d13249598b4863a2a3eaded56eb199d26e60869e` 改为 native `GetNextDlgTabItem` 并保护已有有效焦点/模态 owner，完整 run `40109071435` 已启动。21 项尚未授予，冻结 SDK/原断言保持。


root以干净`211a3bf320717c78f6b1565399212031d663db01`接管G01未验收的Windows provider收口：外部模型已在UI确认停止，两条后台仅为只读`gh run view`，无源文件writer。保留账户/capture已验收`dde92e89`、原失败`40094080436`和全部现有提交；root不将已知错误TextUnit/几何响应授予，也不让排队旧复审再次启动生产写入。原新UI回归的首次失败发生于Shift+Tab回到原note编辑器后，需按正确正反焦点路径核实其预期，而非避开该控件。

G07根目录干净交付`e54c3ea9`由root追加纯文档修正`50f158d2`：传输设置1200/1500 ms与Windows端到端4.02 s分别陈述，既有下载<45 s、发布<30 s防挂起断言不变；不再宣称设置值为整个操作的严格上界。验证JSON保留原producer的预期字符串、原始结果及身份，另加解释字段，未运行新测试或改变受测源码。

G01固定`40112f49`已补真实range refs与页面快照。root对照微软官方Move/MoveEndpointByUnit/ExpandToEnclosingUnit文档发现第二层缺口：非空Move无条件折叠、cross endpoint夹回旧端点、不支持合法unit未向更大unit回退、Expand(Character)不展开空范围，且新probe断言复制了错误语义。跨行选择还只返回一个union矩形。已整理具体ASCII位置和跨行/Unicode反例交原owner；不能只以本轮新增测试通过授予。

G16二审固定`59a21fd1`：新的`nested_child`以面积比<=0.9猜测父子，与语义路径无关；同级100×100与其坐标内80×80按钮会被三处分支当非遮挡，虽然较小按钮可见面积100%重叠。已交原owner收窄到有依据的真实祖先/同元素例外，补同级完全包含、跨滚动容器包含、真正父子及未知视口反例，50%阈值不改。当前`40090892898`三目标producer与judge全success、summary仍排队；不以该绿覆盖新盲区，不授予可访问性。

12:17 UTC：root只停止自己接手后已被`430c718b`替代的三轮重复G02运行`40092373580`、`40092639342`、`40092723573`，释放macOS队列；失败原始日志/工件保留，诊断失败`40092109613`与旧交付`40091225844`不动，当前最终`40092824048`不取消。其Windows/Linux及完整sanitizer已success：故障点分别为Windows17/22/21、Linux31/42/40、sanitizer25/38/36，均零终止；macOS尚排队。

G01复审消息最初滞留UI队列，root已只停止模型的例行GitHub轮询并以新用户可见消息交回全部具体要求；云端`40092915376`保留。原owner已恢复并实际修改其独占provider文件，root未接管G01生产写入。

- G09清单run`40081161966`记录`release_ready=false`：安装文档、部分归档与pkg-config材料仍有构建机绝对路径。后续分发准备须在冻结SDK约束内解决并复验；清单完成不等于发布就绪。
- G10观测run`40081997953`没有授予性能预算。其保留失败`40079602783`里的16 MiB TXT导入不可见后来改用多章EPUB进行观测；原TXT必须单独复现、区分实际导入/标题查询/等待条件的根因。EPUB观测不能证明原TXT问题已修复，已交回原owner保留原输入并追查。
- G07记录的Windows操作耗时可超过单个WinHTTP超时设置；“1200 ms是整个操作上界”的含义不能从4.02 s观测推出。集成时应准确区分各阶段设置与端到端总耗时。
