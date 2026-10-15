# EXReader · 悦读

一个本地优先的跨平台电子书阅读器。共享 JavaScript 阅读核心，Tauri 2 桌面 / 移动壳，浏览器 PWA。当前版本 **0.1.0**。

## 直接使用 Windows 免安装版

解压 `release/EXReader-Windows-x64-portable.zip`，双击 `EXReader.exe`。Windows 10 / 11 需要系统 WebView2；当前 Windows 11 通常已自带。

保留 `.portable` 文件时，书库位于程序旁的 `EXReader-data/`。更新程序时保留这个目录。迁移之前使用应用的“偏好设置 → 导出整个书库”，退出程序后再移动文件夹。

## 开发运行

要求 Node.js 22.12+（推荐 24）、npm。源码已包含固定版本的 Foliate 和 PWA 图标。

```sh
npm ci
node scripts/assets.mjs
npm run dev
```

打开 `http://127.0.0.1:1420`。导入本地书籍，或使用原创示例文章试读。开发模式不启用离线缓存。

```sh
npm run build
npm run preview
```

生产 `dist/` 可部署至任意支持 HTTPS 的静态服务器。iOS / iPadOS 在 Safari 中选择“添加到主屏幕”，Android 使用浏览器安装入口。首次完成资源缓存后支持离线。不同地址、浏览器和原生应用拥有独立书库，通过 ZIP 备份迁移。

## 功能状态

| 功能 | 当前实现 |
| --- | --- |
| PDF | PDF.js 按页渲染、缩放、文字选择、高亮、页码书签、搜索、进度恢复 |
| EPUB | Foliate 章节 / 分页、目录、搜索、CFI 标注、进度恢复 |
| MOBI / AZW3 | Foliate MOBI / KF8 解析，共用阅读设置与标注；测试覆盖基础无压缩 MOBI |
| FB2 | Foliate 解析，共用阅读设置与标注 |
| TXT | UTF-8 / UTF-16 / GB18030 自动识别，可指定 GBK / Big5 等编码 |
| RTF | rtf.js 转换为 HTML 后阅读，可调整正文排版 |
| DOCX | Mammoth 转换为 HTML 后阅读，保留可转换的语义内容；不复刻 Word 分页 |
| 有声书 | MP3 / M4A / M4B / OGG / OPUS / WAV / FLAC / AAC 文件入口、播放 / 暂停、倍速、跳转、进度恢复与时间书签；解码由设备提供 |
| 书库 | 导入 / 拖放、搜索书名作者标签、排序、网格 / 列表、收藏、已读状态、删除 |
| 元数据 | 改书名、作者、标签、封面；仅编辑书库副本 |
| 排版 | 字号、字体、行距、对齐、单双栏、滚动 / 翻页、暖纸 / 明亮 / 夜读 |
| 标注 | 流式书籍 CFI 高亮与笔记、PDF 文字范围高亮、书签、统一标注列表、Markdown 导出 |
| 备份 | 原书、封面、进度、书库信息和标注打包 ZIP，事务式合并恢复 |
| 内置转换 | 将电子书文字导出 EPUB、TXT、HTML、FB2、RTF、DOCX；EPUB 写入书库书名和封面 |
| 桌面转换 | 可调用另行提供的 calibre，输出 MOBI、PDF、EPUB、DOCX、RTF、FB2、TXT |

标注保存在书库中，不直接修改 PDF / EPUB。内置文字转换不保留图片、复杂表格、原排版和标注；扫描 PDF 需要额外 OCR。M4B 的内嵌章节、DRM / LCP、OCR、跨设备同步尚未实现。转换不能保证任意格式之间无损往返。

## 六个平台的交付方式

| 平台 | 当前交付 / 验证状态 | 原生构建 |
| --- | --- | --- |
| Windows | 本机生成 x64 免安装 EXE / ZIP；WebView2 需系统提供 | `npm run portable` |
| Linux | 共享浏览器核心；原生包需在 Linux 构建与验证 | `npm run tauri -- build`，生成 AppImage / deb 等 |
| macOS | 共享浏览器核心；原生包需在 macOS 构建与验证 | `npm run tauri -- build`，生成 app / dmg |
| Android | 响应式浏览器 / PWA；原生 APK 尚未本机生成 | Android SDK / NDK + `tauri android init` / `build` |
| iOS | 响应式浏览器 / PWA；原生包尚未构建或签名 | macOS + Xcode + `tauri ios init` / `build` |
| iPadOS | 与 iOS 共用核心，支持宽屏与分栏；需真机验证 | 与 iOS 相同 |

WebKit 自动化和手机视口测试不等于 Apple / Android 真机测试。这里的“支持六个平台”首先通过共享浏览器核心实现；除 Windows 外的原生安装包仍需对应工具链完成构建、签名和验证。iOS / iPadOS 原生程序遵循系统分发规则，不能像 Windows EXE 一样解压直接运行。

`.github/workflows/desktop.yml` 提供桌面构建工作流，`android.yml` 提供 Android 调试 APK 工作流；工作流尚未在远端运行。Apple 发布签名和商店分发需要开发者账号配置。

## 可选 calibre

安装 calibre，或把免安装 calibre 的完整目录放在 EXReader 程序旁的 `calibre/`（内部需有 `ebook-convert.exe`）。也识别 `Calibre Portable/Calibre/`、Windows 标准安装目录、macOS 应用目录和系统 PATH。

管理书籍 → 转换 / 导出 → 桌面 calibre 转换。格式白名单、输入 100 MB / 输出 200 MB 上限、3 分钟超时；无网络转换服务。calibre 需单独取得，本项目不附带。此桥接已实现，完整转换仍需安装 calibre 后验证。

## 验证

```sh
npx playwright install chromium webkit
npm test
npm run build
npx playwright test --config=playwright.production.config.js
cargo test --manifest-path src-tauri/Cargo.toml --release --lib
```

测试使用项目自制的 EPUB、MOBI、FB2、RTF、DOCX、PDF 和 WAV 样本，覆盖导入、打开、重开、标注、书库编辑、备份恢复、转换往返、内容隔离与响应式布局。Windows WebKit 自动化端口宣称支持 WAV，但无法解码本地 PCM 样本，因此明确跳过该环境的音频测试；相同文件在 Chromium 验证。Apple 真机音频仍需验证。

当前整体书库 ZIP 备份 / 恢复上限为 1 GB，内存中打包。大体积有声书库需要后续实现流式备份。文件存储和恢复同样受设备可用空间与浏览器配额影响。

## 代码与来源

`src/main.js` 为界面和交互；`store.js` 管理 IndexedDB 事务；`reader.js`、`pdf.js` 为阅读适配器；`formats.js` 负责解析入口与内容清理；`transfer.js` 负责导出和备份；`src-tauri/` 提供原生壳和 calibre 桥接。

[三个开源项目的学习记录](docs/PROJECT_STUDY.md) · [依赖与许可证](THIRD_PARTY_NOTICES.md)。自己的代码采用 MIT；没有复制或捆绑 Thorium、SumatraPDF、calibre 的应用代码。
