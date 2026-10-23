# WP6 有界 EPUB 章阅读

SDK 3.40.0，核心 3.39.0，ABI1/schema6。新入口为
`exr_publication_pager_create()`；原完整文档快照及借用指针生命周期不变。
包 B 的设计和早期失败保留在 `docs/WP6-BOUNDED-DESIGN.md`、
`docs/validation/wp6-bounded-chapters.json`，不作为本实现的通过证据。

## 数据与所有权

章扫描建立紧凑结构索引、全局节点 ID 和规范化 UTF-8 坐标；普通正文和属性按窗重读。
样式声明先收集，再以一次流式批处理计算所有节点样式；计算样式和字体族由稳定 intern 池拥有。
模板保留声明的真实祖先；模板中存在祖先不代表其表格、float 或 ruby 已完整装入。
完整段落、表格、ruby、float 和不同书写轴的局部上下文作为不可分单元；窗口边界不强制分页。
主竖排 viewport 可跨窗；局部不同轴上下文保持原分页语义。

分页栈、表格游标、行缓冲、双向状态及 checkpoint 保存全局坐标，不保存窗口字符串指针。
窗口重载完整验证源成员及结尾完整性；失败清空输出，保留取消、限界、读取和格式错误类别。
publication 由 pager 保留；字体和宿主回调遵循原 pager 生命周期。所有接口串行使用，回调不得重入。

## 预算和统计

默认章工作预算 64 MiB，首选源窗口 4 MiB；窗口大小是提示，不拆分真实原子单元。
索引、名称、样式映射、文本节点映射、样式池、XML、CSS、外部 CSS 解码和 ZIP 工作分配前计费。
ZIP 工作在总额中固定预留至多 1 MiB；样式 visitor 与其消费者固定分区，避免池增长挤占下批空间。
单个不可分单元或声明超过可用额时返回 `EXR_LIMIT`，不抬高原快照的 32 MiB 成员上限。
独立阅读入口沿用 128 MiB 流输入总限界、256 层和每元素 256 属性边界。

`exr_pager_chapter_statistics()` 分列源逻辑字节、完整索引、解析/续排工作区、页缓存、checkpoint 和显式快照。
容量按实际保留数组计费；峰值是保守上界，包含 XML/CSS/ZIP 临时分配和投影数组新旧重叠。
续排统计包含字形容量、双向分析、嵌套 cursor 和表格状态；共享对象可能保守重复计入。
有界入口的文本/塑形工作计数按一次公共翻页操作重置；同页内嵌套、试排和浮动 cursor 共享计数，
原数值限界不变，完整快照路径仍沿用原累计限界。超过 4 Mi 字符的完整阅读另有独立回归。
字体、图像和绘制输出使用原有独立预算；进程 RSS 仅交叉核对，不替代这些分类。
10→100 MiB 增量出口按固定语料的索引加解析/续排峰值比较，不宣称任意节点密度下恒定索引。

## 查询与正文输出

`exr_pager_cfi_create/resolve` 保留原 package spine 路由和章内全局节点 ID，支持最多 32 scalar 的上下文及唯一断言修正。
`exr_pager_anchor_create/resolve` 使用原书签范围和歧义口径；查询可逐出当前窗口，不改变分页位置。
`exr_pager_read_text` 流式提供规范化 UTF-8 选择或整章正文，每块至多 32 KiB，块边界完整。
sink 失败或取消时可能已接收前缀，文件原子发布由宿主处理。
完整结构/资源导出仍使用原显式快照接口；新流式出口覆盖正文，不新增高保真全格式转换声明。

## 验证入口

`tests/test_chapter_index.c`、`tests/test_chapter_window.c`、`tests/test_style_budget.c`、
`tests/test_chapter_source.c`、`tests/test_chapter_reader.c`。
读者回归对照原快照逐页哈希，覆盖多窗口、晚 CSS、声明祖先内的跨度表格、float、ruby、RTL、
主竖排/局部横排、多 part CFI、Unicode/断言修正、正文和选文逐字节对照、逐出恢复、预算及错误清理。
`examples/window.c` 同时作为默认/裁剪静态 SDK 的安装消费者；C++ 精确版本消费也调用新入口。

固定语料与独立新进程测量使用 `tools/generate_bounded_chapter_corpus.py`、
`tools/wp6_chapter_probe.c`、`tools/run_wp6_bounded_probe.py`。
Windows、三平台原生 CI、Linux sanitizer 和最终状态集中在
`docs/validation/2026-10-20-wp6-window-reader.json`；尚在执行的条件不得标为通过。
WP16 长测必须固定最终集成源码，沿用 `docs/RELIABILITY-HANDOFF.md` 第 6 节的拒绝条件。
