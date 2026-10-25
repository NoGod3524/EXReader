# SDK 3.41 整页背景候选

## 当前完整 SDK 门禁结果

受测源码 `c2a8a2d77d9e3b5e8f4739a6d81caf33d3080677`，生产 SDK 树仍为 `edddc463c06ed5731195cdb8f06b2df6dff7699e`。[完整运行 40170665534](https://github.com/NoGod3524/EXReader/actions/runs/40170665534) attempt 1 的 17 个作业全部 success，最终 `reading-required` 作业 `121103345526` 原始日志给出 `accepted=true`、`problems=[]`、SDK 3.41.0 / ABI 1 / library schema 7。范围是原生阅读 SDK 与固定 representative real-v1 语料，`published=false`、`complete_product=false`。

同一源码、同一运行覆盖三桌面 native、Android、iPhone/iPad 模拟器、sanitizers、fuzz、六个 reading-core/library 安装消费者、R2 原始语料与性能。性能实际环境为 `amd-epyc-7763`，仍用原 `tests/reading_real/budgets.json`，SHA-256 `75142b54f03b62d8f12752ff96fbc2f8e7f0d910511ec218165c39844ef5b0f3`；环境注册表 SHA-256 `d389ec5c71f702a52dfed8acf7b23be4c760acfb8a6a16d7192b701f56c0a6d3`。这一轮没有执行其他 CPU 型号的性能预算。

最终汇总工件 `12590152318`（`reading-required-40170665534-1`），3350 字节，SHA-256 `c506cf5105442c6584286c3568237942a06a63b43911caa527e115afbc4ef987`，有效期 `2027-01-23T06:52:33Z`。云端最终作业下载并核验本轮原工件、实际程序与性能输出，本地仅查日志和元数据。最终日志同时登记六份未发布候选的字节数、归档与 manifest 散列。

此前独立新 API ASan/UBSan 修正轮 `1e4f60c5` / [40169200690](https://github.com/NoGod3524/EXReader/actions/runs/40169200690) 也已 success：原 native 161 项逐名字匹配执行前注册表及 JUnit，候选 probe 580 断言通过。前述失败轮均保留。

产品共同线仍使用旧冻结 3.40；宿主整页配色、真实旧库迁移、物理设备与完整产品须依各自运行验收。以下段落保留此前各源码的调查与失败记录。

用户已授权独立新增SDK候选，保留旧3.40冻结提交 `9854061be331fe603a1822d9b2b36ee357154927`、ABI1和原预算。方案见 [固定提案](https://github.com/NoGod3524/EXReader/blob/3ede1ea6623a961a180af5c3d811aad99ea47191/docs/READER-PAGE-BACKGROUND-PROPOSAL.md)。本分支未合入产品共同线，不发布tag/Release。

SDK候选3.41.0 / core3.40.0新增 `exr_render_page_background`；只在原渲染循环前初始化指定画布，支持1或4通道。RGBA是straight RRGGBBAA；灰度沿用canvas原77/150/29权重并忽略alpha。原书的背景、边框、文字、彩色字体和图片随后照原顺序绘制。旧三个入口始终传白色，保留原快速memset路径。新入口失败清空输出，页位图64MiB及原CPU/工作区预算不改。

Linux初轮在Actions重新构建原冻结SDK，安装两个版本并分别编译仅消费安装包的消费者。12个页面样本包含真实图片/显式白底/半透明绘制、复杂文字、双线/虚线/点线/透明/RTL/竖排表格、彩色字体和有界EPUB第0/95页。旧三个入口的位图文件必须逐字相同；新白底与旧入口逐字相同。浅/深/透明/半透明背景检查真实像素、图片alpha、书籍显式白底；逐取消轮询点验证清空输出且重试一致。原全部native测试原样运行；旧用例与夹具未改。

所有构建、运行、语法检查、夹具和工件处理只在Actions。初轮b911815e/run40164920053 Linux原native164与候选535断言已通过。后续受测源码 `edddc463c06ed5731195cdb8f06b2df6dff7699e` / [run40165924012](https://github.com/NoGod3524/EXReader/actions/runs/40165924012) 三桌面生产者均success，每个平台原native164/164、冻结消费者165、候选580断言、12页样本；旧三个入口的实际位图逐字相同。

首次strict因root引用了985工具中不存在的下载helper而ImportError，原失败保留。仅修自有汇总器后的 `4a5a793ebe2a98a96ed119334399821e923c19ab` / [run40166642441](https://github.com/NoGod3524/EXReader/actions/runs/40166642441) 已success：Actions下载并认证原轮三个ZIP、原实际消费者及原始位图，不重编、不把validator当作新受测SDK。

| 平台 | 原生产作业 | 原工件 ID | ZIP字节 | SHA-256 |
| --- | ---: | ---: | ---: | --- |
| Linux | 121086827818 | 12587888112 | 6195914 | `4104e5ff58134f64de6aff89d1f4c39ee05845f642dc71aa07ee88ad2efa4e61` |
| Windows | 121086828030 | 12588696982 | 4770338 | `9564721e006ddaab7433989f5fd52d1ddf4843a9bd2957a3b583377d9f368f5b` |
| macOS | 121086827964 | 12588512430 | 5276683 | `ecb38fde4efc79bb40aeb16c59680320bb87473ffc9bb84c8cc1efec90892c9c` |

三个原工件有效期至 `2027-01-23T05:32:45Z`。认证汇总工件 `12588313157`，1287字节，SHA-256 `8f95d1304cf63d325513b0f21d049b38e3edab73784618ece104299c31a85c95`。三平台原API位图SHA-256均 `afac9ce14aea617710dda0444e0914b724290716c4fe49f77cb0d92a68f50b41`，每平台冻结及候选消费者各自的实际程序散列保存在汇总报告中。

Android、iPhone/iPad、宿主真实控件与原六包/可靠性/性能门禁仍须各自实测。共享模块使用原SDK版本构造parser身份，3.41新建记录通过不等于3.40旧记录迁移通过；旧库重开/锚点身份兼容尚未授予。仅SDK消费者的EXACT版本声明随新SDK更新，旧3.40声明和原证据仍保留在冻结提交中。

## 移动端与原门禁的后续结果

移动端受测source `1180d9ce9b40cf30e1b9796ddb5392cf3a18215c` / [40167198635](https://github.com/NoGod3524/EXReader/actions/runs/40167198635) attempt1，Android API34 x86_64、iPhone/iPad arm64模拟器三生产者及严格ZIP认证均success。各自在同目标重新构建并安装冻结SDK与候选，执行未改的同一probe，核实际安装程序hash和12页原位图一致。没有物理设备/宿主主题UI授予。首轮ba1fc111/40167048953在交叉编译消费者查找安装Config时失败，1180仅修显式EXReader_DIR和查找根，不改SDK或probe；原失败保留。

原六份reading-core/library的独立包门禁在source `ba1fc1116b7080fcaba163856387410a54d340e6` 的Linux [40167143220](https://github.com/NoGod3524/EXReader/actions/runs/40167143220) 与Windows/macOS [40167144549](https://github.com/NoGod3524/EXReader/actions/runs/40167144549) 均success，各自产生未发布候选。它们不替代完整reading-required门禁。

完整门禁1180/[40167529130](https://github.com/NoGod3524/EXReader/actions/runs/40167529130) 保留失败：原985起点没有后续正式冻结预算，performance在构建前拒绝；R2对当前下载的pg84原件散列不符而拒绝，未换语料或修改预期。已普通合入已接纳默认分支固定 `cdfe48231853d6e70fba2c41b42bdd187155901a` 的原门禁工具/原冻结预算，生产SDK树仍逐字等eddd；守卫同时核foundation的SDK仍等985、预算/合同/清单仍等foundation。R2原始冻结字节来源问题仍单独处理，不能授予完整新SDK。

独立ASan/UBSan轮f7e659cd/[40167606838](https://github.com/NoGod3524/EXReader/actions/runs/40167606838) 的原native实际161/161及新API580断言均通过，但root汇总误把Release的164写作Sanitize配置预期，最终AssertionError；不抹去原失败。修正为Sanitize实际固定161，并逐名字核执行前ctest注册表与JUnit、拒绝跳过；只修验证逻辑，SDK、原测试和编译选项不变，后续结果独立登记。

为避免上游可变URL替换冻结输入，新增显式原始字节缓存路径：仅在Actions认证原已接受run39902467216/source fa540271的原R2工件12479327987（固定ZIP大小/摘要、上游作业、有效期），只取其八份原输入，并逐份重新验证现有清单的大小/hash及原发布者URL。新R2/performance仍重新运行当前消费者；不复用旧SDK输出。合同、清单和数值预算不改；当前发布者许可条款仍重新下载核验。错误缓存、截断、额外字节和符号链接均拒绝，默认收集器仍只访问发布者；发现阶段不能使用缓存。恢复来源JSON随新轮原证据保存。该路径须先通过独立inputs云端验证，再启动完整门禁；失败时不授予新SDK。

上述临时恢复实现1b0ba6c3/run40169486853已实际通过10个收集协议用例、原8输入逐份恢复及当前许可核验。后续发现用户早已批准的CPU固定交付 **220585e8248918096b9fc2c389ea5ad2389d388b** 同时携带已验收的原始输入恢复器（原run39974986212、固定工件12510622310），因此普通merge该完整交付，保留它的已验 `collect cached`，删除本分支重复恢复器；此前运行和失败仍归各自source。该交付还保留7763原预算逐字不变，并为9V45、8573C分别登记独立固定预算及精确环境选择；没有按当前失败重采样或增宽预算。

完整轮1b0ba6c3/run40169614704的R2已通过，performance随后在旧3.40保护树守卫处拒绝3.41（仍为未验收）。新增显式新SDK入口只允许完整eddd源码和实际3.41 runtime/ABI1；旧默认入口仍严格985/3.40。新报告如实保留两侧不同SDK身份，各自核规范SDK树及实际提交树；原baseline JSON/散列、合同、字体、输入、CPU/compiler/reference、数值/大小/像素与页签名边界全部不变。最终reading-required也须显式传入候选身份，不能由报告自行启用新模式。新增独立scope拒绝例和原协议先在Actions预检，之后才重新跑完整门禁。
