# SDK 3.41 整页背景候选

用户已授权独立新增SDK候选，保留旧3.40冻结提交 `9854061be331fe603a1822d9b2b36ee357154927`、ABI1和原预算。方案见 [固定提案](https://github.com/NoGod3524/EXReader/blob/3ede1ea6623a961a180af5c3d811aad99ea47191/docs/READER-PAGE-BACKGROUND-PROPOSAL.md)。本分支未合入产品共同线，不发布tag/Release。

SDK候选3.41.0 / core3.40.0新增 `exr_render_page_background`；只在原渲染循环前初始化指定画布，支持1或4通道。RGBA是straight RRGGBBAA；灰度沿用canvas原77/150/29权重并忽略alpha。原书的背景、边框、文字、彩色字体和图片随后照原顺序绘制。旧三个入口始终传白色，保留原快速memset路径。新入口失败清空输出，页位图64MiB及原CPU/工作区预算不改。

Linux初轮在Actions重新构建原冻结SDK，安装两个版本并分别编译仅消费安装包的消费者。12个页面样本包含真实图片/显式白底/半透明绘制、复杂文字、双线/虚线/点线/透明/RTL/竖排表格、彩色字体和有界EPUB第0/95页。旧三个入口的位图文件必须逐字相同；新白底与旧入口逐字相同。浅/深/透明/半透明背景检查真实像素、图片alpha、书籍显式白底；逐取消轮询点验证清空输出且重试一致。原全部native测试原样运行；旧用例与夹具未改。

所有构建、运行、语法检查、夹具和工件处理只在Actions。初轮b911815e/run40164920053 Linux原native164与候选535断言已通过。后续edddc463/run40165924012三桌面实际构建/测试生产者均success；首次strict因root引用了985工具中不存在的下载helper而ImportError，原失败保留。只修改自有汇总器，后续Actions重新散列该轮三个原ZIP并核原始像素/程序，明确program source与validator source，不重编或转授新生产source。Windows/macOS最终工件认证、Android、iPhone/iPad、宿主真实控件与原六包/可靠性/性能门禁须按各自真实结果独立登记；不能把桌面候选当作六目标迁移完成。仅SDK消费者的EXACT版本声明随新SDK更新，旧3.40声明和原证据仍保留在冻结提交中。
