# EXReader Framework

GPLv3 电子书阅读框架：无应用 UI 的书库、格式解析、正文渲染、标注、备份与转换。当前框架版本 **0.2.0**，基于 EXReader 0.1.1 提取。

## 三条版本线

- [`codex/framework`](https://github.com/NoGod3524/EXReader/tree/codex/framework)：GPL-3.0-only 框架，当前分支。
- [`codex/reader-app`](https://github.com/NoGod3524/EXReader/tree/codex/reader-app)：基于同一框架 API 的完整阅读器，包含书架、设置和平台壳。
- [`codex/reader-0.1.1`](https://github.com/NoGod3524/EXReader/tree/codex/reader-0.1.1)：冻结的原有 MIT 阅读器。[原版安装包](https://github.com/NoGod3524/EXReader/releases/tag/preview-0.1.1) 保持原许可。

## 使用

```js
import { createLibrary, createReader } from './src/index.js';
import './src/render.css'; // 需要正文渲染时由宿主引入

const library = createLibrary({ name: 'my-library' });
const { book, duplicate } = await library.importFile(file); // 浏览器 File
await library.updateBook(book.id, { title: '新书名', tags: ['文学'] });
const books = await library.listBooks({ query: '文学', sort: 'title' });
const reader = await createReader(container, await library.getFile(book.id), book,
  await library.listNotes(book.id), {
    relocate: location => library.saveProgress(book.id, location),
    error: error => console.error(error),
  });
await reader.next();
await reader.close();
const backup = await library.createBackup(); // Blob，保存方式由宿主决定
await library.close();
```

应用自行提供按钮、弹窗、主题、文件选择与保存对话框。框架导入时不会创建 DOM、打开数据库、注册 Service Worker 或设置全局事件。按需调用正文渲染才会创建内容节点。

## 能力与边界

| 能力 | 当前状态 |
| --- | --- |
| 书库 | 导入、重复检测、按书名 / 作者 / 标签搜索、排序、收藏、阅读状态、修改元数据 / 封面、删除时清理文件与标注 |
| 流式书籍 | EPUB、FB2、FB2.ZIP / FBZ、TXT、RTF、MOBI / AZW3、DOCX、HTML / HTM |
| 固定页面 | PDF（PDF.js）；CBZ 图片漫画（Foliate 固定版面） |
| 有声书 | MP3、M4A、M4B、OGG、OPUS、WAV、FLAC、AAC，实际解码依赖设备 |
| 位置和标注 | CFI、PDF 页码 / 矩形、音频时间点、笔记、Markdown 导出 |
| 格式输出 | EPUB、TXT、HTML、FB2、RTF、DOCX 和原文件；正文转换不保留复杂排版与图片 |
| 迁移 | 原文件、元数据、封面、进度、标注的 ZIP 备份 / 合并恢复；兼容 0.1.1 备份 |
| 可选桌面转换 | `integrations/calibre/` 独立 Rust crate，调用用户另装的 calibre；无 Tauri / UI 依赖 |

当前实现是 JavaScript + 浏览器 WebView 框架，存储使用 IndexedDB；解析、排版、PDF 和媒体功能需要相应浏览器 API。入口可在 Node 导入和查询格式，但目前不是可在服务器执行所有格式解析的原生引擎。可用于 Windows、Linux、macOS、Android、iOS、iPadOS 的浏览器 / WebView 宿主；平台安装包属于阅读器分支。

MOBI / AZW3 不支持 DRM；现有自动化样本主要验证基础 MOBI。CBZ 当前验证图片页解析；图像页不提供文字选区、文字转换或 CFI 高亮保证。PDF 标注存于书库，不写入 PDF。扫描 PDF 转换需要另行 OCR。大体积 ZIP 备份当前在内存中完成，上限 1 GB。未实现 OPDS、同步、OCR、DRM / LCP、有声书章节 / 后台播放服务。

## 开发与验证

Node.js 22.12+（推荐 24）。

```sh
npm ci
npm run test:node
npm run build
npx playwright install chromium webkit
npm test
cargo test --manifest-path integrations/calibre/Cargo.toml
```

`dist/exreader.js` 是 ESM 入口，动态导入的分块与 `render.css` / `exreader.css`、`pdf-assets/`、`licenses/` 需一同部署。PDF 默认从站点根路径 `/pdf-assets/` 加载字体和解码器；已有资源路径的应用可用 `await configurePDF()` 指定。测试页面只提供空白宿主，不包含阅读器界面。

[验证记录](docs/FRAMEWORK_VALIDATION.md) · [API](docs/API.md) · [后续格式与架构方向](docs/FRAMEWORK.md) · [第三方许可](THIRD_PARTY_NOTICES.md) · [原版研究记录](docs/PROJECT_STUDY.md)

## 许可

Copyright (c) 2026 EXReader contributors。当前分支自有代码采用 **GPL-3.0-only**，见 [LICENSE](LICENSE)。允许商用；分发基于本框架的派生程序需按 GPLv3 提供对应源码及构建所需材料。第三方代码继续保留其原许可。0.1.1 及此前已授予的 MIT 许可不撤回。项目中的电子书文件不因导入而改变版权。
