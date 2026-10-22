# R5 SDK 冻结跟踪

状态：**重新冻结中**。原源码 **`ce5d664c9f76d0613df6d79b27568a7039c4a81e`** 的冻结状态已撤回，
SDK 3.40.0 / library 3.34.0 / ABI 1 / schema 7 契约不变。
Apple 接续发现单段原文加标签超过16KiB窗口时，窗口准备可能递归回同一单元，首次捕获锚点超时。
原六组通过记录与Windows/Linux在该源码的宿主通过记录保留；新源码须重新完成冻结验证及宿主复验。

## 单元递归修复

云端诊断 [39869850934](https://github.com/NoGod3524/EXReader/actions/runs/39869850934)确认，
原Repeated夹具已完成导入、publication打开与pager创建，随后首次anchor capture耗尽180秒。
对照 [39870093796](https://github.com/NoGod3524/EXReader/actions/runs/39870093796) 的16KiB分支重复超时，
64KiB诊断分支完成同一歧义负例。该对照只定位问题，正式宿主保留16KiB窗口。

修复`src/chapter_reader.c`：仅在可见child对应不同unit root时继续下降，
同root的text/inline child直接按完整真实单元加载；实际工作区不足仍返回`EXR_LIMIT`。
`native-chapter-oversized-unit`覆盖16KiB单段、32KiB嵌套inline、重复引文歧义、
全文流式查询与首页面等价，并检查2MiB单元在1MiB工作区下拒绝。
该回归独立设置60秒超时，防止递归回归耗尽整轮预算。修复候选尚未获云端接受。
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

宿主必须保留K祖先关系与以下八项Git对象一致，不能只比较SDK版本字符串。

| 路径 | K中的Git对象 |
| --- | --- |
| `src` | `a1e88421a2f0f6cadc16acaa9ec3fcfdfa4d30e6` |
| `include` | `86fb444dbf1664771d997daeff772bb465d617a7` |
| `cmake` | `ec5eb002674d867228ea033d466973c42b69571f` |
| `CMakeLists.txt` | `a69fd0f8e932a21ae1130045698c0f88181418ef` |
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

Apple、Android、Linux独立实施与云端验收中。新版本各自通过后再收共同宿主源码，不能拼接旧源码结果。

H5修补、H6程序门禁、H7文档和R3测量已纳入K，且按上表重新同源验证，
见 [许可证复核](READING-LICENSE-REVIEW.md)；
H6 跨平台证据门禁的受测身份与新日志候选分列，见 [门禁复核](READING-PLATFORM-GATE-REVIEW.md)。
旧联合包的`docs/validation/sdk-baseline.json`仍记录K2历史身份；新联合收口须显式提升契约并重验。
新源码冻结尚未通过；发布tag、默认分支必需检查、真实语料验收仍未完成。
真实语料保持0/1710，旧源码98作业长测不转移，新增WP16 CPU信用为0。
