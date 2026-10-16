# EXReader · 悦读

一个本地优先的跨平台电子书阅读器。共享 JavaScript 阅读核心，Tauri 2 桌面 / 移动壳，浏览器 PWA。当前版本 **0.1.1**。

[GitHub 仓库](https://github.com/NoGod3524/EXReader) · [预览版下载](https://github.com/NoGod3524/EXReader/releases) · [构建与测试](https://github.com/NoGod3524/EXReader/actions)

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
| Linux | x64 系统 WebKit 免安装包约 4.5 MiB，另有 AppImage / deb | `npm run tauri -- build --bundles appimage,deb` |
| macOS | 已生成 Intel + Apple Silicon 通用 app / dmg | `npm run tauri -- build --target universal-apple-darwin` |
| Android | ARM64 / x86_64 优化预览 APK，ARM64 约 8.9 MiB，固定预览签名 | Android SDK / NDK + `tauri android init` / `build` |
| iOS | 已生成模拟器 app 和未签名设备 IPA | macOS + Xcode + `tauri ios init` / `build` |
| iPadOS | 与 iOS 共用原生包，单独进行 iPad 模拟器启动检查 | 与 iOS 相同 |

Linux 轻量版 `system-webkit.tar.gz` 解压后运行 `./exreader`，需要系统 WebKitGTK 4.1 与 GTK 3；Ubuntu 可用 `sudo apt install libwebkit2gtk-4.1-0 libayatana-appindicator3-1 fonts-noto-cjk` 安装运行库和中文字体。需要自带运行库时选择较大的 AppImage 包；不使用 FUSE 时可运行 `APPIMAGE_EXTRACT_AND_RUN=1 ./EXReader*.AppImage`。Linux 当前构建基线为 Ubuntu 22.04；书库使用系统用户数据目录，通过 ZIP 备份迁移。原生构建后运行 `python3 scripts/portable-linux.py` 可生成轻量包。

macOS 解压 app ZIP 后移动到“应用程序”，当前预览包未做 Apple 公证。Android 选择 ARM64 APK，允许文件来源安装；后续预览包保留相同签名，可覆盖更新并保留书库。

iOS / iPadOS 的 `unsigned.ipa` 是供开发者签名的设备构建，不能直接安装；需要在 macOS 上配置自己的 Apple 开发者签名、设备或 TestFlight 分发。`simulator.app.zip` 只用于 Apple Silicon Mac 的 Xcode 模拟器。当前未完成 Apple 真机验证。

`.github/workflows/desktop.yml`、`android.yml`、`ios.yml` 可手动触发并下载产物。具体已通过的检查见 [验证记录](docs/VALIDATION.md)。原生应用的导出使用系统保存对话框，移动端仅显示内置转换。

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
