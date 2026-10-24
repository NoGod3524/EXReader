# F2：目录导航

先读[共同约束](README.md)，从固定起点创建`codex/reader-navigation`。
目标是让宿主直接展示书籍自带目录，并将用户选择交回可验证的原生导航目标。

## 文件归属

仅新增`apps/reader/navigation/**`、`tests/reader_navigation/**`、
`.github/workflows/reader-navigation.yml`、`docs/READER-NAVIGATION.md`、
`docs/validation/reader-navigation.json`。

## 交付契约

- 可选安装包`EXReaderNavigation 0.1.0`，公开C ABI`reader_navigation.h`。
  复用`exr_publication_navigation`/`exr_document_navigation`，不自写EPUB/PDF解析器。
- 保留原始顺序、parent、label、href、base、role与part，不把未知/重复路径猜成某章。
  `SIZE_MAX`的未解析目标维持未解析；目录文本作为纯文本，不解释HTML或执行代码。
- 只通过SDK公开API解析本地章节/片段或CFI；输出原样spine索引+path和必要的定位信息。
  支持重复spine的显式身份，拒绝仅凭同路径选第一个。外部链接返回NEEDS_HOST类状态，
  不联网、不启动浏览器、不携带凭据；损坏或越界目标明确失败。
- 没有自带目录时返回空目录；PDF/CBZ可以提供独立的按页入口，
  不能把页码列表称为作者大纲，不能为了本包修改冻结SDK增加PDF大纲能力。
- 快照复制必要字符串，不向UI泄漏SDK借用指针。提供1..100行分页，
  层级/子项查询及独立释放；受检总节点/深度/文字上限明确，越限拒绝而非静默截断。
- 不改当前阅读位置、进度、标注、书库或同步记录；由root在用户点击后执行导航。
  句柄调用/释放遵循创建owner，不创建线程、不允许SDK回调重入。

## 云端出口

Windows/Linux安装后C/C++消费者。覆盖EPUB3 nav、EPUB2 NCX、嵌套/空目录、
重复标题、非ASCII标题、相对路径/片段、重复spine、外部目标、未解析part、
越界/损坏、分页、深度/节点限额、取消及快照在SDK释放后的寿命。
真实可解析目标须在第二独立打开的SDK对象上确认；缺失/歧义不误跳。
保留无目录和不支持作者大纲的准确范围；发布同源报告和安装后消费者身份。
