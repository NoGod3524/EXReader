# Apple 原生目录导航

固定起点 `356c57a4c641f05e10cff13850e24bd94336454e`；本包在 Search 已验源码之后接入 F2。

F2 源码仅复制受测提交 `cbd7832b914bddcf99e06a85962d301a00b47efa` 的 `apps/reader/navigation`，树身份固定为 `9395914832e191ad63f18f6188ca5044260d2f12`。其 Linux/Windows 包级证据见 [固定验收记录](https://github.com/NoGod3524/EXReader/blob/13fd6dc1408fba0e71f5bc5a919e225a97c972c3/docs/validation/reader-navigation.json)。

原生 SwiftUI 目录面板每次最多显示 32 个同级项，保留作者顺序、父子关系及重复标签。子目录、上一级、前后批由显式按钮触发；同一列表行的跳转和子目录采用独立按钮样式。PDF/CBZ 明示“按页入口 · 非作者目录”。作者目录使用 CFI 时仍只显示普通标题，宿主读取该行并自动进入严格原生解析；界面不提供手工技术输入。

每次队列调用在同一实际线程内打开并释放 F2 快照，跨调用仅传递独立 Swift 值。目录和目标均绑定原件格式、SHA-256、字节及解析版本；显示前重新读取原件核验。路径重复只展示候选 spine，不自动选首项。片段不存在必须由用户确认章首，不静默降级。

跳转在第二个独立 SDK 库实例中直接调用公开 `document_resolve` / `publication_cfi_resolve` / 固定页数组，核对章节索引、path、id、node 或 CFI 点；不重复调用 F2 充当独立校验。CFI TEXT 节点只在 raw 与 normalized 范围逐字节一致时按 Unicode scalar 累加 UTF-16 单位，拒绝代理项内部与空白折叠；元素只使用公开子节点边界。实际布局 pager 的整个 projection 与独立文档逐块比较，原生 anchor 必须 FOUND 且位置精确相等后才渲染与保存。固定页没有文字 FOUND 声明，仅授予独立页面身份核验。

关闭、取消、换书通过 generation 和当前书身份丢弃迟到结果；候选渲染以前不改变旧 session。提交沿用既有 `HostCancelBox.commit` 取消边界。应用重开重新读取目录，不持久化快照指针或未经核验的目标。

Apple 构建只显式链接安装后的 `libreader_navigation.a` 与既有动态 SDK；不传递模块 CMake 的静态 SDK。实际宿主二进制和 `dladdr` 检查共同核实单一 SDK 提供者。冻结 SDK `9854061b…`、3.40.0/ABI1、产品 schema1 均不变。

容器观测改为 collector 与 always-trace 各自独立报告。定位工具在发出命令前独占创建报告路径，拒绝覆盖已存在文件；每条命令的参数、原始输出、退出码和原有超时保存。当前不添加重试、不改变 collector 断言和测试期限。

源码、12 项 native 适配检查、6 个真实 UI 用例（macOS / iPhone / iPad）及同源工件汇总由 `reader-apple-navigation.yml` 执行。CFI 夹具先由安装 SDK 的公开创建接口生成合法目标，再写入真实 EPUB 作者目录；不猜测内部路径。原有完整回归只在最终稳定源码上执行，旧源码通过记录保持原归属。

保留的早期运行：`eb123aa8` / `40130739432` 的 native 11/12，探针在独立连接提交后重用了已失效的原件 lease；`abdc772b` / `40131358600` 的 native 12/12、macOS UI 5/5、iPhone 与 iPad 各 4/5，失败集中于 iOS 列表行默认按钮样式把“子目录”点击同时作为父行跳转。断言与期限均保留。该源的原始 ZIP 与失败日志继续保留，更新源重新执行完整专项。

## 同源云端验收

受测源码 `1e86ddac59a415d18370ce40bdd0489622e9a896`，专项 [run 40132480954](https://github.com/NoGod3524/EXReader/actions/runs/40132480954) / attempt 1，7/7 作业成功。严格汇总 `120989689758` 实算六份生产者 ZIP 的大小与 SHA-256，核对每份实际程序及报告身份，`accepted=true`。原 SDK 八树与 schema1、F1/F2 树身份逐字门禁通过。

| 范围 | 实际结果 |
| --- | --- |
| Swift owner 适配与独立 SDK 定位 | 12/12，含 32/32/6 分页、层级、重复 spine、明确章首确认、原件/产品只读、实际取消及重试、篡改节点拒绝、旧书拒绝、真实作者 CFI 与 surrogate/折叠拒绝、PDF/CBZ 页面身份 |
| 容器原始报告 | 5/5，首个失败 stdout/stderr/退出码保留、重复路径拒绝、独立 always-trace、原超时与部分输出保留；无重试 |
| macOS、iPhone、iPad 实际 UI | 各 6/6、23 个具名步骤、29 份原始附件；普通标题作者 CFI、层级与重开、32 项分页、明确重复章节选择、取消、PDF 页面入口均逐目标通过 |
| 实际程序提供者 | 唯一安装后产品 SQLite、安装后 F1/F2、单一动态 SDK；原 7 个提供者反例保持 |

同一源码随后只发起一次四套原回归：Search [40133477416](https://github.com/NoGod3524/EXReader/actions/runs/40133477416) 已 7/7，三目标各原 4 例 / 14 步骤 / 18 附件，native Search 11、catalog 8、mapping 16 全保留；WP13 [40133494188](https://github.com/NoGod3524/EXReader/actions/runs/40133494188) 已 8/8，三目标各原 13 例 / 67 步骤 / 50 附件，package 与原 97 个门禁反例完整通过，`problems=[]`。Mapping [40133512224](https://github.com/NoGod3524/EXReader/actions/runs/40133512224) 已 6/6，三目标各原 5 例 / 22 步骤 / 14 附件与原 native 全保留。

Shelf [40133527618](https://github.com/NoGod3524/EXReader/actions/runs/40133527618)（`scope=full`）已结束：native 原 catalog8 / shelf16 / account22 与 2202 原件通过，macOS 和 iPhone 的书架7、账号3、生产语义2全部通过；iPad 书架6/7，`test07StoredOriginalReadingAndFilteredReturn` 失败，后续账号与生产语义跳过，汇总未授予。失败时当前 epoch 的真实单行 frame 已对齐 `min_y=0`，但原模型仍等待尚未发出的滚动命令，筛选原书返回一直处于恢复布局。容器定位成功，collector 与 always-trace 原件独立保留。该失败及 iPad 工件 `12577227656`（226856392 字节、`sha256:56181a157e13eefad8ce4c3d1d5427f31cae490dff1e5f9df6ad58bedaa7cc74`）不删改；修复后按新源码复验。

## 真实已对齐布局的恢复修复

候选 `f5d25b4c71ea39bd22bebea4eedfee16ca178c35` 在共同 `observe` 路径修复上述等待：尚未发出滚动时，必须具有同 epoch 的全部当前行 frame、真实正视口、已应用的 query/generation、无加载，且目标确为首个可见行、`min_y` 距零不超过 1pt，才确认布局已经对齐；不伪造 `issued_restore_revision`。过期、部分、缺行、未应用 query、偏离目标的几何仍被拒绝。原 shelf16 检查与 collector、期限全部保留。

该源码导航专项 [40139222963](https://github.com/NoGod3524/EXReader/actions/runs/40139222963) / attempt1 已 7/7 严格通过：新增恢复正反例后 native13/13、容器5/5、macOS/iPhone/iPad 各6UI/23步骤/29附件，汇总 `121010058019` 为 `accepted=true`。同源重点恢复 [40139232257](https://github.com/NoGod3524/EXReader/actions/runs/40139232257) 的原 catalog8/shelf16/account22 与2202真实原件通过；macOS 原04/05/07、iPhone与iPad原05/06/07均3/3，原失败test07分别11.943/15.505/18.470秒通过。这轮恢复仍明确 `diagnostic_only=true, accepted=false`，不作为完整书架授予。

候选的四套完整原回归各执行一次，全部已终态：Search [40140546536](https://github.com/NoGod3524/EXReader/actions/runs/40140546536) 7/7 严格通过，三目标各原4UI/14步骤/18附件；WP13 [40140554070](https://github.com/NoGod3524/EXReader/actions/runs/40140554070) 8/8 严格通过，三目标各原13UI/67步骤/50附件、97个门禁反例保留，`problems=[]`；Mapping [40140570887](https://github.com/NoGod3524/EXReader/actions/runs/40140570887) 6/6，三目标各原5UI/22步骤/14附件，原 native 全保留。

Shelf full [40140560610](https://github.com/NoGod3524/EXReader/actions/runs/40140560610) 的 macOS 与 iPhone 书架7、账号3、生产语义2均完整通过，各保留2202原件、530次真实HTTPS请求和两轮256分片；iPad书架6/7，原02完成全部2202正反遍历，原07过滤原书返回已通过，但原06进程重开恢复失败，账号/生产语义跳过、汇总跳过。失败时100个当前行、epoch10、issued=-1，目标确在第50行的 `min_y=3100`，需要真实滚动；aggregate偏好未触发命令。失败工件 `12580151386`（211742287字节、`sha256:da58d3e1265530e7f3d44319696c00e5a31df1dfb9e761606d234dda0bbd7589`）保留，当前不授予四套完整共同回归。

接续源码 `9d9a9dc085bc79848d974fd6e1cd7f716927f8f1` 在 `codex/reader-apple-reading-records-ui` 改为由真实 restoreRevision 请求/首次出现派发原 `scrollTo`，aggregate只确认真实几何，沿用原post-issue epoch、retry、断言与期限。该源完整app编译和19项产品阅读记录native预检 [40145615101](https://github.com/NoGod3524/EXReader/actions/runs/40145615101) 已通过，但明确 `diagnostic_only=true, accepted=false`；原05/06/07重点恢复 [40145621010](https://github.com/NoGod3524/EXReader/actions/runs/40145621010) 执行中。后续最终共同源码将重新授予实际覆盖的界面与完整回归，不把本页旧源码结果转移过去。规范等价但字节不同的 CBZ 页ID也在接续源码按 UTF-8 逐字节处理；本页 f5 原件不包含这份新 Unicode 授予。

完整作业、生产与失败工件 ID / 字节 / digest / 有效期见 [reader-apple-navigation.json](validation/reader-apple-navigation.json)。所有运行均在 Actions；本地仅源码与 Git 操作。授予范围是本包声明的原生 Apple 导航接口，性能、真机与完整产品均未授予。
