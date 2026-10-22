# 三个项目的学习记录与架构取舍

本文保留早期 JavaScript 阅读器方案的调研与取舍。当前 C11 引擎、原生宿主、验收状态和后续质量目标见 [项目概述](PROJECT_OVERVIEW.md)。

本次做了源码结构与关键模块的初步调研，没有逐行审计三个项目。

## Thorium Reader

查阅版本：`42177d6cefd5461ac93a0d28bdfcdf5b2e5412b8`。

- [项目与技术依赖](https://github.com/edrlab/thorium-reader/blob/42177d6cefd5461ac93a0d28bdfcdf5b2e5412b8/package.json)：Electron、Readium、阅读器与书库窗口、独立 PDF 标注测试。
- [标注模型](https://github.com/edrlab/thorium-reader/blob/42177d6cefd5461ac93a0d28bdfcdf5b2e5412b8/src/common/readium/annotation/annotationModel.type.ts)：标注正文和目标位置分开，支持 EPUB CFI、文本引文与位置选择器。
- [阅读设置持久化](https://github.com/edrlab/thorium-reader/blob/42177d6cefd5461ac93a0d28bdfcdf5b2e5412b8/src/renderer/common/hooks/useReaderConfig.ts)：即时设置与持久化分开，提供防抖保存。

EXReader 采用独立标注记录，流式格式使用 Foliate CFI，PDF 使用页码和归一化矩形，音频使用秒数。设置立即应用，进度防抖写入，返回书库时主动保存。目前没有实现 Thorium 的 W3C 标注集互通、LCP、OPDS 和完整无障碍规范。

## SumatraPDF

查阅版本：`9edfa4449c2720bbba1fe4e9eccdabc3ec5d34c1`。

- [项目说明](https://github.com/sumatrapdfreader/sumatrapdf/blob/9edfa4449c2720bbba1fe4e9eccdabc3ec5d34c1/readme.md)：面向 Windows 的多格式阅读器，应用整体涉及 (A)GPLv3，部分组件使用 BSD。
- [MOBI 解析](https://github.com/sumatrapdfreader/sumatrapdf/blob/9edfa4449c2720bbba1fe4e9eccdabc3ec5d34c1/src/shared/MobiDoc.cpp)：区分 PalmDOC、Huffman 压缩，显式处理边界和加密状态；格式解析独立于界面。

EXReader 采用按格式延迟加载的引擎，不在进入书库时加载 PDF worker 或 DOCX / RTF 解析器。桌面壳使用系统 WebView，避免携带一整套 Chromium。Windows `.portable` 标记使书库位于程序旁。没有复制 Sumatra 的 Windows UI、MuPDF 或 MOBI 解析实现，也没有假定它能直接移植到 iOS。

## calibre

- [项目](https://github.com/kovidgoyal/calibre)：完整书库与电子书工具集，GPLv3。
- [转换管线 Plumber](https://github.com/kovidgoyal/calibre/blob/master/src/calibre/ebooks/conversion/plumber.py)：输入插件、预处理、结构、样式、输出插件分阶段处理，并将书名、作者、封面等作为转换元数据。

EXReader 将书库编辑、阅读与转换分开。内置转换导出段落文字，复杂转换由桌面端按需调用 `ebook-convert`。调用使用参数数组，限制格式和大小，使用临时目录并设置超时，不经 shell 拼接命令。calibre 没有捆绑进 EXReader；移动端没有 calibre 转换。

## 实际复用的阅读组件

Foliate JS 固定在 `78914aef4466eb960965702401634c2cb348e9b1`，MIT，负责 EPUB、MOBI/KF8、FB2、分页与 CFI。PDF 单独使用 PDF.js。DOCX 使用 Mammoth，RTF 使用 rtf.js，内容用 DOMPurify 清理，并受 CSP 限制。

Foliate 本地补丁包括：禁用上游实验 PDF 分支，让 PDF 走 EXReader 的独立适配器；修正 iframe 加载时 ResizeObserver 提前排版，以及关闭后字体回调继续操作文档的生命周期问题。`scripts/vendor.py` 可复现。选择这些组件是为了覆盖六个平台的共享阅读核心，同时保留各组件的许可证和来源。
