# SDK 3.41 整页背景候选

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
