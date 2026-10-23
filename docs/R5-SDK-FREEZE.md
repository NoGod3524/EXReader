# R5 SDK 冻结跟踪

当前R2/R4修复集成正在准备下一次冻结；下表K及H8–H11结果仍仅属于各自固定源码，
不自动覆盖新图片/PDF缓存、CMap、anchor和R6原生工作流接线变化。接续见[R6集成记录](R6-READING-RELEASE.md)。

状态：**SDK 已重新冻结**。固定源码 **`9c69bc4c7efb0cff68ced27562709fe597189041`**，
SDK 3.40.0 / library 3.34.0 / ABI 1 / schema 7。
Apple 接续发现的16KiB窗口同单元递归已修复；原`ce5d664`冻结撤回与所有失败记录保留。
**H8–H11四宿主共同验收已通过**：固定源码
`e25959e1285b5ebf9a4bf5b27c596d12702dc695`，四组11作业与11份必需工件均同源、attempt1。
首轮Android重启帧/iPad首次导入失败、第二轮iPhone首次导入失败均保留，详见下文。

## 当前冻结证据

六组全部绑定上述完整SHA、attempt 1；18个执行作业成功，30份工件同源、非空、未过期，
Actions提供的SHA-256 digest字段有效。许可证另有一个按条件跳过的诊断作业，不计入18个。

| 组 | run | 执行作业 | 工件 | 同次完成结论 |
| --- | --- | ---: | ---: | --- |
| SDK source / sanitizer | [39871864812](https://github.com/NoGod3524/EXReader/actions/runs/39871864812) | 2/2 | 2 | 普通与ASan/UBSan各native6/6、安装消费者5/5；36拒绝回归及长章严格汇总通过 |
| 完整 native | [39871859101](https://github.com/NoGod3524/EXReader/actions/runs/39871859101) | 7/7 | 19 | 三桌面各168项ctest，ASan/UBSan165项；安装/裁剪/绑定、Android arm64、Apple库和iPhone/iPad各21自检通过 |
| Linux reading presets | [39871870185](https://github.com/NoGod3524/EXReader/actions/runs/39871870185) | 2/2 | 2 | core3/3、library5/5安装消费者；各9格式、构建组成与初始测量接受 |
| Windows/macOS presets | [39871874132](https://github.com/NoGod3524/EXReader/actions/runs/39871874132) | 4/4 | 4 | core5程序/library8程序全部真实执行；各9格式和25/30拒绝回归通过 |
| 严格许可材料 | [39871878859](https://github.com/NoGod3524/EXReader/actions/runs/39871878859) | 2/2 | 2 | 两preset材料检查与release_ready通过，无pending或必需缺项；既有拒绝/正控全过 |
| PDF/CBZ合成测量 | [39871882988](https://github.com/NoGod3524/EXReader/actions/runs/39871882988) | 1/1 | 1 | 固定合成页、像素/随机跳页与证据拒绝回归通过 |

新增单元回归在Linux/macOS/Windows分别0.06/0.07/0.08秒，ASan/UBSan0.38秒；
固定16KiB窗口、直接text与嵌套inline、重复引文歧义、流式全文查询、首页等价及真实低预算拒绝均通过。
长章六负载仍各3进程、64页/16随机，实际淘汰/恢复与持久化通过；
10→100MiB索引加解析工作区峰值增量仍为20,269,300B，未扩大为RSS或绝对延迟承诺。

## 单元递归修复

云端诊断 [39869850934](https://github.com/NoGod3524/EXReader/actions/runs/39869850934)确认，
原Repeated夹具已完成导入、publication打开与pager创建，随后首次anchor capture耗尽180秒。
对照 [39870093796](https://github.com/NoGod3524/EXReader/actions/runs/39870093796) 的16KiB分支重复超时，
64KiB诊断分支完成同一歧义负例。该对照只定位问题，正式宿主保留16KiB窗口。

修复`src/chapter_reader.c`：仅在可见child对应不同unit root时继续下降，
同root的text/inline child直接按完整真实单元加载；实际工作区不足仍返回`EXR_LIMIT`。
`native-chapter-oversized-unit`覆盖16KiB单段、32KiB嵌套inline、重复引文歧义、
全文流式查询与首页面等价，并检查2MiB单元在1MiB工作区下拒绝。
该回归独立设置60秒超时，防止递归回归耗尽整轮预算；已在上述固定源码通过。
首候选`2f268476`的native运行[39871355982](https://github.com/NoGod3524/EXReader/actions/runs/39871355982)
保留为失败：两种正常单元查询/歧义/页面检查已通过，新增低预算反例误要求lazy pager构造时立刻拒绝。
实际单元在首次查询时加载；回归改为在`exr_pager_anchor_create`触发加载并要求`EXR_LIMIT`且输出为空。
该修正不改SDK实现或预算。

## 原源码冻结证据（历史保留）

下列六组全部为同一 `ce5d664…`、attempt 1；18 个执行作业成功。
许可证工作流另有一个按条件跳过的 `material-pins` 诊断作业，不计入这 18 个。
GitHub 连接逐项读取 jobs、完成日志和每页100项的工件元数据；30份工件全部同源、非空、未过期、digest有效。

| 组 | run | 执行作业 | 工件 | 同次完成结论 |
| --- | --- | ---: | ---: | --- |
| SDK source / sanitizer | [39865824641](https://github.com/NoGod3524/EXReader/actions/runs/39865824641) | 2/2 | 2 | 普通和ASan/UBSan各 native 6/6、安装消费者5/5；36项测量拒绝检查；长章严格接受 |
| 完整 native | [39865828087](https://github.com/NoGod3524/EXReader/actions/runs/39865828087) | 7/7 | 19 | 三桌面各167项ctest；sanitizer164项；安装/裁剪/绑定；Android arm64；Apple设备/模拟器库及iPhone/iPad各21项原宿主检查 |
| Linux reading presets | [39865833043](https://github.com/NoGod3524/EXReader/actions/runs/39865833043) | 2/2 | 2 | core 3/3、library 5/5消费者；各9格式smoke、构建组成和初始合成测量接受 |
| Windows/macOS presets | [39864534400](https://github.com/NoGod3524/EXReader/actions/runs/39864534400) | 4/4 | 4 | core必需5程序/library必需8程序均真实执行；各9格式；25/30项门禁回归全过 |
| 严格许可材料 | [39864537874](https://github.com/NoGod3524/EXReader/actions/runs/39864537874) | 2/2 | 2 | 两preset均`release_ready=true`；failures/pending/mandatory_missing为空；31反例、1缺口阻断、3正控 |
| PDF/CBZ合成测量 | [39864540878](https://github.com/NoGod3524/EXReader/actions/runs/39864540878) | 1/1 | 1 | 固定独立合成页、像素/随机跳页与证据拒绝回归通过；范围见R3测量文档 |

长章包含10/50/100MiB单章与分章六个合成工作负载，各3次独立进程、64页/16次随机请求。
同次严格汇总确认所有工作负载、窗口淘汰后的随机恢复、重复页面hash和持久化闭环通过。
每次随机阶段实际淘汰11次、恢复检查点7次；10→100MiB的索引加解析工作区峰值增量20,269,300B，
低于既有32MiB门槛。该工作区计量与进程RSS分列；不授予任意真实文档或绝对延迟预算。

## 固定源码树

宿主必须保留当前K=`9c69bc4…`祖先关系与以下八项Git对象一致，不能只比较SDK版本字符串。

| 路径 | K中的Git对象 |
| --- | --- |
| `src` | `3cda521444a7e40aa85d907bb1f88c8b09e2907b` |
| `include` | `86fb444dbf1664771d997daeff772bb465d617a7` |
| `cmake` | `ec5eb002674d867228ea033d466973c42b69571f` |
| `CMakeLists.txt` | `b9631e34728e5aaf6924345f7f64acbe1b18f1c6` |
| `tests/fixtures` | `2a1fd5e58347f6ed8692996ba855c703f3c2da46` |
| `.github/workflows/native.yml` | `be39352acf9313ab596030efa6ecea9d5a4a4540` |
| `.github/workflows/reliability.yml` | `a27c1d1ca5a7aae1d590ceed356fdd5cd81abdb9` |
| `bindings` | `54c12f70a1a63cae6574984a388b66bf6248c38e` |

## 源码与验证记录

| 源码 | 云端运行 | 当前授予范围 |
| --- | --- | --- |
| `a0c35f5f01ff88244470ef395886410b78293693` | source `39857282570` 两作业成功；native `39857283787` 七作业成功 | 原件随机读第一阶段，不含有界导入/章内存储 |
| `b68776345ebc7956991d5d056a59828e1b305d78` | source `39859278474`、native `39859304551` | 首轮编译失败保留；两处 guarded output 同行触发 `-Werror=misleading-indentation`，未授予通过 |
| `f3dabe04e37e773ccbf20d6595421a890f3feff2` | source `39859742229` | 新增长章测量；继承上述待修编译问题，不能授予通过 |
| `2bece1b7a04b6ceb4542711f4a6c85f202e6fd0d` | source `39859836493`、native `39859836728` | native 七作业成功；未授予该候选长章整体通过，后续修复章首点的全章扫描 |
| `96c4f2c035a737ccf3f5be890d127d6efdd946f8` | source `39861407735`、native `39861408078` | 修复CBZ原件游标在metadata/progress更新后失效；该候选不作为最终冻结出口 |
| `352bb2d5f4007c62cd821da24b053d20abcd060d` | source `39863165651`、native `39863164990` | 边界点锚点快路；重复路径回归夹具误用公开构造器，后续修正，不能授予通过 |
| `fd210224a4eba206762c08de435a5e9edfdf2a90` | source `39863218905`、native `39863217247` | 修正重复路径夹具；macOS揭示测试缺公开formats头；16页测量未实际淘汰窗口，严格汇总拒绝 |
| `26f04e020de90cf9c25b3208f691d763dc7a66e8` | source `39863607846`、native `39863607111` | 补齐公开头；保留16页计划未满足淘汰/恢复条件的失败 |
| `4d753e4f5937b84fd2e803a943eafc9549edd50f` | source `39863850831` | 增加逐条件云端日志，确认淘汰与检查点恢复都为0；未降低门槛 |
| `6f0d7592ea431394d175d221b04b054facf4a26c` | source `39864227780` | 64页/16随机/3进程计划严格通过；后续整合许可材料安装规则后固定ce5 |
| `ce5d664c9f76d0613df6d79b27568a7039c4a81e` | 上表六组 | 原冻结源码；后被单元递归失败撤回，原通过记录保留 |
| `2f26847684b54006ca812c35477ceae43719e7d4` | native `39871355982` | 同单元递归修复；新增预算反例在lazy创建阶段误期待拒绝，保留失败 |
| `9c69bc4c7efb0cff68ced27562709fe597189041` | 当前冻结证据六组 | 修正预算反例的实际触发点；18执行作业/30工件同源全过，正式重新冻结 |

源码变更以完整 SHA 识别；不能将第一阶段通过项拼入后续源码的整体验收。
后续纯文档提交不改变受测实现身份。

长章观察到章首点恢复仍扫描整章。当前候选仅在空引文、单侧上下文为空且边界已得满分时
跳过该 scope 的其余扫描；外层重复章节仍全部比较。回归覆盖虚拟 100 MiB 源的读取次数、
取消和重复路径歧义。这不解决任意章中位置的扫描，也不授予整体性能预算。

## 固定契约

- 原件 `exr_library_source` 保留内部 owner 引用，不复制整本到堆；删除旧书永久作废旧 source。
  其他连接任意提交保守地使 source 失效，宿主必须重新开 reader。
- schema 7 在原升级事务内一次创建 bounded marker、章内 progress 和独立 notes 三表。
  旧 schema 1–6 升级不扫描正文，不转换旧全书坐标，旧 SDK 明确拒绝新 schema。
- source/file EPUB 导入只读取 ZIP/package 元数据，分块保存原件。原 ZIP 上限 128 MiB；
  作者/封面暂不提取，精确全书文本长度未知；重复原件保留已存在的存储模式与数据。
- 新位置采用稳定 part 索引 + 已解码 package path + 章内 normalized UTF-8 selector。
  写入/读取只验证存储与路由；正文 FOUND/MISSING/AMBIGUOUS 由 bounded pager 解析。
- 新标注要求显式同章 quote；评论修改保留 selector。旧全书 progress/notes 不接受新模式。
  不提供跨章单条标注或自动旧坐标转换。

完整设计与限制见 [存储契约](R5-BOUNDED-STORAGE-CONTRACT.md)、[原件随机读](R5-LIBRARY-SOURCE.md)。

## 冻结出口

1. 普通与 ASan/UBSan 的 source、schema/数据兼容、导入失败回滚、位置与 notes 测试成功。
2. 安装后公共消费者验证 file 导入→书库原件→bounded pager→保存→关库重开/改字号恢复。
3. 10/50/100 MiB 的单章/分章固定合成工作负载真实走 SQLite 原件，保留顺序与随机恢复、
   尾部读取、进度重开、页面 hash 及内存数据。沿用现有 WP6 工作区门槛，进程 RSS 单列，
   不把它改称完整绝对性能预算或真实语料。
4. 同源完整 native 七作业与工件核对完成；新候选的失败、跳过、缺证据不算通过。
5. 固定 API 头、源码和 schema，再开始 H8；新模式不能静默全文回退。

## 宿主接续

H8–H11由主代理团队负责。Windows受测源码`2a9dcff8131543f27cad358fe254b6d4253423c0`，
run [39865943512](https://github.com/NoGod3524/EXReader/actions/runs/39865943512)成功：
26项原自检、158步/8截图、51项证据拒绝、80项H8检查、worker11项正例及11项反向拒绝。
其SDK八树与K一致。158正例采用新增唯一编号夹具；原重复文本字节保留为歧义拒绝回归，
不宣称原重复夹具能够唯一导航。交付文档HEAD为`2b6f46256cc214d981975931c7086546c2541d1a`。

Windows新SDK实现复验源码`8c51264b9017c255345b7ba2056c4f6bd1f1969a`，
run[39871687848](https://github.com/NoGod3524/EXReader/actions/runs/39871687848)全部成功，原26/158、51拒绝、80H8及11正反worker门禁保留。
该源码在当前K之前，仅测试/文档后继变化；其保护树与当前K相同，后续共同源码复验已绑定当前K祖先守卫。

Linux受测`6cb58962866c4f2223dfba0d21b6d36675cbfff1`，
run[39872057413](https://github.com/NoGod3524/EXReader/actions/runs/39872057413) attempt2完整重跑成功：
原20、四组回归（故障26）、H11专项37、backend82全部通过，当前K祖先及八树守卫通过。
attempt1在用例开始前窗口映射超时，失败原件保留。交付HEAD`49edfd4c…`已合入当前集成分支。
### 四宿主共同源码首轮（未通过）

受测源码`9fb084a1fb9307b459f21f60ed91f12fffd14a00`包含当前K祖先，八项保护树与K逐项相同。
四组均为该源码、attempt 1；完成日志与Actions作业/工件元数据已核对。

| 平台 | run | 完成结论 |
| --- | --- | --- |
| Windows | [39875523437](https://github.com/NoGod3524/EXReader/actions/runs/39875523437) | 成功；原26自检、158步/8截图、51证据拒绝、H8的80检查及worker11正例/11反向拒绝通过 |
| Linux | [39875526650](https://github.com/NoGod3524/EXReader/actions/runs/39875526650) | 成功；原20、四组回归、H11专项37及backend82通过，H11严格接受 |
| Android | [39875520153](https://github.com/NoGod3524/EXReader/actions/runs/39875520153) | 失败；原45项中重排进程重启帧比较失败，独立10和bounded11通过；严格汇总拒绝，证据正反例门禁未执行 |
| Apple | [39875517031](https://github.com/NoGod3524/EXReader/actions/runs/39875517031) | 失败；三SDK、package、macOS及iPhone成功，iPad首次导入用例失败；collector及严格summary拒绝 |

Android的49页/49次native next/0 recovery不能替代失败的重启比较。
iPad其余12项与已修的test08通过，但首例没有完整步骤/附件，不能授予Apple包通过。
现有失败原件不能区分首次点击未触发与启动后继任务覆盖；接续增加单次点击前状态及有界操作观测。
修复后固定新共同源码，四组全部重跑；本轮桌面通过项不拼入下一源码。

### 四宿主共同源码第二轮（未通过）

固定源码`b64c72aeca99b9b8e4bf9b5555cac78446dd050b`，K祖先与八保护树一致。
Android候选`29b892c1158aa17f2150a88636133fa55cb8ea4f`的实际实现/ownership为
`eba7bd58ef8431a4477eaa1db96a9bf5f01baa51`：共享绘制观测、原8秒验收截止、
PDF翻页前异后同、两类重启新PID及强制帧PNG/metadata，原48与额外20拒绝检查。
Apple候选`e14cb4a7e0a7c36213f7a82879b56dcebb3ea641`要求唯一、前台、稳定的原生Button单次点击，
保留原截止与结果断言，并补仅UITest模式的16条有界操作trace；首次导入失败根因仍未确定。

| 平台 | run | 状态 |
| --- | --- | --- |
| Windows | [39879077780](https://github.com/NoGod3524/EXReader/actions/runs/39879077780) | 成功；原26、158步/8截图、51拒绝、80项H8及worker11正例/11反向拒绝 |
| Linux | [39879080162](https://github.com/NoGod3524/EXReader/actions/runs/39879080162) | 成功；原20、四组回归、H11专项37及backend82，严格接受 |
| Android | [39879075101](https://github.com/NoGod3524/EXReader/actions/runs/39879075101) | 成功；45+10+11用例零失败零跳过，49页/49次next/0 recovery，48+20门禁及严格accepted通过 |
| Apple | [39879072615](https://github.com/NoGod3524/EXReader/actions/runs/39879072615) | iPhone首次导入失败，collector拒绝；macOS/iPad各13UI/67步骤及package通过，summary因上游失败严格拒绝 |

iPhone的test01在90秒内未导入，13项中1项失败。点击前、点击后及结果等待失败的trace均只有startup1–6，
token=0，无fixture/import请求；长度不足512字符，没有尾部截断。
同次观测确认Button唯一、enabled/hittable、应用前台、frame稳定，XCTest记录了Synthesize event；
本次handler未进入，不能归因于SDK导入、busy拒绝或晚startup覆盖。
失败工件`12469504968`保留，不授予本轮共同验收。
Apple最终为六作业成功、iPhone失败、summary拒绝；summary的证据拒绝回归按条件跳过，不计通过。

### 四宿主共同源码第三轮（通过）

固定源码`e25959e1285b5ebf9a4bf5b27c596d12702dc695`，K祖先与八保护树一致。
候选`0ce4e681d459e7433029eb7a8ae0fcb862c7fbeb`只将共享导入输入改为一次100ms press，
没有fallback、第二次输入或预算/断言变化。本轮三平台均完成真实导入闭环；原tap未送达的底层原因尚未确定。

| 平台 | run | 状态 |
| --- | --- | --- |
| Windows | [39881691924](https://github.com/NoGod3524/EXReader/actions/runs/39881691924) | 成功；原26、158步/8截图、51项证据自验、H8的80项及worker11正例/11反向拒绝 |
| Linux | [39881694674](https://github.com/NoGod3524/EXReader/actions/runs/39881694674) | 成功；原20、四组回归、H11专项37及backend82全部通过 |
| Android | [39881689136](https://github.com/NoGod3524/EXReader/actions/runs/39881689136) | 成功；45+10+11零失败零跳过，49页/49次next/0 recovery、48+20门禁及最终accepted通过 |
| Apple | [39881686534](https://github.com/NoGod3524/EXReader/actions/runs/39881686534) | 八作业成功；三平台各13UI/67步骤/50附件，SDK21/Model18/bounded15及各legacy21通过，严格summary与97项门禁通过 |

四组共11作业全部同源成功，11份必需工件均同run/source、非空、核对时未过期，Actions SHA-256 digest有效。
Apple八个必需工件名称逐项匹配；summary初次及回归后再次`accepted=true`、`problems=[]`。
本轮Windows/Linux/Android均重新完整执行，不转授前轮通过项。
SDK K保持9c69；S3包含K祖先，八条保护树逐项相同，未重新打开SDK冻结。

授予H8–H11各自声明范围：Windows、GTK/X11 Linux、Apple macOS及iPhone/iPad模拟器、Android API34 x86_64模拟器。
EPUB采用有界入口与章内持久化；其他重排格式仍保留明确快照上限，各平台原有格式范围与限制继续适用。
本轮不是旧12组35作业的重新验收；旧sdk-baseline.json仍属K2历史。

### S3必需工件身份

以下均绑定上述S3及表中平台run；只登记Actions API元数据，未下载或重新计算工件。

| 平台 / 工件名 | ID | 字节 | Actions digest |
| --- | --- | ---: | --- |
| Windows / `EXReader-WP13-Windows` | `12470139324` | 39606946 | `sha256:ebd0b9d2c180221a9d11f76a1e8f68cf857b7c674d3d401247cde8bb54bc59cf` |
| Linux / `WP13-Linux-e25959e1285b5ebf9a4bf5b27c596d12702dc695` | `12469954735` | 33045142 | `sha256:4a68ab261c7a5671df9c168ae2d02e9511eb0611f01d67594a7e2ff888c249b4` |
| Android / `EXReader-WP13-Android` | `12471048990` | 154348455 | `sha256:ad1a6825da666a887067280a9d2f3af1cecd4848296bd8c8deed044acecd80ab` |
| Apple / `wp13-apple-iphone` | `12472330001` | 36826405 | `sha256:1e4c5f6379058c83448d4ebaa842ad9c9aedbf9f969cfd7ab1f897283500cf4b` |
| Apple / `wp13-apple-package` | `12471416222` | 126995103 | `sha256:a8a3fb08438ac01bf0da0fb41a4fa0e464340abc3c6071e2c08885cc0351d308` |
| Apple / `wp13-apple-ipad` | `12471398195` | 46007962 | `sha256:47e5611e59d0bb43002025c2f3319ea4001eb3f122c22c5461825390657d1fa2` |
| Apple / `wp13-apple-validation` | `12471383725` | 66581 | `sha256:0a3eddccf152e77d4889fbde50515415b761135f6bada523ca7d94f6509bcbd4` |
| Apple / `wp13-apple-macos` | `12471018852` | 36179253 | `sha256:546fd172a9de515328a9814c615aa436766f7c7e1649918dc74a0dfc1cbbf93e` |
| Apple / `wp13-apple-sdk-iphoneos` | `12470712983` | 17874526 | `sha256:8ad0ded7d7c387dada7e83309bac65df7d665364c6b14afc893b69d7f5d4e130` |
| Apple / `wp13-apple-sdk-iphonesimulator` | `12470213597` | 18156106 | `sha256:4bddfb20d57c60a3fc2e69ea75838791347ff3141c6d17558a8781493471f051` |
| Apple / `wp13-apple-sdk-macos` | `12470069004` | 18157799 | `sha256:e515c63290759407f49fcf7b9ee47efe77e79c9ca48d13a368f091d5ec7e8dd6` |

Windows job`120180288386`、Linux job`120180297063`、Android job`120180279876`。
Apple的SDK三job为`120180270741`/`120180271003`/`120180271080`，
UI三job为`120181006859`/`120181006824`/`120181006905`，package`120181006862`，summary`120187456639`。

H5修补、H6程序门禁、H7文档和R3测量已纳入K，并在K的六组冻结运行中验证；S3只重新执行四宿主，
见 [许可证复核](READING-LICENSE-REVIEW.md)；
H6 跨平台证据门禁的受测身份与新日志候选分列，见 [门禁复核](READING-PLATFORM-GATE-REVIEW.md)。
旧联合包的`docs/validation/sdk-baseline.json`仍记录K2历史身份；新联合收口须显式提升契约并重验。
本次授予当前SDK源码/API/schema冻结；发布tag、默认分支必需检查、真实语料验收仍未完成。
真实语料保持0/1710，旧源码98作业长测不转移，新增WP16 CPU信用为0。
