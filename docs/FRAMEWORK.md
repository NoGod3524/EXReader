# 框架方向

目标是让不同产品复用书库、解析、阅读定位、标注与转换。框架提供能力和数据，应用负责 UI 与系统交互。

- `src/library.js`：书库业务；`src/store.js`：可替换存储，默认 IndexedDB。
- `src/registry.js`：格式能力；`src/formats.js`：按需加载解析器和内容清理。
- `src/reader.js` / `src/pdf.js`：可选 DOM 内容渲染；`src/render.css` 只包含渲染几何和选区规则。
- `src/transfer.js`：备份与格式输出，全部返回数据，不弹窗、不发起下载。
- `integrations/calibre/`：独立桌面转换组件，运行时另装 calibre。
- 阅读器分支：书架视图、主题、导航、工具栏、保存对话框、PWA 和六平台宿主。

下一阶段按真实样本扩展格式和一致性测试：优先完善 AZW3 / KF8、固定版面 EPUB 和 CBZ 的渲染兼容，再评估 Markdown、CBR / CB7、DJVU 等。每种格式分别记录导入、元数据、渲染、搜索、标注和转换能力。不能把安装了解码库等同于完整支持。

大书库方向包括索引查询、分页、批量任务与流式备份；核心 API 稳定后再拆包发布。原生无 DOM 引擎属于后续架构选择，不把当前 WebView 实现描述成操作系统级引擎。

框架和后续阅读器分支均使用 GPL-3.0-only。冻结的 0.1.1 阅读器保留原 MIT 许可和原发布包。
